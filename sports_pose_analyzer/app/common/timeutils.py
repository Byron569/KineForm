"""帧号 ↔ 时间戳映射（CFR 视频专用）。"""
from __future__ import annotations

import numpy as np


def frame_to_timestamp_ms(frame_index: int, fps: float) -> float:
    """CFR 下第 frame_index 帧的时间戳（毫秒）。

    帧起点约定：第 0 帧起始时刻为 0ms，第 N 帧起始时刻 = N / fps。
    """
    if fps <= 0:
        raise ValueError(f'fps 必须为正数，收到 {fps}')
    if frame_index < 0:
        raise ValueError(f'frame_index 不能为负，收到 {frame_index}')
    return frame_index / fps * 1000.0


def timestamp_ms_to_frame(timestamp_ms: float, fps: float) -> int:
    """时间戳（毫秒）→ 帧号（向下取整到该时刻正在显示的帧）。"""
    if fps <= 0:
        raise ValueError(f'fps 必须为正数，收到 {fps}')
    if timestamp_ms < 0:
        raise ValueError(f'timestamp_ms 不能为负，收到 {timestamp_ms}')
    return int(timestamp_ms * fps / 1000.0)


def all_timestamps_ms(frame_count: int, fps: float) -> np.ndarray:
    """(F,) 全部帧时间戳数组。"""
    return np.arange(frame_count, dtype=np.float64) / fps * 1000.0
