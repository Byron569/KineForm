"""视频骨架叠加渲染。

只依赖 cv2/numpy/PIL（PIL 缺失或无中文字体时自动降级为 cv2 英文绘制），
模块顶层不 import torch/mmpose，保证可在无 GPU 环境下运行与测试。
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np

from ..common.data_models import Event, MetricsResult
from ..common.halpe26 import (
    ANGLE_DEFS, NECK, NUM_KEYPOINTS, SKELETON_LINKS, SIDE_COLORS)
from ..config.defaults import OverlayConfig
from ..video.ffmpeg_tools import transcode_h264

# 叠加层上只显示的四项关节角（左右膝/左右髋）
_ANGLE_OVERLAY_KEYS = ('left_knee', 'right_knee', 'left_hip', 'right_hip')

# 事件类型 → 中文标签（渲染显示用，未知类型原样显示）
EVENT_LABELS_CN: dict[str, str] = {
    'min_left_knee_angle': '左膝最小',
    'max_left_knee_angle': '左膝最大',
    'min_right_knee_angle': '右膝最小',
    'max_right_knee_angle': '右膝最大',
    'min_left_hip_angle': '左髋最小',
    'max_left_hip_angle': '左髋最大',
    'min_right_hip_angle': '右髋最小',
    'max_right_hip_angle': '右髋最大',
    'min_left_ankle_angle': '左踝最小',
    'max_left_ankle_angle': '左踝最大',
    'min_right_ankle_angle': '右踝最小',
    'max_right_ankle_angle': '右踝最大',
    'min_left_elbow_angle': '左肘最小',
    'max_left_elbow_angle': '左肘最大',
    'min_right_elbow_angle': '右肘最小',
    'max_right_elbow_angle': '右肘最大',
    'min_torso_lean': '躯干倾角最小',
    'max_torso_lean': '躯干倾角最大',
    'max_pelvis_speed': '骨盆速度峰值',
    'pose_lost': '姿态丢失',
    'pose_recovered': '姿态恢复',
}

# 各类文本的基础字号（像素）
_FONT_PX_INFO = 20      # 帧号/时间戳/角度值
_FONT_PX_QUALITY = 18   # 姿态质量行
_FONT_PX_EVENT = 20     # 事件标签
_FONT_PX_LOST = 30      # 姿态丢失提示
_FONT_PX_ID = 13        # 关键点编号

# 常规文本颜色（BGR）
_COLOR_TEXT = (255, 255, 255)      # 白色（黑描边）
_COLOR_LEAN = (180, 255, 255)      # 躯干倾角用淡黄，与关节角区分
_COLOR_EVENT = (0, 165, 255)       # 事件标签橙色
_COLOR_ID = (255, 255, 0)          # 关键点编号青黄色
_COLOR_TRAJ = (0, 255, 255)        # 骨盆轨迹黄色
_COLOR_LOST = (0, 0, 255)          # 姿态丢失红色


# ---------------- 文本绘制（支持中文，单次往返批量绘制） ----------------
_FONT_CACHE: dict[int, object] = {}
_FONT_CANDIDATES = (
    r'C:\Windows\Fonts\msyh.ttc',            # 微软雅黑
    r'C:\Windows\Fonts\simhei.ttf',          # 黑体
    r'C:\Windows\Fonts\simsun.ttc',          # 宋体
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
)


def _load_font(px: int):
    """按字号加载支持中文的 PIL 字体（带缓存）；不可用返回 None（降级 cv2）。"""
    if px in _FONT_CACHE:
        return _FONT_CACHE[px]
    font = None
    try:
        from PIL import ImageFont
        for p in _FONT_CANDIDATES:
            if os.path.exists(p):
                font = ImageFont.truetype(p, px)
                break
    except Exception:
        font = None
    _FONT_CACHE[px] = font
    return font


def _text_size(text: str, px: int) -> tuple[int, int]:
    """测量文本宽高（布局用，近似值即可）。"""
    font = _load_font(px)
    if font is not None:
        box = font.getbbox(text)
        return max(1, box[2] - box[0]), max(1, box[3] - box[1])
    scale = px / 28.0
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    return max(1, w), max(1, h)


def _flush_texts(img: np.ndarray, texts: list[tuple]) -> None:
    """把收集到的文本一次性绘制到 img（PIL 单次往返；降级时用 cv2 逐条画）。

    texts 每项为 (text, x, y, color_bgr, px, outline_color_bgr)，
    (x, y) 为文本块左上角锚点。
    """
    if not texts:
        return
    if _load_font(_FONT_PX_INFO) is not None:
        # 有中文字体：PIL 批量绘制，带描边
        from PIL import Image, ImageDraw
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        for text, x, y, color, px, outline in texts:
            font = _load_font(px)
            draw.text(
                (int(x), int(y)), text, font=font,
                fill=(int(color[2]), int(color[1]), int(color[0])),
                stroke_width=max(1, px // 10),
                stroke_fill=(int(outline[2]), int(outline[1]), int(outline[0])))
        img[:] = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
        return
    # 降级：cv2 只能绘制 ASCII（中文会显示为问号），先粗黑再细彩模拟描边
    for text, x, y, color, px, outline in texts:
        scale = px / 28.0
        org = (int(x), int(y) + px)
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale,
                    outline, max(2, px // 8), cv2.LINE_AA)
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale,
                    color, 1, cv2.LINE_AA)


# ---------------- 单帧叠加绘制 ----------------
def draw_skeleton_frame(img: np.ndarray,
                        kpts,
                        overlay: OverlayConfig,
                        *,
                        angles: dict | None = None,
                        torso_lean: float | None = None,
                        pelvis_traj: Sequence[tuple[float, float]] | None = None,
                        event_labels: Sequence[str] | None = None,
                        frame_index: int | None = None,
                        timestamp_ms: float | None = None,
                        pose_quality: float | None = None) -> np.ndarray:
    """在单帧图像上绘制骨架与信息叠加层（就地修改并返回 img）。

    参数：
        img: BGR uint8 图像（就地修改）
        kpts: (26,3) 关键点数组，通道 (x,y,score)；None/形状不对/全 NaN 视为姿态丢失
        overlay: OverlayConfig 渲染开关
        angles: {'left_knee': v, ...} 当前帧关节角（仅绘制左右膝/左右髋四项）
        torso_lean: 当前帧躯干倾角（带符号，画在颈部点旁）
        pelvis_traj: 最近 N 帧骨盆 (x,y) 轨迹（黄色折线）
        event_labels: 当前帧事件类型列表（右上角中文显示）
        frame_index / timestamp_ms: 左上角帧号与时间戳（如 '#123 4.12s'）
        pose_quality: 帧号下方一行的姿态质量（如 '质量 0.94'）
    """
    h, w = img.shape[:2]
    texts: list[tuple] = []   # 收集本帧全部文本，最后统一绘制

    # 解析关键点数组并判定姿态是否丢失
    arr = None
    if kpts is not None:
        a = np.asarray(kpts, dtype=float)
        if a.ndim == 2 and a.shape[0] == NUM_KEYPOINTS and a.shape[1] >= 2:
            arr = a
    valid = (np.isfinite(arr[:, 0]) & np.isfinite(arr[:, 1])
             if arr is not None else None)
    pose_lost = valid is None or not bool(valid.any())

    if pose_lost:
        # 姿态丢失：画面中央红字黑描边
        text = '姿态丢失'
        tw, th = _text_size(text, _FONT_PX_LOST)
        texts.append((text, max(0, w // 2 - tw // 2), max(0, h // 2 - th // 2),
                      _COLOR_LOST, _FONT_PX_LOST, (0, 0, 0)))
    else:
        _draw_pose(img, arr, valid, overlay, texts,
                   angles=angles, torso_lean=torso_lean)

    # 骨盆轨迹：黄色折线（最近 N 帧有效点）
    if overlay.draw_trajectory and pelvis_traj:
        pts = np.array([(x, y) for x, y in pelvis_traj
                        if math.isfinite(x) and math.isfinite(y)],
                       dtype=np.int32).reshape(-1, 2)
        if len(pts) >= 2:
            cv2.polylines(img, [pts], False, _COLOR_TRAJ, 2, cv2.LINE_AA)

    # 事件标签：右上角右对齐垂直堆叠
    if overlay.draw_event_labels and event_labels:
        y = 10
        for label in event_labels:
            text = EVENT_LABELS_CN.get(str(label), str(label))
            tw, th = _text_size(text, _FONT_PX_EVENT)
            texts.append((text, max(0, w - tw - 12), y,
                          _COLOR_EVENT, _FONT_PX_EVENT, (0, 0, 0)))
            y += th + 8

    # 帧号 + 时间戳：左上角第一行，如 '#123 4.12s'
    if overlay.draw_frame_info:
        parts = []
        if frame_index is not None:
            parts.append(f'#{int(frame_index)}')
        if timestamp_ms is not None:
            v = float(timestamp_ms)
            if math.isfinite(v):
                parts.append(f'{v / 1000.0:.2f}s')
        if parts:
            texts.append((' '.join(parts), 12, 10,
                          _COLOR_TEXT, _FONT_PX_INFO, (0, 0, 0)))
    # 姿态质量：帧号下方第二行，如 '质量 0.94'
    if overlay.draw_quality and pose_quality is not None:
        v = float(pose_quality)
        if math.isfinite(v):
            texts.append((f'质量 {v:.2f}', 12, 10 + _FONT_PX_INFO + 10,
                          _COLOR_TEXT, _FONT_PX_QUALITY, (0, 0, 0)))

    _flush_texts(img, texts)
    return img


def _draw_pose(img: np.ndarray, arr: np.ndarray, valid: np.ndarray,
               overlay: OverlayConfig, texts: list[tuple], *,
               angles: dict | None = None,
               torso_lean: float | None = None) -> None:
    """绘制骨架连线/关键点圆点/编号/关节角与躯干倾角（arr 为有效 (26,3) 数组）。"""
    pts = arr[:, :2]

    # 骨架连线：左右/中轴配色，线宽 2，抗锯齿
    if overlay.draw_skeleton:
        for a, b, side in SKELETON_LINKS:
            if valid[a] and valid[b]:
                pa = (int(round(pts[a, 0])), int(round(pts[a, 1])))
                pb = (int(round(pts[b, 0])), int(round(pts[b, 1])))
                cv2.line(img, pa, pb, SIDE_COLORS[side], 2, cv2.LINE_AA)

    # 关键点：白色实心小圆
    if overlay.draw_keypoints:
        for i in range(NUM_KEYPOINTS):
            if valid[i]:
                cv2.circle(img, (int(round(pts[i, 0])), int(round(pts[i, 1]))),
                           3, (255, 255, 255), -1, cv2.LINE_AA)

    # 关键点编号
    if overlay.draw_point_ids:
        for i in range(NUM_KEYPOINTS):
            if valid[i]:
                texts.append((str(i),
                              int(round(pts[i, 0])) + 4,
                              int(round(pts[i, 1])) - _FONT_PX_ID - 2,
                              _COLOR_ID, _FONT_PX_ID, (0, 0, 0)))

    # 关节角度值：黑描边白字画在关节顶点旁（仅左右膝/左右髋四项）
    if overlay.draw_angles and angles:
        for key in _ANGLE_OVERLAY_KEYS:
            v = angles.get(key)
            if v is None:
                continue
            v = float(v)
            if not math.isfinite(v):
                continue
            vertex = ANGLE_DEFS[key][1]   # (近端, 顶点, 远端) 中的顶点
            if not valid[vertex]:
                continue
            x, y = pts[vertex, 0], pts[vertex, 1]
            texts.append((f'{v:.0f}', int(round(x)) + 10,
                          max(2, int(round(y)) - _FONT_PX_INFO - 8),
                          _COLOR_TEXT, _FONT_PX_INFO, (0, 0, 0)))

    # 躯干倾角：带符号值画在颈部点旁
    if overlay.draw_angles and torso_lean is not None:
        v = float(torso_lean)
        if math.isfinite(v) and valid[NECK]:
            x, y = pts[NECK, 0], pts[NECK, 1]
            texts.append((f'{v:+.1f}°', int(round(x)) + 10,
                          max(2, int(round(y)) - _FONT_PX_INFO - 8),
                          _COLOR_LEAN, _FONT_PX_INFO, (0, 0, 0)))


# ---------------- 整段视频渲染 ----------------
def render_analysis_videos(source_path: str | Path,
                           out_full: str | Path,
                           out_skeleton: str | Path,
                           kpts_filtered: np.ndarray,
                           metrics: MetricsResult,
                           events: list[Event],
                           overlay_full: OverlayConfig,
                           overlay_skeleton: OverlayConfig,
                           progress_cb: Callable[[float], None] | None = None,
                           cancel_event=None) -> dict:
    """把姿态分析结果渲染成两个视频（完整叠加版 + 纯骨架版）。

    - 逐帧读取源视频，每帧画两版分别写入 mp4v 中间文件；
    - 输出帧数与 kpts_filtered 行数严格一致：源视频读不尽时用上一帧图像补齐
      （首帧即失败则用黑帧），多余关键点行不丢弃；
    - 渲染结束后用 ffmpeg 转 H.264 并合成原视频音频；转码失败时把 mp4v
      中间文件改名为最终文件并记入 warnings；
    - progress_cb 以 0..1 回调渲染进度；cancel_event 置位时停止、释放资源，
      返回 status='cancelled'。

    返回：{'status': 'completed' | 'cancelled',
           'frames_rendered': int, 'warnings': list[str]}
    """
    warnings: list[str] = []

    kpts = np.asarray(kpts_filtered, dtype=float)
    if kpts.ndim != 3 or kpts.shape[1] != NUM_KEYPOINTS:
        raise ValueError(
            f'kpts_filtered 形状应为 (F,{NUM_KEYPOINTS},3)，实际 {kpts.shape}')
    total = int(kpts.shape[0])

    source = Path(source_path)
    out_full_p, out_skel_p = Path(out_full), Path(out_skeleton)
    tmp_full = out_full_p.with_name(out_full_p.stem + '.render_tmp.mp4')
    tmp_skel = out_skel_p.with_name(out_skel_p.stem + '.render_tmp.mp4')

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f'无法打开源视频: {source}')
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not (fps > 0):
        fps = 30.0
        warnings.append('源视频未报告有效 fps，渲染按 30 fps 处理')
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        cap.release()
        raise RuntimeError('无法读取源视频尺寸')

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    w_full = cv2.VideoWriter(str(tmp_full), fourcc, fps, (width, height))
    w_skel = cv2.VideoWriter(str(tmp_skel), fourcc, fps, (width, height))
    if not (w_full.isOpened() and w_skel.isOpened()):
        cap.release()
        w_full.release()
        w_skel.release()
        raise RuntimeError('无法创建 mp4v 中间视频写入器')

    # 事件按帧索引分组（同一帧可有多个标签）
    events_by_frame: dict[int, list[str]] = {}
    for ev in events or []:
        events_by_frame.setdefault(int(ev.frame_index), []).append(str(ev.type))

    # metrics 各序列的安全访问句柄（防御长度不一致/缺失）
    angles_map = dict(getattr(metrics, 'angles', None) or {})
    torso_seq = getattr(metrics, 'torso_lean', None)
    quality_seq = getattr(metrics, 'pose_quality', None)
    ts_seq = getattr(metrics, 'timestamps_ms', None)
    pelvis_seq = (getattr(metrics, 'trajectories', None) or {}).get('pelvis')

    def value_at(seq, i):
        """取一维序列第 i 个有限值；越界/NaN/缺失返回 None。"""
        if seq is None:
            return None
        try:
            v = float(seq[i])
        except (IndexError, TypeError, ValueError):
            return None
        return v if math.isfinite(v) else None

    def recent_traj(i: int, n: int):
        """取最近 n 帧窗口内的有效骨盆点 (x,y) 列表。"""
        if pelvis_seq is None or n <= 0:
            return None
        lo = max(0, i - int(n) + 1)
        out = []
        try:
            seg = pelvis_seq[lo:i + 1]
        except (IndexError, TypeError):
            return None
        for x, y in seg:
            if math.isfinite(x) and math.isfinite(y):
                out.append((float(x), float(y)))
        return out or None

    rendered = 0      # 已写入的帧数
    read_ok = 0       # 源视频实际读取成功的帧数
    padded = 0        # 读取失败后用上一帧图像补齐的帧数
    last_frame = None  # 最近一次成功读取的原图（补齐用）
    cancelled = False

    try:
        for i in range(total):
            # 取消检查：立即停止渲染（资源在 finally 统一释放）
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

            ok, frame = cap.read()
            if ok:
                read_ok += 1
                last_frame = frame
            else:
                # 读取失败：用上一帧图像补齐，保证输出帧数与关键点严格一致
                padded += 1

            if last_frame is None:
                # 极端情况：首帧即读取失败 → 黑帧兜底
                base = np.zeros((height, width, 3), dtype=np.uint8)
            else:
                base = last_frame

            k = kpts[i]
            frame_angles = {key: value_at(seq, i)
                            for key, seq in angles_map.items()}
            lean = value_at(torso_seq, i)
            quality = value_at(quality_seq, i)
            ts = value_at(ts_seq, i)
            labels = events_by_frame.get(i)

            # 完整叠加版
            img_full = base.copy()
            draw_skeleton_frame(
                img_full, k, overlay_full,
                angles=frame_angles, torso_lean=lean,
                pelvis_traj=(recent_traj(i, overlay_full.trajectory_frames)
                             if overlay_full.draw_trajectory else None),
                event_labels=labels, frame_index=i, timestamp_ms=ts,
                pose_quality=quality)
            w_full.write(img_full)

            # 纯骨架版
            img_skel = base.copy()
            draw_skeleton_frame(
                img_skel, k, overlay_skeleton,
                angles=frame_angles, torso_lean=lean,
                pelvis_traj=(recent_traj(i, overlay_skeleton.trajectory_frames)
                             if overlay_skeleton.draw_trajectory else None),
                event_labels=labels, frame_index=i, timestamp_ms=ts,
                pose_quality=quality)
            w_skel.write(img_skel)

            rendered += 1
            if progress_cb is not None:
                progress_cb(rendered / total)
    finally:
        cap.release()
        w_full.release()
        w_skel.release()

    if cancelled:
        # 清理未完成的中间文件
        for p in (tmp_full, tmp_skel):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        return {'status': 'cancelled', 'frames_rendered': rendered,
                'warnings': warnings}

    if padded:
        if read_ok == 0:
            warnings.append(
                f'源视频无法读取任何帧，已用黑帧渲染全部 {total} 帧'
                f'（输出帧数与关键点保持严格一致）')
        else:
            warnings.append(
                f'源视频实际可读帧数({read_ok})少于关键点行数({total})，'
                f'末尾 {padded} 帧已用上一帧图像补齐'
                f'（输出帧数与关键点保持严格一致）')

    # mp4v 中间文件 → H.264，并合成源视频音频
    for tmp, final in ((tmp_full, out_full_p), (tmp_skel, out_skel_p)):
        final.parent.mkdir(parents=True, exist_ok=True)
        try:
            ok = transcode_h264(tmp, final, audio_source=source)
        except Exception as e:   # ffmpeg 不可用等异常：降级保留 mp4v
            ok = False
            warnings.append(f'H.264 转码异常: {e}')
        if ok:
            tmp.unlink(missing_ok=True)
        else:
            os.replace(tmp, final)
            warnings.append(
                f'H.264 转码失败，已保留 mp4v 编码中间文件: {final.name}')

    return {'status': 'completed', 'frames_rendered': rendered,
            'warnings': warnings}
