"""身体尺度估计与像素归一化测试。

合成数据：身高（头→双踝中点）= 400px，腿长（髋→踝）= 200px，
骨盆 x 匀速 3px/帧 @ 30fps → 90 px/s；身高 1.8m 时 0.0045 m/px
→ 跑速 0.405 m/s。
"""
import numpy as np
import pytest

from app.biomechanics.scale import body_scale, run_speed_estimate
from app.common.halpe26 import (
    HEAD, LEFT_ANKLE, LEFT_HIP, NUM_KEYPOINTS, RIGHT_ANKLE)


def _kpts(n: int = 30) -> np.ndarray:
    """直立人：头 y=100、肩髋 y=300/400、膝 500、踝 600（身高 500px），
    腿长 = 200px（髋 400 → 踝 600）。"""
    arr = np.full((n, NUM_KEYPOINTS, 3), np.nan)
    pts = {
        HEAD: (320.0, 100.0),
        LEFT_HIP: (300.0, 400.0),
        LEFT_ANKLE: (300.0, 600.0),
        RIGHT_ANKLE: (340.0, 600.0),
    }
    for i, (x, y) in pts.items():
        arr[:, i, 0] = x
        arr[:, i, 1] = y
        arr[:, i, 2] = 0.9
    return arr


def test_body_scale_height_and_leg():
    """身高（头→双踝中点 y）= 500px；腿长（髋→踝）= 200px。"""
    s = body_scale(_kpts())
    assert s['body_height_px'] == pytest.approx(500.0)
    assert s['leg_length_px'] == pytest.approx(200.0)


def test_body_scale_nan_robust():
    """部分帧全 NaN：基于有效帧中位数；不足 3 有效帧 → None。"""
    arr = _kpts(10)
    arr[:5] = np.nan
    s = body_scale(arr)
    assert s['body_height_px'] == pytest.approx(500.0)
    assert s['leg_length_px'] == pytest.approx(200.0)

    s2 = body_scale(np.full((2, NUM_KEYPOINTS, 3), np.nan))
    assert s2['body_height_px'] is None
    assert s2['leg_length_px'] is None


def test_run_speed_linear_pelvis():
    """匀速 3px/帧 @30fps → 90 px/s；给身高 1.8m → 0.405 m/s。"""
    n = 60
    t_ms = np.arange(n) * (1000.0 / 30.0)
    pelvis_x = 100.0 + 3.0 * np.arange(n)
    s = run_speed_estimate(pelvis_x, t_ms, body_height_px=500.0,
                           height_m=1.8)
    assert s['speed_px_s'] == pytest.approx(90.0, abs=0.5)
    assert s['m_per_px'] == pytest.approx(1.8 / 500.0)
    assert s['speed_mps'] == pytest.approx(90.0 * 1.8 / 500.0, abs=0.01)


def test_run_speed_no_height_or_treadmill():
    """无身高 → 只有 px/s；原地跑（斜率≈0）→ 速度≈0；样本不足 → None。"""
    t_ms = np.arange(30) * (1000.0 / 30.0)
    s = run_speed_estimate(100.0 + 2.0 * np.arange(30), t_ms)
    assert 'm_per_px' not in s and 'speed_mps' not in s

    s2 = run_speed_estimate(np.full(30, 100.0), t_ms)
    assert s2['speed_px_s'] == pytest.approx(0.0, abs=1e-6)

    assert run_speed_estimate(np.array([1.0, 2.0]), np.array([0.0, 33.3])) is None
