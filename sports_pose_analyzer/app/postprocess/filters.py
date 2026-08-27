"""姿态后处理：无效点标记、跳点剔除、缺口插值与 One Euro 滤波。

纯 numpy 数学模块（顶层不 import torch/mmpose/cv2），无 GPU 亦可测试。
数据约定：关键点数组 shape = (F, 26, 3)，通道 (x, y, score)；
无效关键点 x/y = NaN（score 保留模型原始输出值）。

流水线编排见 postprocess()：
    mark_invalid → detect_outliers → interpolate_gaps → one_euro_filter
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from ..common import halpe26
from ..config.defaults import Thresholds

__all__ = [
    'mark_invalid',
    'interpolate_gaps',
    'one_euro_filter',
    'detect_outliers',
    'postprocess',
    'compute_pose_quality',
]


def _to_kpts(raw) -> np.ndarray:
    """转换为 (F, 26, 3) float 数组（始终返回新副本，不修改输入）。"""
    arr = np.array(raw, dtype=float)
    if (arr.ndim != 3 or arr.shape[1] != halpe26.NUM_KEYPOINTS
            or arr.shape[2] != 3):
        raise ValueError(
            f'关键点数组 shape 应为 (F, {halpe26.NUM_KEYPOINTS}, 3)，'
            f'收到 {arr.shape}')
    return arr


def mark_invalid(raw, score_thr) -> np.ndarray:
    """低分关键点置无效。

    score < score_thr 的点 x/y 置 NaN（score 保留原值）；
    score 恰好等于阈值（== score_thr）的点视为有效，保留原坐标。
    返回副本，不修改输入。
    """
    arr = _to_kpts(raw)
    low = arr[:, :, 2] < score_thr          # 低分掩码 (F, 26)
    arr[low, 0] = np.nan
    arr[low, 1] = np.nan
    return arr


def interpolate_gaps(arr, max_gap) -> np.ndarray:
    """逐关键点对 x、y 独立线性插值填补短缺口。

    只填补「两侧都有有效样本且连续缺失长度 ≤ max_gap」的缺口；
    更长的缺口以及触及首/尾的缺口（单侧无有效样本）保持 NaN。
    score 通道原样保留，不做任何修改。
    """
    out = _to_kpts(arr)
    n_frames, n_kpts = out.shape[0], out.shape[1]
    for k in range(n_kpts):
        for c in (0, 1):                    # x / y 两个通道独立处理
            s = out[:, k, c]                # 基本切片 → 视图，可直接写回 out
            isnan = ~np.isfinite(s)
            if not isnan.any():
                continue
            # 定位连续 NaN 游程 [st, en]（闭区间）
            diff = np.diff(np.concatenate(([0], isnan.astype(np.int8), [0])))
            starts = np.flatnonzero(diff == 1)
            ends = np.flatnonzero(diff == -1) - 1
            for st, en in zip(starts.tolist(), ends.tolist()):
                if st == 0 or en == n_frames - 1:
                    continue                # 首尾缺口：单侧无有效样本，不填
                if en - st + 1 > max_gap:
                    continue                # 缺口过长，不填
                left, right = s[st - 1], s[en + 1]
                if not (np.isfinite(left) and np.isfinite(right)):
                    continue
                # 线性插值：权重 = 到左侧样本的帧距 / 缺口总跨距
                gap = en - st + 2           # 左右有效样本之间的帧距
                w = np.arange(1, gap, dtype=float) / gap
                s[st:en + 1] = left + (right - left) * w
    return out


class _OneEuroChannel:
    """单个标量通道的经典 One Euro Filter（自适应一阶低通）。

    参考 Casiez et al., CHI 2012。参数含义：
    - min_cutoff：静止时的截止频率（越小越平滑）；
    - beta：速度自适应系数（越大对快速运动跟随越好）；
    - d_cutoff：导数低通的截止频率。
    """

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self._x_hat: Optional[float] = None    # 上一次滤波输出
        self._dx_hat = 0.0                     # 上一次滤波后的导数估计
        self._t_prev: Optional[float] = None   # 上一次有效样本时刻（秒）

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        """一阶低通的离散化系数 alpha = 1 / (1 + tau/dt)。"""
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        # 首个样本直接通过（不滤波），导数初始化为 0
        if self._x_hat is None:
            self._x_hat = x
            self._dx_hat = 0.0
            self._t_prev = t
            return x
        dt = t - self._t_prev
        if dt <= 0.0:
            dt = 1e-9                          # 防御：同帧重复样本
        # ① 估计导数并对其低通
        dx = (x - self._x_hat) / dt
        self._dx_hat += self._alpha(self.d_cutoff, dt) * (dx - self._dx_hat)
        # ② 按导数幅值自适应地放宽截止频率（运动越快越不平滑）
        cutoff = self.min_cutoff + self.beta * abs(self._dx_hat)
        # ③ 对位置做低通滤波
        self._x_hat += self._alpha(cutoff, dt) * (x - self._x_hat)
        self._t_prev = t
        return self._x_hat


def one_euro_filter(arr, fps, min_cutoff=1.5, beta=0.10,
                    d_cutoff=1.0) -> np.ndarray:
    """对每个关键点 x/y 各维护一个 One Euro Filter 实例按时间滤波。

    - 仅在有效样本上更新滤波器状态；NaN 样本原样保留；
    - 样本时间取 帧号/fps，跨 NaN 缺口按真实时间差计算 dt；
    - 每个通道的首个有效样本直接通过（不滤波）。
    """
    if fps <= 0:
        raise ValueError(f'fps 必须为正数，收到 {fps}')
    out = _to_kpts(arr)
    n_frames, n_kpts = out.shape[0], out.shape[1]
    # filters[k][c]：第 k 个关键点第 c 通道（0=x, 1=y）的滤波器实例
    filters = [[_OneEuroChannel(min_cutoff, beta, d_cutoff) for _ in range(2)]
               for _ in range(n_kpts)]
    for i in range(n_frames):
        t = i / fps
        for k in range(n_kpts):
            for c in (0, 1):
                v = out[i, k, c]
                if np.isfinite(v):
                    out[i, k, c] = filters[k][c](float(v), t)
                # NaN 样本保留，滤波器状态不变
    return out


# 左右大腿/小腿/大臂/小臂骨骼段（均为 halpe26.SKELETON_LINKS 的子集），
# 用于骨骼段长度突变检测。
_LIMB_SEGMENTS: tuple[tuple[int, int], ...] = (
    (halpe26.LEFT_KNEE, halpe26.LEFT_HIP),          # 左大腿
    (halpe26.LEFT_ANKLE, halpe26.LEFT_KNEE),        # 左小腿
    (halpe26.RIGHT_KNEE, halpe26.RIGHT_HIP),        # 右大腿
    (halpe26.RIGHT_ANKLE, halpe26.RIGHT_KNEE),      # 右小腿
    (halpe26.LEFT_SHOULDER, halpe26.LEFT_ELBOW),    # 左大臂
    (halpe26.LEFT_ELBOW, halpe26.LEFT_WRIST),       # 左小臂
    (halpe26.RIGHT_SHOULDER, halpe26.RIGHT_ELBOW),  # 右大臂
    (halpe26.RIGHT_ELBOW, halpe26.RIGHT_WRIST),     # 右小臂
)


def detect_outliers(arr, body_height, max_jump_ratio,
                    limb_change_ratio) -> tuple[np.ndarray, int]:
    """尖峰跳点与骨骼段长度突变检测。

    规则 A（尖峰跳点，body_height 有效时启用）：某点第 t 帧相对 t-1 帧
    位移 > max_jump_ratio×body_height，且第 t+1 帧回到 t-1 帧位置附近
    （位移 < max_jump_ratio×body_height）→ 第 t 帧该点置 NaN。
    规则 B（骨骼段长度突变）：对左右大腿/小腿/大臂/小臂 8 段，某帧段长
    相对前后帧中位数突变超过 limb_change_ratio×100% → 该帧该段两端点
    置 NaN（注意：单帧突变的左右相邻帧因窗口包含突变值，同样满足判据
    会被一并置 NaN，随后可由 interpolate_gaps 填补）。
    body_height 为 None（无法估计身高）时仅跳过规则 A。

    返回 (修正后数组副本, 修正点数)；修正点数为被置 NaN 的 (帧, 点)
    位置数（两规则命中的同一位置只计一次）。
    """
    out = _to_kpts(arr)
    n_frames = out.shape[0]
    mask = np.zeros(out.shape[:2], dtype=bool)      # (F, 26) 待置 NaN 掩码

    # ---- 规则 A：尖峰跳点（远离后立即回到原位） ----
    if body_height is not None and body_height > 0 and n_frames >= 3:
        thr = float(max_jump_ratio) * float(body_height)
        xy = out[:, :, :2]                          # (F, 26, 2) 只读视图
        for t in range(1, n_frames - 1):
            p_prev, p_cur, p_next = xy[t - 1], xy[t], xy[t + 1]
            # 三帧均有效才可判定
            valid = (np.isfinite(p_prev).all(axis=1)
                     & np.isfinite(p_cur).all(axis=1)
                     & np.isfinite(p_next).all(axis=1))
            # t 相对 t-1 的位移（跳离幅度）
            jump = np.hypot(p_cur[:, 0] - p_prev[:, 0],
                            p_cur[:, 1] - p_prev[:, 1])
            # t+1 相对 t-1 的位移（是否回到原位附近）
            ret = np.hypot(p_next[:, 0] - p_prev[:, 0],
                           p_next[:, 1] - p_prev[:, 1])
            mask[t] |= valid & (jump > thr) & (ret < thr)

    # ---- 规则 B：骨骼段长度突变 ----
    if n_frames >= 3:
        for ia, ib in _LIMB_SEGMENTS:
            a = out[:, ia, :2]
            b = out[:, ib, :2]
            seg_len = np.hypot(a[:, 0] - b[:, 0], a[:, 1] - b[:, 1])
            for t in range(1, n_frames - 1):
                l_prev, l_cur, l_next = seg_len[t - 1], seg_len[t], seg_len[t + 1]
                if not (np.isfinite(l_prev) and np.isfinite(l_cur)
                        and np.isfinite(l_next)):
                    continue
                # 前后帧段长中位数作为参考（两个数的中位数即均值）
                ref = float(np.median([l_prev, l_next]))
                if ref <= 0.0:
                    continue
                if abs(l_cur - ref) > limb_change_ratio * ref:
                    mask[t, ia] = True
                    mask[t, ib] = True

    out[mask, 0] = np.nan
    out[mask, 1] = np.nan
    return out, int(mask.sum())


def postprocess(raw, fps, thresholds: Thresholds,
                body_height=None) -> tuple[np.ndarray, int]:
    """姿态后处理编排。

    mark_invalid → detect_outliers → interpolate_gaps → one_euro_filter。
    body_height 为 None 时用 halpe26.body_height_px 估计（基于标记无效
    后的数组）；估计仍为 None 时 detect_outliers 内部跳过尖峰跳点检测，
    仅保留骨骼段长度突变检测。返回 (filtered, n_outliers)。
    """
    arr = mark_invalid(raw, thresholds.keypoint_score_thr)
    if body_height is None:
        body_height = halpe26.body_height_px(arr)
    arr, n_outliers = detect_outliers(
        arr, body_height,
        thresholds.max_kpt_jump_ratio, thresholds.limb_change_ratio)
    arr = interpolate_gaps(arr, thresholds.max_interp_gap)
    arr = one_euro_filter(
        arr, fps,
        thresholds.one_euro_min_cutoff, thresholds.one_euro_beta,
        thresholds.one_euro_d_cutoff)
    return arr, n_outliers


def compute_pose_quality(raw_frame, det_score, score_thr) -> float:
    """单帧姿态质量 = det_score × 该帧有效点比例（x 非 NaN 计数 / 26）。

    raw_frame: (26, 3) 单帧关键点数组（遵循「无效点 x/y=NaN」约定，
    通常为 mark_invalid 之后、滤波之前的帧）；score_thr 为接口预留参数
    （有效点已按 NaN 约定标记，直接统计 x 非 NaN 即可）。
    det_score 为 None/NaN 时返回 0.0。
    """
    arr = np.asarray(raw_frame, dtype=float)
    if arr.ndim != 2 or arr.shape != (halpe26.NUM_KEYPOINTS, 3):
        raise ValueError(
            f'单帧关键点 shape 应为 ({halpe26.NUM_KEYPOINTS}, 3)，'
            f'收到 {arr.shape}')
    ratio = float(np.mean(np.isfinite(arr[:, 0])))
    if det_score is None:
        return 0.0
    det = float(det_score)
    if not math.isfinite(det):
        return 0.0
    return det * ratio
