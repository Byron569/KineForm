"""二维节段角测试（大腿角相对水平、小腿角相对竖直）。

角度约定（图像坐标 y 向下，+x 为前进方向）：
- 大腿角：髋→膝向量相对水平的 signed 角，膝在髋前上方为正；
  Mattes 最大抬腿参考 ≈ 21°。
- 小腿角：膝→踝向量相对竖直向下的 signed 角，踝在膝前方为正（前倾）；
  800m 世界级 IC 参考 ≈ 4–7°。
"""
import numpy as np
import pytest

from app.biomechanics.segment_angles import (
    segment_angle_series, shank_angle_series, shoulder_angle_series,
    thigh_angle_series)
from app.common.halpe26 import (
    LEFT_ANKLE, LEFT_ELBOW, LEFT_HIP, LEFT_KNEE, LEFT_SHOULDER,
    NUM_KEYPOINTS)


def _kpts_with(n: int, points: dict[int, tuple[float, float]]) -> np.ndarray:
    """构造 (n,26,3) 数组，指定索引处放固定坐标，其余给有效占位值。"""
    arr = np.full((n, NUM_KEYPOINTS, 3), np.nan)
    for i, (x, y) in points.items():
        arr[:, i, 0] = x
        arr[:, i, 1] = y
        arr[:, i, 2] = 0.9
    return arr


def test_thigh_angle_geometry():
    """前上 26.57°、垂直向下 -90°、后上 153.43°（左向跑镜像位）。"""
    # 髋(100,100) 膝(120,90)：dx=20, dy=-10（图像 y 向下）
    arr = _kpts_with(1, {LEFT_HIP: (100.0, 100.0), LEFT_KNEE: (120.0, 90.0)})
    s = thigh_angle_series(arr)
    assert s['left_thigh'][0] == pytest.approx(26.57, abs=0.01)

    # 膝在髋正下方：大腿竖直下垂 = -90°
    arr = _kpts_with(1, {LEFT_HIP: (100.0, 100.0), LEFT_KNEE: (100.0, 200.0)})
    s = thigh_angle_series(arr)
    assert s['left_thigh'][0] == pytest.approx(-90.0)

    # 膝在髋后上方（左向跑的最大抬腿镜像）
    arr = _kpts_with(1, {LEFT_HIP: (100.0, 100.0), LEFT_KNEE: (80.0, 90.0)})
    s = thigh_angle_series(arr)
    assert s['left_thigh'][0] == pytest.approx(153.43, abs=0.01)


def test_shank_angle_geometry():
    """竖直 0°、前倾 +5.71°、后倾 -5.71°。"""
    arr = _kpts_with(1, {LEFT_KNEE: (100.0, 100.0),
                         LEFT_ANKLE: (100.0, 200.0)})
    s = shank_angle_series(arr)
    assert s['left_shank'][0] == pytest.approx(0.0)

    arr = _kpts_with(1, {LEFT_KNEE: (100.0, 100.0),
                         LEFT_ANKLE: (110.0, 200.0)})
    s = shank_angle_series(arr)
    assert s['left_shank'][0] == pytest.approx(5.71, abs=0.01)

    arr = _kpts_with(1, {LEFT_KNEE: (100.0, 100.0),
                         LEFT_ANKLE: (90.0, 200.0)})
    s = shank_angle_series(arr)
    assert s['left_shank'][0] == pytest.approx(-5.71, abs=0.01)


def test_segment_angle_series_keys_and_nan():
    """合并输出 4 键；无效点与零向量 → NaN；左右互不污染。"""
    # 帧 0 正常，帧 1 髋 NaN，帧 2 髋膝重合（零向量）
    arr = _kpts_with(3, {LEFT_HIP: (100.0, 100.0), LEFT_KNEE: (120.0, 90.0)})
    arr[1, LEFT_HIP, 0] = np.nan
    arr[1, LEFT_HIP, 1] = np.nan
    arr[2, LEFT_KNEE, 0] = 100.0
    arr[2, LEFT_KNEE, 1] = 100.0

    s = segment_angle_series(arr)
    assert set(s.keys()) == {'left_thigh', 'right_thigh',
                             'left_shank', 'right_shank',
                             'left_shoulder', 'right_shoulder'}
    assert np.isfinite(s['left_thigh'][0])
    assert np.isnan(s['left_thigh'][1])       # NaN 传播
    assert np.isnan(s['left_thigh'][2])       # 零向量 → NaN
    # 右侧未赋坐标 → 全 NaN
    assert np.isnan(s['right_thigh']).all()
    assert np.isnan(s['right_shank']).all()
    assert np.isnan(s['right_shoulder']).all()


def test_shoulder_angle_hanley_convention():
    """Hanley 解剖约定：下垂 0°、前摆 +90°、后摆 −90°；
    躯干倾斜由同侧髋−肩参考补偿。"""
    # 躯干竖直：肩(100,100) 髋(100,200)
    pts = {LEFT_SHOULDER: (100.0, 100.0), LEFT_HIP: (100.0, 200.0)}

    # 手臂下垂：肘(100,180) → 0°
    arr = _kpts_with(1, {**pts, LEFT_ELBOW: (100.0, 180.0)})
    s = shoulder_angle_series(arr)
    assert s['left_shoulder'][0] == pytest.approx(0.0, abs=1e-9)

    # 前平举：肘(180,100) → +90°
    arr = _kpts_with(1, {**pts, LEFT_ELBOW: (180.0, 100.0)})
    s = shoulder_angle_series(arr)
    assert s['left_shoulder'][0] == pytest.approx(90.0)

    # 后平举：肘(20,100) → −90°
    arr = _kpts_with(1, {**pts, LEFT_ELBOW: (20.0, 100.0)})
    s = shoulder_angle_series(arr)
    assert s['left_shoulder'][0] == pytest.approx(-90.0)

    # 躯干前倾 45°（髋在肩右下方）+ 手臂沿躯干 → 0°（倾斜补偿）
    arr = _kpts_with(1, {LEFT_SHOULDER: (100.0, 100.0),
                         LEFT_HIP: (200.0, 200.0),
                         LEFT_ELBOW: (135.0, 135.0)})
    s = shoulder_angle_series(arr)
    assert s['left_shoulder'][0] == pytest.approx(0.0, abs=1e-9)


def test_shoulder_angle_nan_propagation():
    """肩/髋/肘任一点无效 → NaN；肩肘重合（零向量）→ NaN。"""
    arr = _kpts_with(3, {LEFT_SHOULDER: (100.0, 100.0),
                         LEFT_HIP: (100.0, 200.0),
                         LEFT_ELBOW: (180.0, 100.0)})
    arr[0, LEFT_HIP, 0] = np.nan
    arr[1, LEFT_ELBOW, 0] = np.nan
    arr[2, LEFT_ELBOW, 0] = 100.0     # 肩肘重合
    arr[2, LEFT_ELBOW, 1] = 100.0
    s = shoulder_angle_series(arr)
    assert np.isnan(s['left_shoulder']).all()


def test_segment_angles_shape_validation():
    """非法输入 shape 抛 ValueError。"""
    with pytest.raises(ValueError):
        thigh_angle_series(np.zeros((5, 17, 3)))
    with pytest.raises(ValueError):
        shank_angle_series(np.zeros((5, 26, 2)))
