"""分析管线编排：视频 → CFR 标准化 → 逐帧检测+姿态 → 后处理 →
运动学指标 → 事件 → 双版本渲染 → 结果包导出。

不引入多目标跟踪/人物 ID：每帧用 IoU 规则稳定选择同一主体。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from ..common.data_models import (AnalysisResult, AnalysisSummary, Event,
                                  FrameRecord, MetricsResult, ProjectManifest,
                                  VideoInfo)
from ..common.halpe26 import NUM_KEYPOINTS
from ..common.timeutils import frame_to_timestamp_ms
from ..config.defaults import (DETECTOR, MODEL_REGISTRY, preset_full,
                               preset_skeleton_only)
from ..config.settings import UserSettings
from ..detection.detector import PersonDetector, select_subject
from ..events.detector import detect_events
from ..exporters.writers import (export_events_json, export_html_report,
                                 export_keypoints_json, export_manifest,
                                 export_metrics_csv, export_motion_json)
from ..postprocess.filters import (compute_pose_quality, postprocess)
from ..render.overlay import render_analysis_videos
from .errors import PipelineCancelled

# 进度回调签名: (stage: str, percent: int, detail: str)
ProgressCB = Callable[[str, int, str], None]

# 阶段划分（pose 阶段占大头）
_STAGE_POSE_START, _STAGE_POSE_END = 8, 62
_STAGE_POST_END = 68
_STAGE_RENDER_END = 96


@dataclass
class _InferenceOutcome:
    """逐帧推理产物。"""
    raw: np.ndarray               # (F,26,3) 原始关键点（无检测帧全 NaN）
    statuses: list[str]           # ok / person_not_found / low_pose_confidence
    bboxes: list[Optional[list[float]]]
    det_scores: list[Optional[float]]
    frames_read: int
    avg_ms: float


class AnalysisPipeline:
    """一次完整分析的工作流。模型在 run() 时惰性加载并缓存复用。"""

    def __init__(self, settings: UserSettings):
        self.settings = settings
        if settings.model_key not in MODEL_REGISTRY:
            raise KeyError(f'未知姿态模型: {settings.model_key}')
        self.spec = MODEL_REGISTRY[settings.model_key]
        self._detector: Optional[PersonDetector] = None
        self._pose = None  # RTMPoseRunner

    # ---------- 模型 ----------
    def _ensure_models(self):
        if self._pose is None:
            from ..pose.rtmpose import RTMPoseRunner
            self._detector = PersonDetector(
                DETECTOR, device=self.settings.device,
                score_thr=self.settings.thresholds.det_score_thr)
            self._pose = RTMPoseRunner(self.spec,
                                       device=self.settings.device,
                                       fp16=self.settings.fp16)

    # ---------- 项目目录 ----------
    @staticmethod
    def _project_dir(projects_root: Path, video_path: Path) -> Path:
        stem = ''.join(c if c.isalnum() or c in '-_' else '_'
                       for c in video_path.stem)[:60].strip('_') or 'video'
        name = datetime.now().strftime('%Y-%m-%d_%H%M%S') + '_' + stem
        d = projects_root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------- 主流程 ----------
    def run(self, video_path: str | Path,
            progress_cb: Optional[ProgressCB] = None,
            cancel_event=None) -> AnalysisResult:
        """执行完整分析。cancel_event 为 threading.Event，置位即取消。

        取消时抛出 PipelineCancelled（项目目录保留现场）。
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f'视频不存在: {video_path}')

        def report(stage: str, pct: int, detail: str = ''):
            if progress_cb:
                progress_cb(stage, pct, detail)

        def cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        # 1) 探测
        report('探测视频', 2, str(video_path.name))
        from ..video.ffmpeg_tools import ensure_cfr, probe_video
        info = probe_video(video_path)

        # 2) 项目目录
        projects_root = Path(self.settings.projects_root)
        projects_root.mkdir(parents=True, exist_ok=True)
        proj_dir = self._project_dir(projects_root, video_path)
        report('创建项目', 4, str(proj_dir.name))

        # 3) CFR 标准化
        report('CFR 标准化', 5, '转换中' if info.vfr else '已为恒定帧率，直接复制')
        src_cfr = proj_dir / 'source_cfr.mp4'
        cfr_info = ensure_cfr(video_path, src_cfr, info)
        fps = cfr_info.fps if cfr_info.fps > 0 else 30.0
        warnings: list[str] = []
        vfr_converted = bool(info.vfr)
        if vfr_converted:
            warnings.append(f'源视频疑似可变帧率，已标准化为 CFR {fps:.3f}fps')
        if abs(cfr_info.frame_count - info.frame_count) > \
                max(3, 0.02 * max(info.frame_count, 1)):
            warnings.append(
                f'标准化后帧数由 {info.frame_count} 变为 {cfr_info.frame_count}')

        # 4) 逐帧推理
        self._ensure_models()
        report('加载模型', 6, self.spec.display_name)
        outcome = self._inference_loop(src_cfr, report, cancel_event)
        if cancelled():
            raise PipelineCancelled('推理阶段取消')
        if outcome.frames_read == 0:
            raise RuntimeError('标准化视频无法读取任何帧')
        report('逐帧推理', _STAGE_POSE_END,
               f'{outcome.frames_read} 帧，{outcome.avg_ms:.0f}ms/帧')

        # 5) 后处理
        if cancelled():
            raise PipelineCancelled('后处理阶段取消')
        report('姿态后处理', _STAGE_POSE_END + 2, '')
        thr = self.settings.thresholds
        # 身高像素尺度由 postprocess 内部估计（mark_invalid 后），
        # 估计失败时自动跳过尖峰跳点检测、保留骨骼段突变检测
        filtered, n_outliers = postprocess(outcome.raw, fps, thr)
        if n_outliers:
            warnings.append(f'剔除跳点 {n_outliers} 个')

        # 6) 质量与指标
        report('计算运动学指标', _STAGE_POST_END, '')
        F = outcome.frames_read
        frame_indices = np.arange(F, dtype=np.int64)
        ts = np.array([frame_to_timestamp_ms(i, fps) for i in frame_indices])
        pose_quality = np.zeros(F, dtype=np.float64)
        valid_ratio = np.zeros(F, dtype=np.float64)
        missing_ratio = np.ones(F, dtype=np.float64)
        for i in range(F):
            if outcome.statuses[i] != 'person_not_found':
                frame = outcome.raw[i]
                finite = np.isfinite(frame[:, 0])
                valid_ratio[i] = finite.mean()
                missing_ratio[i] = 1.0 - valid_ratio[i]
                pose_quality[i] = compute_pose_quality(
                    frame, outcome.det_scores[i] or 0.0,
                    thr.keypoint_score_thr)
        from ..biomechanics.metrics import compute_metrics
        metrics = compute_metrics(filtered, fps, frame_indices, ts,
                                  pose_quality, valid_ratio, missing_ratio)
        events = detect_events(metrics, outcome.statuses)
        report('事件检测', _STAGE_POST_END + 4, f'{len(events)} 个事件')

        # 步态时空参数汇总（触地/腾空/周期/步频）+ 每步事件条件化特征
        # + 身体尺度归一化 + 精英参考库 z-score 对比
        from ..events.gait import gait_step_features, gait_temporal_params
        gait_summary = gait_temporal_params(events, fps)

        from ..biomechanics.scale import body_scale, run_speed_estimate
        bscale = body_scale(filtered)
        height_m = getattr(self.settings, 'athlete_height_m', None)
        pelvis_traj = metrics.trajectories.get('pelvis')
        if pelvis_traj is not None:
            speed = run_speed_estimate(
                pelvis_traj[:, 0], metrics.timestamps_ms,
                body_height_px=bscale.get('body_height_px'),
                height_m=height_m)
            if speed:
                bscale.update(speed)
        gait_summary['body_scale'] = bscale
        gait_summary['steps'] = gait_step_features(
            metrics, events, body_scale=bscale)

        if gait_summary['steps']:
            from ..biomechanics.references import (
                AUTO_COMPARE_REFS, compare_steps_to_reference)
            cadence_hz = (gait_summary['cadence_spm'] / 60.0
                          if gait_summary.get('cadence_spm') else None)
            gait_summary['reference_comparison'] = [
                compare_steps_to_reference(
                    gait_summary['steps'], key, cadence_hz=cadence_hz)
                for key in AUTO_COMPARE_REFS]

            # 疲劳趋势（前/后半程对比）+ 起跳步识别（解锁跳高参考对比）
            from ..events.fatigue import fatigue_trend
            from ..events.takeoff import identify_takeoff_steps
            gait_summary['fatigue_trend'] = fatigue_trend(
                gait_summary['steps'])
            gait_summary['takeoff_steps'] = identify_takeoff_steps(
                gait_summary['steps'])
            if gait_summary['takeoff_steps']:
                takeoff_frames = {t['td_frame']
                                  for t in gait_summary['takeoff_steps']}
                gait_summary['reference_comparison'].append(
                    compare_steps_to_reference(
                        [s for s in gait_summary['steps']
                         if s['td_frame'] in takeoff_frames],
                        'hj_takeoff_success'))
        else:
            gait_summary['fatigue_trend'] = None
            gait_summary['takeoff_steps'] = []

        # 7) 渲染
        report('渲染分析视频', _STAGE_POST_END + 5, '')
        out_full = proj_dir / 'analysis.mp4'
        out_skel = proj_dir / 'analysis_skeleton.mp4'
        overlay_full = self.settings.overlay
        overlay_skel = preset_skeleton_only()

        def render_progress(p: float):
            report('渲染分析视频',
                   int(_STAGE_POST_END + 5 +
                       (_STAGE_RENDER_END - _STAGE_POST_END - 5) * p),
                   f'{int(p * 100)}%')

        render_res = render_analysis_videos(
            src_cfr, out_full, out_skel, filtered, metrics, events,
            overlay_full, overlay_skel,
            progress_cb=render_progress, cancel_event=cancel_event)
        if render_res['status'] == 'cancelled':
            raise PipelineCancelled('渲染阶段取消')
        warnings.extend(render_res.get('warnings', []))

        # 8) 导出
        report('导出结果', _STAGE_RENDER_END + 1, '')
        valid_frames = sum(1 for s in outcome.statuses if s == 'ok')
        lowq_frames = sum(1 for s in outcome.statuses
                          if s == 'low_pose_confidence')
        lost_frames = sum(1 for s in outcome.statuses
                          if s == 'person_not_found')

        manifest = ProjectManifest(
            source_video='source_cfr.mp4',
            fps=round(fps, 3),
            frame_count=F,
            width=cfr_info.width,
            height=cfr_info.height,
            pose_model=self.spec.display_name,
            pose_input_size=[self.spec.input_size[0], self.spec.input_size[1]],
            detector=DETECTOR.name,
            created_at=datetime.now().isoformat(timespec='seconds'),
            analysis_status='completed',
            valid_frames=valid_frames,
            valid_ratio=round(valid_frames / max(F, 1), 4),
            avg_pose_quality=round(float(np.mean(pose_quality))
                                   if F else 0.0, 4),
            inference_ms_per_frame=round(outcome.avg_ms, 1),
            source_video_original=str(video_path),
            vfr_converted=vfr_converted,
            warnings=warnings)
        export_manifest(proj_dir / 'manifest.json', manifest)

        kp_meta = {
            'model': self.spec.display_name,
            'num_keypoints': NUM_KEYPOINTS,
            'fps': round(fps, 3),
            'frame_count': F,
            'source_video': 'source_cfr.mp4',
            'source_video_original': str(video_path),
            'valid_frames': valid_frames,
            'low_quality_frames': lowq_frames,
            'person_not_found_frames': lost_frames,
        }
        frames_records = self._build_frame_records(outcome, filtered, ts)
        export_keypoints_json(proj_dir / 'keypoints.json', kp_meta,
                              frames_records)
        export_metrics_csv(proj_dir / 'metrics.csv', metrics)
        export_events_json(proj_dir / 'events.json', events,
                           gait_summary=gait_summary)
        export_motion_json(proj_dir / 'motion.json', manifest, metrics,
                           video_id=proj_dir.name)

        # 汇总
        angle_stats = {}
        for k, series in metrics.angles.items():
            fin = series[np.isfinite(series)]
            if len(fin):
                angle_stats[k] = {
                    'min': round(float(fin.min()), 1),
                    'max': round(float(fin.max()), 1),
                    'mean': round(float(fin.mean()), 1)}
        lean = metrics.torso_lean[np.isfinite(metrics.torso_lean)]
        if len(lean):
            angle_stats['torso_lean'] = {
                'min': round(float(lean.min()), 1),
                'max': round(float(lean.max()), 1),
                'mean': round(float(lean.mean()), 1)}
        summary = AnalysisSummary(
            total_frames=F,
            valid_frames=valid_frames,
            valid_ratio=round(valid_frames / max(F, 1), 4),
            avg_pose_quality=round(float(np.mean(pose_quality))
                                   if F else 0.0, 4),
            angle_stats=angle_stats,
            events=events,
            warnings=warnings)
        export_html_report(proj_dir / 'report.html', proj_dir.name,
                           manifest, summary, metrics, events)

        result = AnalysisResult(
            project_dir=proj_dir,
            manifest=manifest,
            summary=summary,
            paths={
                'source_cfr': src_cfr,
                'analysis': out_full,
                'analysis_skeleton': out_skel,
                'manifest': proj_dir / 'manifest.json',
                'keypoints': proj_dir / 'keypoints.json',
                'metrics': proj_dir / 'metrics.csv',
                'events': proj_dir / 'events.json',
                'motion': proj_dir / 'motion.json',
                'report': proj_dir / 'report.html',
            },
            metrics=metrics,
            gait_summary=gait_summary)
        report('完成', 100, str(proj_dir.name))
        return result

    # ---------- 逐帧推理 ----------
    def _inference_loop(self, video: Path,
                        report: ProgressCB, cancel_event) -> _InferenceOutcome:
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            raise RuntimeError(f'无法打开视频: {video}')
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        thr = self.settings.thresholds

        raw_frames: list[np.ndarray] = []
        statuses: list[str] = []
        bboxes: list[Optional[list[float]]] = []
        det_scores: list[Optional[float]] = []
        prev_bbox: Optional[tuple] = None
        t_sum = 0.0
        n = 0
        last_report = time.perf_counter()
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    break
                ok, frame = cap.read()
                if not ok:
                    break
                t0 = time.perf_counter()
                detections = self._detector.detect(frame)  # type: ignore[union-attr]
                subject = select_subject(detections, prev_bbox,
                                         min_iou=thr.min_iou)
                if subject is None:
                    raw_frames.append(
                        np.full((NUM_KEYPOINTS, 3), np.nan, np.float32))
                    statuses.append('person_not_found')
                    bboxes.append(None)
                    det_scores.append(None)
                    prev_bbox = None
                else:
                    kpt = self._pose.estimate(frame, subject.xyxy)  # type: ignore[union-attr]
                    raw_frames.append(kpt)
                    bboxes.append([float(v) for v in subject.xyxy])
                    det_scores.append(float(subject.score))
                    prev_bbox = subject.xyxy
                    finite = np.isfinite(kpt[:, 0])
                    ratio = float(finite.mean())
                    mean_score = float(np.nanmean(kpt[:, 2])) \
                        if finite.any() else 0.0
                    if ratio < thr.low_pose_valid_ratio or \
                            mean_score < thr.low_pose_mean_score:
                        statuses.append('low_pose_confidence')
                    else:
                        statuses.append('ok')
                t_sum += time.perf_counter() - t0
                n += 1
                now = time.perf_counter()
                if now - last_report >= 0.5:
                    last_report = now
                    pct = _STAGE_POSE_START + int(
                        (_STAGE_POSE_END - _STAGE_POSE_START) *
                        (n / total if total > 0 else 0))
                    report('逐帧推理', min(pct, _STAGE_POSE_END),
                           f'{n}/{total if total > 0 else "?"} 帧')
        finally:
            cap.release()

        raw = (np.stack(raw_frames) if raw_frames
               else np.zeros((0, NUM_KEYPOINTS, 3), np.float32))
        avg_ms = t_sum / max(n, 1) * 1000
        return _InferenceOutcome(raw=raw, statuses=statuses,
                                 bboxes=bboxes, det_scores=det_scores,
                                 frames_read=n, avg_ms=avg_ms)

    # ---------- FrameRecord 组装 ----------
    @staticmethod
    def _build_frame_records(outcome: _InferenceOutcome,
                             filtered: np.ndarray,
                             ts: np.ndarray) -> list[FrameRecord]:
        records = []
        for i in range(outcome.frames_read):
            status = outcome.statuses[i]
            has_pose = status != 'person_not_found'
            rec = FrameRecord.from_arrays(
                frame_index=i,
                timestamp_ms=float(ts[i]),
                status=status,
                bbox=(np.asarray(outcome.bboxes[i], dtype=float)
                      if outcome.bboxes[i] is not None else None),
                det_score=outcome.det_scores[i],
                pose_quality=None,
                raw=outcome.raw[i] if has_pose else None,
                filtered=filtered[i] if has_pose else None)
            records.append(rec)
        return records
