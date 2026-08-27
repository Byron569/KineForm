"""运动学指标单元测试：躯干倾角 / 关键点速度 / 角度序列一致性。"""
import numpy as np
import pytest

from app.biomechanics.metrics import (
    angle_series,
    angular_velocity,
    compute_metrics,
    keypoint_speeds,
    symmetry_summary,
    three_point_angle,
    torso_lean_series,
    trajectories,
)
from app.common.halpe26 import (
    ANGLE_DEFS,
    HEAD,
    HIP,
    LEFT_HIP,
    NECK,
    NUM_KEYPOINTS,
    RIGHT_HIP,
)


def _kpts_with(pairs):
    """构造 (1, 26, 3)：仅设置指定关键点 idx -> (x, y)，其余点 NaN，score=0.9。"""
    arr = np.full((1, NUM_KEYPOINTS, 3), np.nan)
    arr[:, :, 2] = 0.9
    for idx, (x, y) in pairs.items():
        arr[0, idx, 0] = x
        arr[0, idx, 1] = y
    return arr


# ---------------- 躯干倾角 ----------------
def test_torso_lean_vertical_is_zero():
    """竖直（dx=0）→ 0°。"""
    arr = _kpts_with({NECK: (100.0, 100.0), HIP: (100.0, 200.0)})
    assert torso_lean_series(arr)[0] == pytest.approx(0.0)


def test_torso_lean_45_when_dx_equals_dy():
    """dx=dy → 45°。"""
    arr = _kpts_with({NECK: (100.0, 100.0), HIP: (150.0, 150.0)})
    assert torso_lean_series(arr)[0] == pytest.approx(45.0)


def test_torso_lean_mirrored_is_minus_45():
    """镜像（dx=-dy）→ -45°。"""
    arr = _kpts_with({NECK: (100.0, 100.0), HIP: (50.0, 150.0)})
    assert torso_lean_series(arr)[0] == pytest.approx(-45.0)


def test_torso_lean_pelvis_fallback_and_nan():
    """HIP 无效 → 左右髋中点；再无效 → NaN。"""
    arr = _kpts_with({NECK: (100.0, 100.0),
                      LEFT_HIP: (80.0, 200.0), RIGHT_HIP: (120.0, 200.0)})
    assert torso_lean_series(arr)[0] == pytest.approx(0.0)   # 中点 (100,200)
    arr2 = _kpts_with({NECK: (100.0, 100.0)})                # 骨盆完全无效
    assert np.isnan(torso_lean_series(arr2)[0])


# ---------------- 关键点速度 ----------------
def test_constant_speed_10px_per_frame_at_25fps():
    """恒定速度 10 px/帧 @25fps → 250 px/s（含边界单侧差分帧）。"""
    n = 10
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    arr[:, 7, 0] = np.arange(n) * 10.0        # 关键点 7 每帧 x +10px
    speeds = keypoint_speeds(arr, fps=25.0)
    assert speeds.shape == (n, NUM_KEYPOINTS)
    assert speeds[:, 7] == pytest.approx(250.0)
    assert speeds[:, 0] == pytest.approx(0.0)  # 静止点速度为 0


def test_keypoint_speeds_nan_propagation():
    """无效帧及差分涉及无效样本 → NaN。"""
    n = 8
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    arr[:, 3, 0] = np.arange(n) * 10.0
    arr[4, 3, 0] = np.nan                      # 第 4 帧无效
    speeds = keypoint_speeds(arr, fps=25.0)
    # 第 4 帧本身无效 → NaN；第 3、5 帧中心差分涉及第 4 帧 → NaN
    assert np.isnan(speeds[[3, 4, 5], 3]).all()
    assert speeds[2, 3] == pytest.approx(250.0)


# ---------------- 角度序列一致性 ----------------
def test_angle_series_matches_per_frame_three_point_angle():
    """angle_series 与逐帧调用 three_point_angle 完全一致（含 NaN）。"""
    rng = np.random.default_rng(7)
    n = 30
    arr = rng.uniform(0.0, 500.0, size=(n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = rng.uniform(0.4, 0.99, size=(n, NUM_KEYPOINTS))
    mask = rng.random((n, NUM_KEYPOINTS)) < 0.15
    arr[mask, 0] = np.nan
    arr[mask, 1] = np.nan
    series = angle_series(arr)
    assert set(series.keys()) == set(ANGLE_DEFS.keys())
    for name, (ia, ib, ic) in ANGLE_DEFS.items():
        per_frame = np.array([
            three_point_angle(arr[t, ia], arr[t, ib], arr[t, ic])
            for t in range(n)])
        assert np.allclose(series[name], per_frame, equal_nan=True)


# ---------------- 角速度 ----------------
def test_angular_velocity_constant_rate():
    """角度每帧 +10° @25fps → 250 deg/s（含边界单侧差分帧）。"""
    n = 12
    av = angular_velocity({'left_knee': np.arange(n, dtype=float) * 10.0},
                          fps=25.0)
    assert av['left_knee'] == pytest.approx(250.0)


# ---------------- 对称性 ----------------
def test_symmetry_summary_pairs_and_overall():
    """四对均值 + overall（无同时有效帧的对不计入 overall）。"""
    n = 10
    angles = {
        'left_knee': np.full(n, 90.0), 'right_knee': np.full(n, 100.0),
        'left_hip': np.full(n, 120.0), 'right_hip': np.full(n, 120.0),
        'left_ankle': np.full(n, np.nan), 'right_ankle': np.full(n, 80.0),
        'left_elbow': np.full(n, 150.0), 'right_elbow': np.full(n, 140.0),
    }
    sym = symmetry_summary(angles)
    assert sym['knee_mean_abs_diff_deg'] == pytest.approx(10.0)
    assert sym['hip_mean_abs_diff_deg'] == pytest.approx(0.0)
    assert sym['elbow_mean_abs_diff_deg'] == pytest.approx(10.0)
    assert np.isnan(sym['ankle_mean_abs_diff_deg'])
    # overall = (10 + 0 + 10) / 3，ankle 不计入
    assert sym['overall_mean_abs_diff_deg'] == pytest.approx(20.0 / 3.0)


# ---------------- 轨迹与组装 ----------------
def test_trajectories_points():
    """head/heel 直接取点，pelvis 走 HIP 优先逻辑。"""
    n = 5
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    arr[:, HEAD, 0] = 10.0
    arr[:, HEAD, 1] = 20.0
    arr[:, HIP, 0] = 30.0
    arr[:, HIP, 1] = 40.0
    traj = trajectories(arr)
    assert set(traj.keys()) == {'pelvis', 'head', 'left_heel', 'right_heel'}
    assert np.allclose(traj['head'], np.column_stack([np.full(n, 10.0), np.full(n, 20.0)]))
    assert np.allclose(traj['pelvis'], np.column_stack([np.full(n, 30.0), np.full(n, 40.0)]))


def test_compute_metrics_assembles_all_fields():
    """compute_metrics 填全 MetricsResult 全部字段，pelvis_speed 取 HIP 列。"""
    n = 20
    rng = np.random.default_rng(3)
    arr = rng.uniform(0.0, 600.0, size=(n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    m = compute_metrics(
        arr, fps=30.0,
        frame_indices=np.arange(n),
        timestamps_ms=np.arange(n) / 30.0 * 1000.0,
        pose_quality=np.full(n, 0.7),
        valid_ratio=np.ones(n),
        missing_ratio=np.zeros(n))
    assert m.frame_count == n
    assert m.fps == pytest.approx(30.0)
    assert set(m.angles.keys()) == set(ANGLE_DEFS.keys())
    assert set(m.angular_velocity.keys()) == set(ANGLE_DEFS.keys())
    assert m.torso_lean.shape == (n,)
    assert set(m.trajectories.keys()) == {'pelvis', 'head', 'left_heel', 'right_heel'}
    assert m.keypoint_speeds.shape == (n, NUM_KEYPOINTS)
    assert m.pelvis_speed.shape == (n,)
    assert np.allclose(m.pelvis_speed, m.keypoint_speeds[:, HIP])
    assert 'overall_mean_abs_diff_deg' in m.symmetry_index
    assert m.pose_quality[0] == pytest.approx(0.7)
    assert np.allclose(m.timestamps_ms, np.arange(n) / 30.0 * 1000.0)
