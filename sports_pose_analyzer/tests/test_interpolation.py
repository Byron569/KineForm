"""interpolate_gaps 缺口插值单元测试（无 GPU 依赖）。"""
import numpy as np
import pytest

from app.common.halpe26 import NUM_KEYPOINTS
from app.postprocess.filters import interpolate_gaps

K = 5  # 测试用的关键点索引（任取）


def _make(x_values, nan_frames):
    """构造 (F, 26, 3)：关键点 K 的 x 取 x_values，指定帧 x/y 置 NaN。"""
    n = len(x_values)
    arr = np.zeros((n, NUM_KEYPOINTS, 3))
    arr[:, :, 2] = 0.9
    arr[:, K, 0] = x_values
    arr[:, K, 1] = 100.0 + 2.0 * np.arange(n)
    for i in nan_frames:
        arr[i, K, 0] = np.nan
        arr[i, K, 1] = np.nan
    return arr


def test_gap_of_3_frames_filled_linearly():
    """缺口 3 帧（≤ max_gap）线性填补，数值正确。"""
    x = np.arange(10, dtype=float) * 4.0        # 0,4,...,36
    arr = _make(x, nan_frames=[3, 4, 5])
    out = interpolate_gaps(arr, max_gap=5)
    # x：帧 2=8、帧 6=24，缺口内应为 12/16/20
    assert out[3, K, 0] == pytest.approx(12.0)
    assert out[4, K, 0] == pytest.approx(16.0)
    assert out[5, K, 0] == pytest.approx(20.0)
    # y：100+2i，缺口内应为 106/108/110
    assert out[3, K, 1] == pytest.approx(106.0)
    assert out[4, K, 1] == pytest.approx(108.0)
    assert out[5, K, 1] == pytest.approx(110.0)


def test_gap_of_8_frames_not_filled_when_max_gap_5():
    """缺口 8 帧 > max_gap=5 → 不填补，保持 NaN。"""
    x = np.arange(12, dtype=float)
    arr = _make(x, nan_frames=list(range(2, 10)))   # 连续缺失 8 帧
    out = interpolate_gaps(arr, max_gap=5)
    assert np.isnan(out[2:10, K, 0]).all()
    assert np.isnan(out[2:10, K, 1]).all()
    # 缺口两侧的有效样本不动
    assert out[1, K, 0] == 1.0 and out[10, K, 0] == 10.0
    assert out[1, K, 1] == 102.0 and out[10, K, 1] == 120.0


def test_leading_and_trailing_gaps_not_filled():
    """首/尾缺口（单侧无有效样本）不填补。"""
    x = np.arange(10, dtype=float)
    arr = _make(x, nan_frames=[0, 1, 8, 9])
    out = interpolate_gaps(arr, max_gap=5)
    assert np.isnan(out[[0, 1, 8, 9], K, 0]).all()
    assert np.isnan(out[[0, 1, 8, 9], K, 1]).all()
    assert out[4, K, 0] == 4.0          # 中部有效样本不动


def test_score_channel_unchanged():
    """插值只改 x/y，score 通道（含缺口帧的低分）原样保留。"""
    x = np.arange(8, dtype=float)
    arr = _make(x, nan_frames=[3, 4])
    arr[3, K, 2] = 0.10                 # 缺口帧原始低分
    arr[4, K, 2] = 0.20
    out = interpolate_gaps(arr, max_gap=5)
    assert out[3, K, 0] == pytest.approx(3.0)     # x 已填补
    assert out[4, K, 0] == pytest.approx(4.0)
    assert out[3, K, 2] == 0.10                   # score 不变
    assert out[4, K, 2] == 0.20
    assert np.allclose(out[:, :, 2], arr[:, :, 2])


def test_input_array_not_modified():
    """返回副本，输入数组不被修改。"""
    x = np.arange(8, dtype=float)
    arr = _make(x, nan_frames=[3, 4])
    before = arr.copy()
    interpolate_gaps(arr, max_gap=5)
    assert np.array_equal(arr, before, equal_nan=True)
