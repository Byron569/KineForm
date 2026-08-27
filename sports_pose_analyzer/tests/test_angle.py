"""three_point_angle 三点夹角单元测试（无 GPU 依赖）。"""
import math

import pytest

from app.biomechanics.metrics import three_point_angle


def test_right_angle_90():
    """直角：u⊥v → 90°。"""
    assert three_point_angle((1.0, 0.0), (0.0, 0.0), (0.0, 1.0)) == pytest.approx(90.0)


def test_straight_180():
    """共线反向（a、c 在顶点两侧）→ 180°。"""
    assert three_point_angle((1.0, 0.0), (0.0, 0.0), (-1.0, 0.0)) == pytest.approx(180.0)
    assert three_point_angle((2.0, 0.0), (0.0, 0.0), (-3.0, 0.0)) == pytest.approx(180.0)


def test_angle_45():
    """dx=dy 的半直角 → 45°。"""
    assert three_point_angle((1.0, 0.0), (0.0, 0.0), (1.0, 1.0)) == pytest.approx(45.0)


def test_collinear_same_direction_0():
    """共线同向（a、c 在顶点同侧）→ 0°。"""
    assert three_point_angle((1.0, 0.0), (0.0, 0.0), (2.0, 0.0)) == pytest.approx(0.0)


def test_nan_propagation():
    """任一输入含 NaN → NaN。"""
    nan = float('nan')
    assert math.isnan(three_point_angle((nan, 0.0), (0.0, 0.0), (0.0, 1.0)))
    assert math.isnan(three_point_angle((1.0, 0.0), (nan, 0.0), (0.0, 1.0)))
    assert math.isnan(three_point_angle((1.0, 0.0), (0.0, 0.0), (0.0, nan)))


def test_arbitrary_non_collinear():
    """非共线任意角与解析解一致：cos = 1/sqrt(5)。"""
    expected = math.degrees(math.acos(1.0 / math.sqrt(5.0)))
    assert three_point_angle((2.0, 0.0), (0.0, 0.0), (1.0, 2.0)) == pytest.approx(expected)


def test_keypoint_row_with_score_channel():
    """(3,) 关键点行（x, y, score）：只取前两通道参与计算。"""
    a = three_point_angle((1.0, 0.0, 0.9), (0.0, 0.0, 0.8), (0.0, 1.0, 0.7))
    assert a == pytest.approx(90.0)
