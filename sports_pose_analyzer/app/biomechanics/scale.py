"""身体尺度估计、像素归一化与跑速估计（纯 numpy）。

- body_height_px：头顶(HEAD) → 双踝中点的像素距离中位数
  （复用 halpe26.body_height_px），用于把距离类指标化为无量纲。
- leg_length_px：每帧左右髋→踝距离均值的有限帧中位数
  （Miyashiro 腿长 = 大腿+小腿 的像素近似；屈膝帧会低估，
  中位数缓解但不消除，文档已注明）。
- run_speed_estimate：骨盆 x 对时间最小二乘斜率 → px/s
  （假设过地匀速跑；跑步机原地跑 ≈ 0）；提供真实身高时
  换算 m/px 与 m/s。

文献依据：研究报告 1/3——距离与速度指标必须按身体尺度归一化
（CM-foot 距离、步长等），否则不同身高运动员不可直接比较。
"""
from __future__ import annotations

import numpy as np

from ..common import halpe26

__all__ = ['body_scale', 'run_speed_estimate']

_MIN_VALID_FRAMES = 3


def body_scale(kpts) -> dict:
    """估计身体尺度 dict：{body_height_px, leg_length_px}（无效 → None）。"""
    arr = np.asarray(kpts, dtype=float)
    if arr.ndim != 3 or arr.shape[1] != halpe26.NUM_KEYPOINTS:
        return {'body_height_px': None, 'leg_length_px': None}

    height = halpe26.body_height_px(arr)

    # 腿长：左右髋→踝距离各自取有限帧中位数，再对可用侧取均值
    # （单侧遮挡时仍可估计；Miyashiro 腿长 = 大腿+小腿的像素近似）
    sides = []
    for hip_i, ank_i in ((halpe26.LEFT_HIP, halpe26.LEFT_ANKLE),
                         (halpe26.RIGHT_HIP, halpe26.RIGHT_ANKLE)):
        d = np.linalg.norm(
            arr[:, ank_i, :2] - arr[:, hip_i, :2], axis=1)
        d = d[np.isfinite(d)]
        if d.size >= _MIN_VALID_FRAMES:
            sides.append(float(np.median(d)))
    leg = float(np.mean(sides)) if sides else None

    return {'body_height_px': height, 'leg_length_px': leg}


def run_speed_estimate(pelvis_x, timestamps_ms, *,
                       body_height_px: float | None = None,
                       height_m: float | None = None) -> dict | None:
    """骨盆水平速度估计（最小二乘斜率）。

    返回 {speed_px_s[, m_per_px, speed_mps]}；有效样本 < 3 → None。
    假设运动员过地匀速通过画面；跑步机场景斜率 ≈ 0。
    """
    x = np.asarray(pelvis_x, dtype=float)
    t = np.asarray(timestamps_ms, dtype=float)
    if x.shape != t.shape:
        raise ValueError('pelvis_x 与 timestamps_ms 形状不一致')
    mask = np.isfinite(x) & np.isfinite(t)
    x, t = x[mask], t[mask]
    if x.size < _MIN_VALID_FRAMES:
        return None
    if t.max() == t.min():
        return None
    slope_px_s = float(np.polyfit(t, x, 1)[0]) * 1000.0  # ms → s
    out = {'speed_px_s': round(slope_px_s, 2)}
    if height_m and body_height_px and body_height_px > 0:
        m_per_px = float(height_m) / float(body_height_px)
        out['m_per_px'] = round(m_per_px, 6)
        out['speed_mps'] = round(slope_px_s * m_per_px, 3)
    return out
