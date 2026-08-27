"""POST /api/analysis/submit 的 P0 执行体（校验 + 打点持久化 + 基础报告）。

契约见 client/API_CONTRACT.md §4（submit 请求体）与 §5（events.json /
gait_summary）。项目目录布局与 sports_pose_analyzer 的 PROJECTS_DIR
（outputs 根）一致：outputs_dir/<video_id>/{motion.json, events.json}。

纯标准库实现（json / datetime / pathlib），不依赖 fastapi 与
sports_pose_analyzer；由框架层（router + 任务 worker）调用：

  runner = build_runner()
  runner.validate(payload, outputs_dir)      # 同步快速校验 → router 400
  runner.run(payload, outputs_dir, progress_cb, cancel_event, task_id)
                                             # worker 线程内三阶段执行
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

SCHEMA_VERSION = '1.0'

# 请求 metrics 快照与服务端 motion.json 源值的比对允差（绝对值）：
# 契约 §4 声明客户端快照为原样复制，差值超过 0.01（严格大于）记入
# mismatches；0.01 本身及以内视为一致。
_MISMATCH_TOL = 0.01
# event_context 命中半径：|marker.frameIndex - event.frame_index| ≤ 该值（帧）。
_EVENT_CONTEXT_RADIUS = 2


class ValidationError(Exception):
    """请求校验失败（router 映射为 HTTP 400）。

    code 取值：
      markers_empty            — 未包含任何打点标记
      unknown_video            — 未找到视频项目（目录或 motion.json 缺失）
      frame_index_out_of_range — 打点帧号越界
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TaskCancelled(Exception):
    """任务在阶段边界被取消（cancel_event 置位）。"""


def build_runner() -> 'Runner':
    """工厂入口，供框架层获取执行体。"""
    return Runner()


class Runner:
    """submit 执行体：validate 同步快速校验；run 为三阶段异步执行体。"""

    def validate(self, payload: dict, outputs_dir: Path) -> None:
        """同步快速校验；失败抛 ValidationError。

        帧号上限以服务端 motion.json 为准（frame_count，缺失时回退
        frames 长度），不信任请求体自带的 frame_count。
        """
        payload = payload or {}
        markers = payload.get('markers')
        if not isinstance(markers, list) or not markers:
            raise ValidationError('markers_empty', '未包含任何打点标记')

        video_id = payload.get('video_id')
        if (not isinstance(video_id, str) or not video_id
                or video_id in ('.', '..')
                or '/' in video_id or '\\' in video_id):
            raise ValidationError('unknown_video', f'未找到视频项目: {video_id}')

        motion = _read_json(Path(outputs_dir) / video_id / 'motion.json')
        if not isinstance(motion, dict):
            raise ValidationError('unknown_video', f'未找到视频项目: {video_id}')

        frame_count = _frame_count(motion)
        for marker in markers:
            fi = marker.get('frameIndex') if isinstance(marker, dict) else None
            if (not isinstance(fi, int) or isinstance(fi, bool)
                    or fi < 0 or fi >= frame_count):
                raise ValidationError(
                    'frame_index_out_of_range',
                    f'打点帧号越界: {fi!r}（有效范围 0..{frame_count - 1}）')

    def run(self, payload: dict, outputs_dir: Path,
            progress_cb: Optional[Callable[[str, int, str], None]] = None,
            cancel_event: Any = None, task_id: str = '') -> dict:
        """在 worker 线程内执行三阶段：校验(0) → 持久化(40) → 报告(80) → 完成(100)。

        每个阶段边界检查 cancel_event.is_set()，置位则抛 TaskCancelled。
        返回 {"result_path", "markers_saved", "report_path"}。
        """
        outputs_dir = Path(outputs_dir)
        video_id = payload.get('video_id')
        project_dir = outputs_dir / str(video_id)

        # 阶段 1：校验（0%）——防御性重新校验
        _raise_if_cancelled(cancel_event)
        _notify(progress_cb, 'validate', 0, '校验提交数据')
        self.validate(payload, outputs_dir)
        markers = payload['markers']

        # 阶段 2：持久化打点（40%）——每次提交是最新快照，已存在则覆盖
        _raise_if_cancelled(cancel_event)
        _notify(progress_cb, 'persist', 40, '持久化打点数据')
        _write_json(project_dir / 'submitted_markers.json', {
            'schema_version': SCHEMA_VERSION,
            'task_id': task_id,
            'video_id': video_id,
            'submitted_at': _local_now_iso(),
            'markers': markers,
            'motion': payload.get('motion'),
        })

        # 阶段 3：生成基础报告（80%，无模型评分）
        _raise_if_cancelled(cancel_event)
        _notify(progress_cb, 'report', 80, '生成基础报告')
        report_path = project_dir / 'score_report.json'
        _write_json(report_path, self._build_report(payload, project_dir, task_id))

        _notify(progress_cb, 'done', 100, '分析完成')
        return {
            'result_path': f'outputs/{video_id}/score_report.json',
            'markers_saved': len(markers),
            'report_path': str(report_path.resolve()),
        }

    # ---------- 报告构建 ----------

    def _build_report(self, payload: dict, project_dir: Path, task_id: str) -> dict:
        motion = _read_json(project_dir / 'motion.json') or {}
        events_doc = _read_json(project_dir / 'events.json')
        if isinstance(events_doc, dict):
            events = events_doc.get('events') or []
            gait_summary = events_doc.get('gait_summary')
        else:
            events, gait_summary = [], None

        frame_metrics = {
            frame.get('frameIndex'): (frame.get('metrics') or {})
            for frame in (motion.get('frames') or [])
            if isinstance(frame, dict)
            and isinstance(frame.get('frameIndex'), int)
        }
        steps = (gait_summary.get('steps') or []) if isinstance(gait_summary, dict) else []

        report_markers = [
            _report_marker(marker, frame_metrics, steps, events)
            for marker in payload.get('markers') or []
        ]
        return {
            'schema_version': SCHEMA_VERSION,
            'task_id': task_id,
            'video_id': payload.get('video_id'),
            'created_at': _local_now_iso(),
            'markers': report_markers,
            'summary': _build_summary(gait_summary, len(report_markers)),
        }


# ---------- 标记条目构建 ----------

def _report_marker(marker: dict, frame_metrics: dict,
                   steps: list, events: list) -> dict:
    marker = marker or {}
    frame_index = marker.get('frameIndex')
    entry = {
        'id': marker.get('id'),
        'frameIndex': frame_index,
        'timestampMs': marker.get('timestampMs'),
        'label': marker.get('label'),
        'comment': marker.get('comment'),
        'metrics': marker.get('metrics'),
    }
    # 二次校验：请求快照 vs 服务端 motion.json 该帧源值（逐键比对）
    server_metrics = frame_metrics.get(frame_index) or {}
    mismatches = _compare_metrics(marker.get('metrics'), server_metrics)
    if mismatches:
        entry['metrics_checked'] = {
            'metrics': server_metrics,
            'mismatches': mismatches,
        }
    entry['step'] = _match_step(steps, frame_index)
    entry['event_context'] = _event_context(events, frame_index)
    return entry


def _compare_metrics(submitted: Optional[dict], server: dict) -> dict:
    """逐键比对请求快照与服务端源值；返回 {key: {submitted, server}}，空即一致。

    只遍历请求快照出现的键（服务端多出的键不视为不一致）。
    """
    mismatches = {}
    for key, value in (submitted or {}).items():
        server_value = server.get(key)
        if _values_disagree(value, server_value):
            mismatches[key] = {'submitted': value, 'server': server_value}
    return mismatches


def _values_disagree(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is not b                     # 一侧 null 一侧有值 → 不一致
    if isinstance(a, bool) or isinstance(b, bool):
        return a != b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) > _MISMATCH_TOL     # 严格大于容差才算不一致
    return a != b


def _match_step(steps: list, frame_index: Any) -> Optional[dict]:
    """frameIndex 所属步：td_frame ≤ fi < next_td_frame（None 表示区间开到结尾）。

    多步匹配取 td_frame 最大者；gait_summary 缺失 / steps 为空 / 无匹配
    均返回 None。
    """
    if not isinstance(frame_index, int) or isinstance(frame_index, bool):
        return None
    best = None
    for step in steps:
        if not isinstance(step, dict):
            continue
        td = step.get('td_frame')
        next_td = step.get('next_td_frame')
        if not isinstance(td, int) or isinstance(td, bool) or td > frame_index:
            continue
        if next_td is not None and frame_index >= next_td:
            continue
        if best is None or td > best.get('td_frame'):
            best = step
    return best


def _event_context(events: list, frame_index: Any) -> Optional[list]:
    """|frameIndex - event.frame_index| ≤ 2 的邻近事件（按距离升序）；无则 None。"""
    if not isinstance(frame_index, int) or isinstance(frame_index, bool):
        return None
    hits = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_frame = event.get('frame_index')
        if not isinstance(event_frame, int) or isinstance(event_frame, bool):
            continue
        delta = event_frame - frame_index
        if abs(delta) <= _EVENT_CONTEXT_RADIUS:
            hits.append({
                'type': event.get('type'),
                'frame_index': event_frame,
                'timestamp_ms': event.get('timestamp_ms'),
                'delta_frames': delta,
            })
    hits.sort(key=lambda h: (abs(h['delta_frames']), h['frame_index']))
    return hits or None


# ---------- summary 构建 ----------

def _build_summary(gait_summary: Any, n_markers: int) -> dict:
    summary = {'n_markers': n_markers}
    if not isinstance(gait_summary, dict):
        summary['gait'] = None
        summary['fatigue_trend'] = None
        summary['takeoff_steps'] = None
        return summary

    steps = gait_summary.get('steps') or []
    gait = {
        'n_steps': len(steps),
        'cadence_spm': gait_summary.get('cadence_spm'),
        'contact_time_ms_mean': _contact_time_ms_mean(gait_summary),
    }
    reference_comparison = gait_summary.get('reference_comparison')
    if reference_comparison:
        gait['reference_comparison'] = [
            {'reference': item.get('reference'),
             'side_summary': item.get('side_summary') or {}}
            for item in reference_comparison if isinstance(item, dict)
        ]
    summary['gait'] = gait

    fatigue = gait_summary.get('fatigue_trend')
    summary['fatigue_trend'] = (
        {'n_steps': fatigue.get('n_steps'), 'delta': fatigue.get('delta') or {}}
        if isinstance(fatigue, dict) else None)

    takeoff_steps = gait_summary.get('takeoff_steps')
    summary['takeoff_steps'] = takeoff_steps or None
    return summary


def _contact_time_ms_mean(gait_summary: dict) -> Optional[float]:
    """左右侧 contact_time_ms.mean 的平均值（保留 2 位小数）。

    某侧统计块缺失/为 null 则不计入；两侧均缺 → None。
    """
    means = []
    for side in ('left', 'right'):
        block = gait_summary.get(side)
        if not isinstance(block, dict):
            continue
        stats = block.get('contact_time_ms')
        mean = stats.get('mean') if isinstance(stats, dict) else None
        if isinstance(mean, (int, float)) and not isinstance(mean, bool):
            means.append(mean)
    if not means:
        return None
    return round(sum(means) / len(means), 2)


# ---------- 基础 IO / 工具 ----------

def _read_json(path: Path) -> Any:
    """读取 JSON 文件；缺失或解析失败返回 None（调用方按可选文件处理）。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data: Any) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _local_now_iso() -> str:
    """本地时区 ISO-8601 时间戳（含 UTC 偏移，如 2026-08-26T15:30:00+08:00）。"""
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _frame_count(motion: dict) -> int:
    """服务端帧数：motion.json 的 frame_count，缺失/非法时回退 frames 长度。"""
    frame_count = motion.get('frame_count')
    if (isinstance(frame_count, int) and not isinstance(frame_count, bool)
            and frame_count > 0):
        return frame_count
    return len(motion.get('frames') or [])


def _raise_if_cancelled(cancel_event: Any) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TaskCancelled('任务已取消')


def _notify(progress_cb: Optional[Callable[[str, int, str], None]],
            stage: str, percent: int, detail: str) -> None:
    if progress_cb is not None:
        progress_cb(stage, percent, detail)
