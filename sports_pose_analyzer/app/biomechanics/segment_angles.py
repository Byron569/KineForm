"""二维节段角序列（纯 numpy，顶层不 import torch/mmpose/cv2）。

角度约定（图像坐标，y 轴向下；+x 为前进方向）：
- 大腿角 thigh：髋→膝向量相对水平方向的带符号角（度），
  膝在髋前上方为正（右向跑时）。Mattes 2021 最大抬腿参考 ≈ 21°。
- 小腿角 shank：膝→踝向量相对竖直向下方向的带符号角（度），
  踝在膝前方为正（前倾）。800m 世界级初触地参考 ≈ 4–7°。
- 肩角 shoulder（Hanley 2020 解剖约定）：躯干—上臂夹角，
  站立手臂下垂 = 0°，前摆（右向跑时指向 +x）为正，后摆为负。
  世界级马拉松参考：IC 男 ≈ −47° / 女 ≈ −50°，TO ≈ +27°。
  躯干参考取同侧髋−肩向量（躯干倾角自动补偿）。

无效点（NaN）→ NaN；零向量（两点重合）→ NaN。
左向跑视频：本模块按图像坐标输出原始角，方向翻转由
app.events.gait.gait_step_features 按行进方向处理
（thigh: 180°−θ 再wrap到(-180,180]；shank/shoulder: −θ）。
"""
from __future__ import annotations

import numpy as np

from ..common import halpe26

__all__ = [
    'thigh_angle_series',
    'shank_angle_series',
    'shoulder_angle_series',
    'segment_angle_series',
]


def _as_kpts(kpts) -> np.ndarray:
    """校验并转换为 (F, 26, 3) float 数组。"""
    arr = np.asarray(kpts, dtype=float)
    if (arr.ndim != 3 or arr.shape[1] != halpe26.NUM_KEYPOINTS
            or arr.shape[2] != 3):
        raise ValueError(
            f'关键点数组 shape 应为 (F, {halpe26.NUM_KEYPOINTS}, 3)，'
            f'收到 {arr.shape}')
    return arr


def _angle_series(a: np.ndarray, b: np.ndarray, mode: str) -> np.ndarray:
    """a→b 向量的带符号角序列（度）。mode='thigh' 相对水平（数学
    y 向上），mode='shank' 相对竖直向下。NaN/零向量 → NaN。"""
    dx = b[:, 0] - a[:, 0]
    dy = b[:, 1] - a[:, 1]
    with np.errstate(invalid='ignore'):
        if mode == 'thigh':
            ang = np.degrees(np.arctan2(-dy, dx))
        else:  # shank
            ang = np.degrees(np.arctan2(dx, dy))
    degenerate = (~np.isfinite(dx)) | (~np.isfinite(dy)) \
        | ((dx == 0.0) & (dy == 0.0))
    return np.where(degenerate, np.nan, ang)


def thigh_angle_series(kpts) -> dict[str, np.ndarray]:
    """左/右大腿角序列 dict：'left_thigh'/'right_thigh' → (F,) 度。"""
    arr = _as_kpts(kpts)
    return {
        'left_thigh': _angle_series(
            arr[:, halpe26.LEFT_HIP, :2], arr[:, halpe26.LEFT_KNEE, :2],
            'thigh'),
        'right_thigh': _angle_series(
            arr[:, halpe26.RIGHT_HIP, :2], arr[:, halpe26.RIGHT_KNEE, :2],
            'thigh'),
    }


def shank_angle_series(kpts) -> dict[str, np.ndarray]:
    """左/右小腿角序列 dict：'left_shank'/'right_shank' → (F,) 度。"""
    arr = _as_kpts(kpts)
    return {
        'left_shank': _angle_series(
            arr[:, halpe26.LEFT_KNEE, :2], arr[:, halpe26.LEFT_ANKLE, :2],
            'shank'),
        'right_shank': _angle_series(
            arr[:, halpe26.RIGHT_KNEE, :2], arr[:, halpe26.RIGHT_ANKLE, :2],
            'shank'),
    }


def shoulder_angle_series(kpts) -> dict[str, np.ndarray]:
    """左/右肩角序列（Hanley 2020 解剖约定）：

    肩点处躯干向量（同侧髋−肩，向下）与上臂向量（肩→肘）的带符号
    夹角（度）：手臂下垂 = 0°，前摆（图像 +x 侧）为正，后摆为负，
    前平举 = +90°。躯干倾斜由同侧髋−肩参考自动补偿。
    无效点 / 零向量 → NaN。
    """
    arr = _as_kpts(kpts)
    out: dict[str, np.ndarray] = {}
    for side, sh, hp, el in (
            ('left', halpe26.LEFT_SHOULDER, halpe26.LEFT_HIP,
             halpe26.LEFT_ELBOW),
            ('right', halpe26.RIGHT_SHOULDER, halpe26.RIGHT_HIP,
             halpe26.RIGHT_ELBOW)):
        trunk = arr[:, hp, :2] - arr[:, sh, :2]     # 肩→髋（躯干向下）
        arm = arr[:, el, :2] - arr[:, sh, :2]       # 肩→肘（上臂）
        cross = trunk[:, 0] * arm[:, 1] - trunk[:, 1] * arm[:, 0]
        dot = trunk[:, 0] * arm[:, 0] + trunk[:, 1] * arm[:, 1]
        with np.errstate(invalid='ignore'):
            ang = -np.degrees(np.arctan2(cross, dot))
        n_t = np.hypot(trunk[:, 0], trunk[:, 1])
        n_a = np.hypot(arm[:, 0], arm[:, 1])
        bad = ((~np.isfinite(cross)) | (~np.isfinite(dot))
               | (n_t <= 0.0) | (n_a <= 0.0))
        out[f'{side}_shoulder'] = np.where(bad, np.nan, ang)
    return out


def segment_angle_series(kpts) -> dict[str, np.ndarray]:
    """全部 6 条节段角序列（thigh + shank + shoulder 合并）。"""
    return {**thigh_angle_series(kpts),
            **shank_angle_series(kpts),
            **shoulder_angle_series(kpts)}
