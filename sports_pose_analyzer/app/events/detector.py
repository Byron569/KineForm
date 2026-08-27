"""关键事件检测（纯 numpy/scipy，顶层不 import torch/mmpose/cv2）。

内置检测器（均通过 register_event_detector 注册进 EVENT_DETECTORS，
detect_events 按注册顺序依次调用并汇总）：
- joint_angle_minima        左/右膝关节角显著局部极小 + 全局最小帧
- torso_lean_maxima         |躯干倾角| 局部极大 + 全局最大帧
- pelvis_height_extrema     骨盆高度（y 像素）局部极高/极低 + 全局极值帧
- max_joint_angular_velocity 各关节角速度序列的全局最大帧
- pose_lost_boundaries      姿态丢失/恢复的边界帧

通用约定：
- confidence 取该帧 metrics.pose_quality 并截断到 [0,1]（NaN → 0）；
- timestamp_ms 取 metrics.timestamps_ms[i]，frame_index 取
  metrics.frame_indices[i]；
- 角度事件 unit='degree'，骨盆高度事件 unit='px'，
  角速度事件 unit='deg/s'，姿态丢失事件 unit='frame'；
- 长度 < 3 或全 NaN 的序列安全跳过（不产生事件）。
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from scipy.signal import find_peaks

from ..common.data_models import Event, MetricsResult

__all__ = [
    'EVENT_DETECTORS',
    'ACTION_TEMPLATES',
    'register_event_detector',
    'detect_events',
]

# 可扩展事件检测器注册表：名称 -> 检测器 (metrics, statuses) -> list[Event]
EVENT_DETECTORS: dict[str, Callable[..., list[Event]]] = {}

ACTION_TEMPLATES: dict = {}
"""动作模板注册表（预留空接口）。

未来深蹲/跳跃等专用动作规则的建议接入方式：
1. 为动作定义模板 dict（动作名、参与的关节角/轨迹序列、相位划分与
   阈值条件、事件类型命名），注册到本表；
2. 用 register_event_detector 注册一个基于模板的检测器：遍历本表，
   把各相位条件转换为 Event 序列（例如深蹲 = 左右膝角先后跌破
   下蹲阈值、再回升越过起身阈值，产出蹲姿最深帧等事件）；
3. detect_events 会自动调用 EVENT_DETECTORS 中的全部检测器，
   新增动作无需修改 detect_events 或既有检测器。
"""


def register_event_detector(name: str) -> Callable:
    """装饰器：把事件检测器函数注册进 EVENT_DETECTORS。

    检测器签名：detect(metrics: MetricsResult, statuses: list[str])
    -> list[Event]。detect_events 会依次调用全部已注册检测器并汇总，
    因此第三方/未来动作规则只需注册即可生效。
    """

    def decorator(fn: Callable) -> Callable:
        EVENT_DETECTORS[name] = fn
        return fn

    return decorator


# ---------------- 内部工具 ----------------
def _finite_std(series: np.ndarray) -> float | None:
    """有限样本的总体标准差（等价 nanstd）；无有限样本返回 None。"""
    finite = series[np.isfinite(series)]
    if finite.size == 0:
        return None
    return float(np.std(finite))


def _confidence(metrics: MetricsResult, i: int) -> float:
    """第 i 帧事件置信度：pose_quality 截断到 [0,1]，NaN → 0。"""
    q = float(metrics.pose_quality[i])
    if not np.isfinite(q):
        return 0.0
    return min(max(q, 0.0), 1.0)


def _extrema_events(metrics: MetricsResult, series, event_type: str,
                    unit: str, prom_thr: float, *, find_max: bool,
                    max_peaks: int = 10) -> list[Event]:
    """局部极值 + 全局极值事件（峰值检测通用实现）。

    find_max=True 找局部极大（否则找局部极小）；显著极值按 prominence
    降序最多 max_peaks 个，且必含全局极值帧（若不在其中则追加）。
    事件 value 取「被分析序列」在该帧的原始值（如倾角取 |torso_lean|，
    高度事件取 pelvis y 像素值）。序列长度 < 3 或全 NaN 时不检测。
    """
    events: list[Event] = []
    series = np.asarray(series, dtype=float)
    if series.shape[0] < 3 or not np.isfinite(series).any():
        return events
    # 找极大用原序列，找极小用取负后的序列（scipy 只找峰）
    target = series if find_max else -series
    peaks, props = find_peaks(target, prominence=prom_thr)
    frames: list[int] = []
    if peaks.size:
        order = np.argsort(props['prominences'])[::-1][:max_peaks]
        frames = sorted(int(i) for i in peaks[order])
    g = int(np.nanargmax(target))            # 全局极值帧必含
    if g not in frames:
        frames.append(g)
    for i in frames:
        events.append(Event(
            type=event_type,
            frame_index=int(metrics.frame_indices[i]),
            timestamp_ms=float(metrics.timestamps_ms[i]),
            value=float(series[i]),
            unit=unit,
            confidence=_confidence(metrics, i)))
    return events


# ---------------- 内置检测器 ----------------
@register_event_detector('joint_angle_minima')
def _detect_joint_angle_minima(metrics: MetricsResult,
                               statuses: list[str]) -> list[Event]:
    """左/右膝关节角的显著局部极小 + 全局最小。

    prominence ≥ max(5.0°, 0.25×序列 std)，按 prominence 降序最多
    10 个，且必含全局 nanargmin 帧。
    """
    events: list[Event] = []
    for key in ('left_knee', 'right_knee'):
        if key not in metrics.angles:
            continue
        series = np.asarray(metrics.angles[key], dtype=float)
        std = _finite_std(series)
        if std is None:
            continue                          # 全 NaN：安全跳过
        prom_thr = max(5.0, 0.25 * std)
        events.extend(_extrema_events(
            metrics, series, f'min_{key}_angle', 'degree', prom_thr,
            find_max=False))
    return events


@register_event_detector('torso_lean_maxima')
def _detect_torso_lean_maxima(metrics: MetricsResult,
                              statuses: list[str]) -> list[Event]:
    """|躯干倾角| 的显著局部极大 + 全局最大。

    prominence ≥ max(5.0°, 0.25×序列 std)，最多 10 个 + 全局；
    事件 value 取 |torso_lean|（倾角幅值）。
    """
    series = np.abs(np.asarray(metrics.torso_lean, dtype=float))
    std = _finite_std(series)
    if std is None:
        return []
    prom_thr = max(5.0, 0.25 * std)
    return _extrema_events(metrics, series, 'max_torso_lean', 'degree',
                           prom_thr, find_max=True)


@register_event_detector('pelvis_height_extrema')
def _detect_pelvis_height_extrema(metrics: MetricsResult,
                                  statuses: list[str]) -> list[Event]:
    """骨盆高度（pelvis y 像素，越小越高）的局部极值 + 全局极值。

    max_pelvis_height 对应 y 局部极小（最高点），min_pelvis_height
    对应 y 局部极大（最低点）；prominence ≥ 0.25×序列 std，各最多
    10 个 + 全局。
    """
    events: list[Event] = []
    pelvis = np.asarray(metrics.trajectories['pelvis'], dtype=float)
    y = pelvis[:, 1]
    std = _finite_std(y)
    if std is None:
        return events
    prom_thr = 0.25 * std
    # y 局部极小 = 骨盆最高
    events.extend(_extrema_events(metrics, y, 'max_pelvis_height', 'px',
                                  prom_thr, find_max=False))
    # y 局部极大 = 骨盆最低
    events.extend(_extrema_events(metrics, y, 'min_pelvis_height', 'px',
                                  prom_thr, find_max=True))
    return events


@register_event_detector('max_joint_angular_velocity')
def _detect_max_joint_angular_velocity(metrics: MetricsResult,
                                       statuses: list[str]) -> list[Event]:
    """8 个关节角速度序列各自的全局最大帧事件（unit='deg/s'）。

    同一帧上多关节同时取到全局最大时，由 detect_events 末尾去重
    （同 type+frame 只留一个）。
    """
    events: list[Event] = []
    for series in metrics.angular_velocity.values():
        s = np.asarray(series, dtype=float)
        if s.shape[0] < 3 or not np.isfinite(s).any():
            continue
        i = int(np.nanargmax(s))
        events.append(Event(
            type='max_joint_angular_velocity',
            frame_index=int(metrics.frame_indices[i]),
            timestamp_ms=float(metrics.timestamps_ms[i]),
            value=float(s[i]),
            unit='deg/s',
            confidence=_confidence(metrics, i)))
    return events


@register_event_detector('pose_lost_boundaries')
def _detect_pose_lost_boundaries(metrics: MetricsResult,
                                 statuses: list[str]) -> list[Event]:
    """姿态丢失/恢复边界帧。

    statuses[i-1]=='ok' 且 statuses[i]!='ok' → 第 i 帧为 pose_lost_start；
    statuses[i-1]!='ok' 且 statuses[i]=='ok' → 第 i 帧为 pose_lost_end；
    value=0.0，unit='frame'。
    """
    events: list[Event] = []
    if statuses is None:
        return events
    n = min(len(statuses), len(metrics.frame_indices))
    for i in range(1, n):
        prev_ok = statuses[i - 1] == 'ok'
        cur_ok = statuses[i] == 'ok'
        if prev_ok and not cur_ok:
            etype = 'pose_lost_start'
        elif (not prev_ok) and cur_ok:
            etype = 'pose_lost_end'
        else:
            continue
        events.append(Event(
            type=etype,
            frame_index=int(metrics.frame_indices[i]),
            timestamp_ms=float(metrics.timestamps_ms[i]),
            value=0.0,
            unit='frame',
            confidence=_confidence(metrics, i)))
    return events


# ---------------- 对外入口 ----------------
def detect_events(metrics: MetricsResult,
                  statuses: list[str]) -> list[Event]:
    """运行全部已注册检测器，返回按 frame_index 升序的事件列表。

    末尾去重：同 (type, frame_index) 只保留一个（保留先出现者）。
    """
    events: list[Event] = []
    for fn in list(EVENT_DETECTORS.values()):
        events.extend(fn(metrics, statuses))
    # 按帧号升序（稳定排序，同帧内保持检测器产出顺序）
    events.sort(key=lambda e: e.frame_index)
    # 末尾去重：同 (type, frame_index) 只留一个
    seen: set[tuple[str, int]] = set()
    dedup: list[Event] = []
    for e in events:
        key = (e.type, e.frame_index)
        if key not in seen:
            seen.add(key)
            dedup.append(e)
    return dedup
