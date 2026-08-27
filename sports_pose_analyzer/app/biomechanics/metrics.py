"""二维运动学指标（纯 numpy，顶层不 import torch/mmpose/cv2）。

全部为图像坐标系下的未标定指标（像素 / 度 / 秒）：
- 关节角（8 个，定义见 halpe26.ANGLE_DEFS）与角速度；
- 躯干倾角（NECK→骨盆连线相对图像竖直方向，带符号）；
- pelvis/head/左右脚跟轨迹与关键点速度；
- 左右对称性汇总标量。

数据约定：关键点数组 shape = (F, 26, 3)，通道 (x, y, score)；
无效点 x/y = NaN；一切时间序列的无效样本用 NaN 表示。
"""
from __future__ import annotations

import numpy as np

from ..common import halpe26
from ..common.data_models import MetricsResult
from .segment_angles import segment_angle_series

__all__ = [
    'three_point_angle',
    'angle_series',
    'torso_lean_series',
    'trajectories',
    'keypoint_speeds',
    'angular_velocity',
    'symmetry_summary',
    'compute_metrics',
]


def _as_kpts(kpts) -> np.ndarray:
    """校验并转换为 (F, 26, 3) float 数组（只读用途，不复制）。"""
    arr = np.asarray(kpts, dtype=float)
    if (arr.ndim != 3 or arr.shape[1] != halpe26.NUM_KEYPOINTS
            or arr.shape[2] != 3):
        raise ValueError(
            f'关键点数组 shape 应为 (F, {halpe26.NUM_KEYPOINTS}, 3)，'
            f'收到 {arr.shape}')
    return arr


def three_point_angle(a, b, c):
    """以 b 为顶点的三点夹角（度，向量法，范围 [0, 180]）。

    a/b/c 可为单点 (2,) 或 (3,)（自动取前两通道 x/y），也可为等长的
    (F,2)/(F,3) 数组（逐帧向量化，返回 (F,) 数组）。
    任何输入含 NaN、或顶点与某个端点重合（零向量）→ NaN。
    """
    a = np.asarray(a, dtype=float)[..., :2]
    b = np.asarray(b, dtype=float)[..., :2]
    c = np.asarray(c, dtype=float)[..., :2]
    u = a - b                           # 顶点 → 端点 a 的向量
    v = c - b                           # 顶点 → 端点 c 的向量
    nu = np.linalg.norm(u, axis=-1)
    nv = np.linalg.norm(v, axis=-1)
    dot = np.sum(u * v, axis=-1)
    cross = u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]
    # atan2(|叉积|, 点积) 在 [0, 180] 内数值稳定（避免 acos 的病态区间）
    with np.errstate(invalid='ignore'):
        ang = np.degrees(np.arctan2(np.abs(cross), dot))
    degenerate = ((~np.isfinite(nu)) | (~np.isfinite(nv))
                  | (nu <= 0.0) | (nv <= 0.0))
    ang = np.where(degenerate, np.nan, ang)
    return float(ang) if np.ndim(ang) == 0 else ang


def angle_series(kpts, angle_defs=None) -> dict[str, np.ndarray]:
    """8 个关节角的逐帧序列 dict[str, (F,)]（度）。

    默认使用 halpe26.ANGLE_DEFS；任一构成点无效（NaN）→ 该帧该角为 NaN。
    """
    arr = _as_kpts(kpts)
    defs = halpe26.ANGLE_DEFS if angle_defs is None else angle_defs
    return {name: three_point_angle(arr[:, ia], arr[:, ib], arr[:, ic])
            for name, (ia, ib, ic) in defs.items()}


def _pelvis_series(arr: np.ndarray) -> np.ndarray:
    """骨盆点序列 (F,2)：优先 HIP 点，无效时取左右髋中点，再无效 → NaN 行。"""
    n_frames = arr.shape[0]
    hip = arr[:, halpe26.HIP, :2]
    lhip = arr[:, halpe26.LEFT_HIP, :2]
    rhip = arr[:, halpe26.RIGHT_HIP, :2]
    hip_ok = np.isfinite(hip).all(axis=1)
    both_ok = np.isfinite(lhip).all(axis=1) & np.isfinite(rhip).all(axis=1)
    pelvis = np.full((n_frames, 2), np.nan)
    pelvis[hip_ok] = hip[hip_ok]
    use_mid = (~hip_ok) & both_ok        # 仅 HIP 无效且双髋均有效时取中点
    pelvis[use_mid] = (lhip[use_mid] + rhip[use_mid]) / 2.0
    return pelvis


def torso_lean_series(kpts) -> np.ndarray:
    """躯干倾角逐帧序列（度，带符号）。

    NECK → 骨盆（HIP 点，无效时左右髋中点，再无效 → NaN）连线相对
    图像竖直方向的角度，atan2(dx, dy)；正值 = 骨盆在颈部的图像右侧，
    负值 = 左侧；任一端无效的帧为 NaN。
    """
    arr = _as_kpts(kpts)
    neck = arr[:, halpe26.NECK, :2]
    d = _pelvis_series(arr) - neck       # (F, 2)：NECK → 骨盆向量
    with np.errstate(invalid='ignore'):
        lean = np.degrees(np.arctan2(d[:, 0], d[:, 1]))
    return lean


def trajectories(kpts) -> dict[str, np.ndarray]:
    """关键轨迹点 dict：pelvis/head/left_heel/right_heel → (F,2) 像素坐标。

    pelvis 取 HIP 点（无效时左右髋中点，再无效 → NaN 行）；
    head 取 HEAD 点；左右脚跟取 LEFT_HEEL/RIGHT_HEEL 点；
    无效帧为 NaN 行（不修改输入数组）。
    """
    arr = _as_kpts(kpts)
    return {
        'pelvis': _pelvis_series(arr),
        'head': arr[:, halpe26.HEAD, :2].copy(),
        'left_heel': arr[:, halpe26.LEFT_HEEL, :2].copy(),
        'right_heel': arr[:, halpe26.RIGHT_HEEL, :2].copy(),
    }


def keypoint_speeds(kpts, fps) -> np.ndarray:
    """关键点速度 (F, 26)，单位 px/s。

    内部帧用中心差分 (p[t+1]-p[t-1])/(2Δt)，首末帧用单侧差分；
    差分涉及的任一帧无效、或该帧本身无效 → NaN。
    """
    if fps <= 0:
        raise ValueError(f'fps 必须为正数，收到 {fps}')
    arr = _as_kpts(kpts)
    n_frames, n_kpts = arr.shape[0], arr.shape[1]
    x, y = arr[:, :, 0], arr[:, :, 1]
    dt = 1.0 / fps
    vx = np.full((n_frames, n_kpts), np.nan)
    vy = np.full((n_frames, n_kpts), np.nan)
    if n_frames >= 2:
        vx[1:-1] = (x[2:] - x[:-2]) / (2.0 * dt)     # 中心差分
        vy[1:-1] = (y[2:] - y[:-2]) / (2.0 * dt)
        vx[0] = (x[1] - x[0]) / dt                   # 边界单侧差分
        vy[0] = (y[1] - y[0]) / dt
        vx[-1] = (x[-1] - x[-2]) / dt
        vy[-1] = (y[-1] - y[-2]) / dt
    speed = np.hypot(vx, vy)
    # 中心差分公式不含 p[t]，该帧本身无效时需显式置 NaN
    invalid = ~np.isfinite(x) | ~np.isfinite(y)
    speed[invalid] = np.nan
    return speed


def angular_velocity(angles_dict, fps) -> dict[str, np.ndarray]:
    """关节角速度 dict（与输入同 keys），单位 deg/s。

    中心差分，边界单侧差分；角度无效的帧 → NaN。
    """
    if fps <= 0:
        raise ValueError(f'fps 必须为正数，收到 {fps}')
    dt = 1.0 / fps
    out: dict[str, np.ndarray] = {}
    for key, s in angles_dict.items():
        s = np.asarray(s, dtype=float)
        n = s.shape[0]
        v = np.full(n, np.nan)
        if n >= 2:
            v[1:-1] = (s[2:] - s[:-2]) / (2.0 * dt)  # 中心差分
            v[0] = (s[1] - s[0]) / dt                # 边界单侧差分
            v[-1] = (s[-1] - s[-2]) / dt
        v[~np.isfinite(s)] = np.nan                  # 无效角度帧
        out[key] = v
    return out


# 对称性统计的左右关节对（名称 → (左键, 右键)）
_SYM_PAIRS: tuple[tuple[str, tuple[str, str]], ...] = (
    ('knee', ('left_knee', 'right_knee')),
    ('hip', ('left_hip', 'right_hip')),
    ('ankle', ('left_ankle', 'right_ankle')),
    ('elbow', ('left_elbow', 'right_elbow')),
)


def symmetry_summary(angles) -> dict[str, float]:
    """左右对称性汇总（标量 dict）。

    knee/hip/ankle/elbow 四对各自统计「左右同时有效帧的 |左-右| 均值」，
    键形如 'knee_mean_abs_diff_deg'（无同时有效帧时该键为 NaN）；
    'overall_mean_abs_diff_deg' 为计入的对的均值——无同时有效帧的对
    不计入 overall；全部无同时有效帧时 overall 为 NaN。
    """
    out: dict[str, float] = {}
    pair_means: list[float] = []
    for joint, (lk, rk) in _SYM_PAIRS:
        mean = float('nan')
        if lk in angles and rk in angles:
            left = np.asarray(angles[lk], dtype=float)
            right = np.asarray(angles[rk], dtype=float)
            both = np.isfinite(left) & np.isfinite(right)
            if both.any():
                mean = float(np.mean(np.abs(left[both] - right[both])))
                pair_means.append(mean)
        out[f'{joint}_mean_abs_diff_deg'] = mean
    out['overall_mean_abs_diff_deg'] = (
        float(np.mean(pair_means)) if pair_means else float('nan'))
    return out


def compute_metrics(kpts_filtered, fps, frame_indices, timestamps_ms,
                    pose_quality, valid_ratio,
                    missing_ratio) -> MetricsResult:
    """组装 MetricsResult（填全所有字段）。

    - angles / angular_velocity / torso_lean / trajectories /
      keypoint_speeds 由过滤后关键点计算；
    - pelvis_speed 取 keypoint_speeds 的 HIP（骨盆）关键点速度列；
    - symmetry_index = symmetry_summary(angles)。
    """
    arr = _as_kpts(kpts_filtered)
    angles = angle_series(arr)
    speeds = keypoint_speeds(arr, fps)
    return MetricsResult(
        fps=float(fps),
        frame_indices=np.asarray(frame_indices, dtype=np.int64),
        timestamps_ms=np.asarray(timestamps_ms, dtype=float),
        angles=angles,
        angular_velocity=angular_velocity(angles, fps),
        torso_lean=torso_lean_series(arr),
        trajectories=trajectories(arr),
        keypoint_speeds=speeds,
        pelvis_speed=speeds[:, halpe26.HIP].copy(),
        pose_quality=np.asarray(pose_quality, dtype=float),
        valid_ratio=np.asarray(valid_ratio, dtype=float),
        missing_ratio=np.asarray(missing_ratio, dtype=float),
        symmetry_index=symmetry_summary(angles),
        segment_angles=segment_angle_series(arr),
    )
