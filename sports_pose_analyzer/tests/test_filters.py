"""后处理滤波单元测试：mark_invalid / one_euro / detect_outliers / postprocess。"""
import numpy as np
import pytest

from app.common.halpe26 import LEFT_ELBOW, LEFT_WRIST, NUM_KEYPOINTS
from app.config.defaults import Thresholds
from app.postprocess.filters import (
    detect_outliers,
    mark_invalid,
    one_euro_filter,
    postprocess,
)


# ---------------- mark_invalid ----------------
def test_mark_invalid_threshold_boundary():
    """score == 阈值的点保留（严格小于才置 NaN）。"""
    n = 4
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.5                    # 恰好等于阈值 → 全部保留
    arr[0, 0, 2] = 0.4                    # 低于阈值 → 无效
    arr[1, 5, 2] = 0.499999               # 略低于阈值 → 无效
    arr[2, 7, 2] = 0.500001               # 略高于阈值 → 保留
    out = mark_invalid(arr, score_thr=0.5)

    assert np.isnan(out[0, 0, 0]) and np.isnan(out[0, 0, 1])
    assert np.isnan(out[1, 5, 0]) and np.isnan(out[1, 5, 1])
    assert np.isfinite(out[2, 7, 0]) and np.isfinite(out[2, 7, 1])
    assert np.isfinite(out[3, 3, 0])      # == 阈值的点保留
    assert np.isfinite(out[0, 1, 0])      # 同帧其他点不受影响
    # score 通道保留原值
    assert out[0, 0, 2] == 0.4
    assert out[2, 7, 2] == pytest.approx(0.500001)
    # 输入未被修改
    assert np.isfinite(arr[0, 0, 0]) and np.isfinite(arr[1, 5, 1])


# ---------------- one_euro_filter ----------------
def test_one_euro_constant_series_passthrough():
    """常数序列：输出 ≈ 常数（首样本直通 + 零导数 → 不漂移）。"""
    n = 40
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    arr[:, 3, 0] = 123.4
    arr[:, 3, 1] = 56.7
    out = one_euro_filter(arr, fps=25.0, min_cutoff=1.5, beta=0.1, d_cutoff=1.0)
    assert np.allclose(out[:, 3, 0], 123.4, atol=1e-9)
    assert np.allclose(out[:, 3, 1], 56.7, atol=1e-9)
    assert np.allclose(out[:, 4, 0], 0.0)          # 其余常 0 点仍是 0
    assert np.allclose(out[:, :, 2], 0.9)          # score 通道不动


def test_one_euro_preserves_nan():
    """NaN 样本原样保留，且不影响后续有效样本滤波。"""
    n = 12
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    arr[:, 2, 0] = 50.0
    arr[5, 2, 0] = np.nan
    arr[6, 2, 0] = np.nan
    out = one_euro_filter(arr, fps=25.0)
    assert np.isnan(out[5, 2, 0]) and np.isnan(out[6, 2, 0])
    assert np.isfinite(out[4, 2, 0]) and np.isfinite(out[7, 2, 0])
    assert out[0, 2, 0] == pytest.approx(50.0)     # 首样本直接通过


# ---------------- detect_outliers ----------------
def _base_pose(n=10):
    """构造静止姿态序列 (n, 26, 3)：第 k 点固定于 (100+k, 200+k)。"""
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    for k in range(NUM_KEYPOINTS):
        arr[:, k, 0] = 100.0 + k
        arr[:, k, 1] = 200.0 + k
    return arr


def test_detect_outliers_single_spike_removed():
    """单点尖峰（跳离后立即回位）被剔除，周围帧/点不动。"""
    arr = _base_pose()
    arr[5, 0, 0] = 400.0        # 鼻子第 5 帧跳离 300px（不在四肢骨骼段上）
    out, n = detect_outliers(arr, body_height=500.0,
                             max_jump_ratio=0.35, limb_change_ratio=0.40)
    assert n == 1
    assert np.isnan(out[5, 0, 0]) and np.isnan(out[5, 0, 1])
    assert out[5, 0, 2] == 0.9                       # score 保留
    assert out[4, 0, 0] == 100.0 and out[6, 0, 0] == 100.0   # 前后帧不动
    for t in (4, 5, 6):                              # 其它点不动
        for k in range(1, NUM_KEYPOINTS):
            assert np.isfinite(out[t, k, 0]) and np.isfinite(out[t, k, 1])
    for t in range(10):                              # 其它帧鼻子不动
        if t != 5:
            assert out[t, 0, 0] == 100.0


def test_detect_outliers_without_body_height_skips_spike_rule():
    """body_height=None → 跳过尖峰跳点检测，尖峰保留。"""
    arr = _base_pose()
    arr[5, 0, 0] = 400.0
    out, n = detect_outliers(arr, body_height=None,
                             max_jump_ratio=0.35, limb_change_ratio=0.40)
    assert n == 0
    assert out[5, 0, 0] == 400.0


def test_detect_outliers_limb_length_change():
    """左小臂段长单帧突变 > 40% → 突变帧两端点（肘/腕）置 NaN。

    按规则定义（某帧段长 vs 前后帧中位数），突变帧的左右相邻帧因
    窗口内包含突变值也会被判为突变，一并置 NaN（帧 4/5/6）。
    """
    arr = _base_pose()
    arr[:, LEFT_ELBOW, 0] = 100.0
    arr[:, LEFT_ELBOW, 1] = 200.0
    arr[:, LEFT_WRIST, 0] = 150.0        # 段长 50
    arr[:, LEFT_WRIST, 1] = 200.0
    arr[5, LEFT_WRIST, 0] = 300.0        # 第 5 帧段长 200（突变 300%）
    out, n = detect_outliers(arr, body_height=None,
                             max_jump_ratio=0.35, limb_change_ratio=0.40)
    # 帧 4/5/6 × (左肘 + 左腕) = 6 个修正点
    assert n == 6
    for t in (4, 5, 6):
        assert np.isnan(out[t, LEFT_ELBOW, 0]) and np.isnan(out[t, LEFT_ELBOW, 1])
        assert np.isnan(out[t, LEFT_WRIST, 0]) and np.isnan(out[t, LEFT_WRIST, 1])
    # 窗口外的帧与其它点不动
    assert out[3, LEFT_WRIST, 0] == 150.0 and out[7, LEFT_WRIST, 0] == 150.0
    assert out[3, LEFT_ELBOW, 0] == 100.0
    assert np.isfinite(out[5, 3, 0])          # 非该骨骼的点不受影响


# ---------------- postprocess 编排 ----------------
def test_postprocess_pipeline_smoke():
    """编排冒烟：低分点标记 → 单帧缺口插值 → 平滑；输入不被修改。"""
    n = 30
    t = np.arange(n)
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    for k in range(NUM_KEYPOINTS):        # 平滑小幅摆动（无跳点/无段长突变）
        arr[:, k, 0] = 300.0 + k * 2.0 + 5.0 * np.sin(2.0 * np.pi * t / 30.0)
        arr[:, k, 1] = 300.0 + k * 3.0 + 4.0 * np.cos(2.0 * np.pi * t / 30.0)
    arr[10, 3, 2] = 0.10                  # 单帧低分 → 无效后又被插值填补
    before = arr.copy()

    filtered, n_outliers = postprocess(arr, fps=25.0, thresholds=Thresholds())
    assert filtered.shape == (n, NUM_KEYPOINTS, 3)
    assert isinstance(n_outliers, int) and n_outliers == 0
    assert np.array_equal(arr, before)                    # 输入未被修改
    assert np.isfinite(filtered[10, 3, 0])                # 缺口已插值填补
    assert filtered[10, 3, 2] == 0.10                     # score 保留原值
    assert np.allclose(filtered[:, :, 2], arr[:, :, 2])   # score 通道不变


def test_postprocess_long_gap_stays_nan():
    """超过 max_interp_gap 的长缺口插值后仍为 NaN。"""
    n = 20
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    arr[:, 3, 0] = 10.0
    arr[8:16, 3, 2] = 0.05                 # 连续 8 帧低分 → 长缺口
    filtered, _ = postprocess(arr, fps=25.0, thresholds=Thresholds())
    assert np.isnan(filtered[8:16, 3, 0]).all()
    assert np.isfinite(filtered[7, 3, 0]) and np.isfinite(filtered[16, 3, 0])
