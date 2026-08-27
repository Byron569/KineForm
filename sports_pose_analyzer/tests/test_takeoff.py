"""跳高起跳步识别测试。

合成数据：单侧（left）9 步序列，前 8 步为正常助跑步
（contact_time_ms=100、每步均有同侧 next_td_frame），末步为
起跳步候选（contact_time_ms=170、next_td_frame=None——起跳后
腾空过杆落垫，该侧不再有下一次触地）。

文献依据（Nicholson 2024 / WA2017，见
app/biomechanics/references.py hj_takeoff_success）：跳高起跳
触地 0.14–0.19 s（成功尝试均值 0.169 s），远长于助跑步。

已知答案：有效步触地中位数 = 100 ms，末步比值 = 1.7 > 1.4 →
识别 1 个起跳步；confidence = clamp(1.7 / (2×1.4), 0, 1) ≈ 0.6071。
"""
import pytest

from app.events.takeoff import identify_takeoff_steps

STRIDE_FRAMES = 30          # 相邻触地帧间隔（仅用于排布 td_frame）
START_TD = 60               # 首步触地帧


def _make_steps(contacts_ms: list[float], side: str = 'left',
                start_td: int = START_TD,
                stride_frames: int = STRIDE_FRAMES) -> list[dict]:
    """构造 gait_step_features 风格的合成步列表（关键字段子集）。

    td_frame 按固定步长递增；除末步 next_td_frame=None（该侧再无
    触地）外，其余步均有同侧下一次触地。
    """
    steps = []
    td = start_td
    for i, contact in enumerate(contacts_ms):
        is_last = i == len(contacts_ms) - 1
        steps.append({
            'side': side,
            'td_frame': td,
            'to_frame': td + 3,
            'next_td_frame': None if is_last else td + stride_frames,
            'contact_time_ms': float(contact),
            'flight_time_ms': None if is_last else 200.0,
            'stride_time_ms': None if is_last else 1000.0,
        })
        td += stride_frames
    return steps


def test_takeoff_detected_in_run_with_final_long_contact():
    """8 步正常助跑（contact=100ms）+ 末步长触地（170ms、其后无
    同侧触地）→ 识别出 1 个起跳步，side/td_frame 正确。"""
    steps = _make_steps([100.0] * 8 + [170.0])
    takeoffs = identify_takeoff_steps(steps)

    assert len(takeoffs) == 1
    t = takeoffs[0]
    assert t['side'] == 'left'
    assert t['td_frame'] == START_TD + STRIDE_FRAMES * 8     # 末步=300
    assert t['contact_time_ms'] == 170.0
    assert t['contact_median_ms'] == 100.0
    assert t['ratio'] == pytest.approx(1.7)
    assert 0.0 < t['confidence'] <= 1.0
    assert isinstance(t['reason'], str) and t['reason']


def test_pure_running_sequence_no_takeoff():
    """纯跑步序列（所有步 contact≈100，末步也是 100ms）→ 不识别
    任何起跳步（防止把普通末步误判为起跳）。"""
    contacts = [98.0, 102.0, 100.0, 101.0, 99.0, 100.0, 103.0, 97.0, 100.0]
    assert identify_takeoff_steps(_make_steps(contacts)) == []


def test_too_few_steps_returns_empty():
    """步数 < 4 → 空列表（中位数不可靠，宁可漏报不误报）；
    恰好 4 步（3 正常 + 1 起跳）仍可识别（边界含 4）。"""
    # 末步 contact=200，若无最少步数限制本应触发，但仅 3 步
    assert identify_takeoff_steps(_make_steps([100.0, 100.0, 200.0])) == []
    assert identify_takeoff_steps([]) == []

    takeoffs = identify_takeoff_steps(
        _make_steps([100.0, 100.0, 100.0, 170.0]))
    assert len(takeoffs) == 1
    assert takeoffs[0]['td_frame'] == START_TD + STRIDE_FRAMES * 3


def test_threshold_is_strictly_greater():
    """阈值边界：末步 contact 恰为 1.4×中位数（140 vs 100）→
    不识别（判据为严格大于，等于阈值不算）。"""
    steps = _make_steps([100.0] * 8 + [140.0])
    assert identify_takeoff_steps(steps) == []


def test_confidence_monotonic_and_clamped():
    """置信度随 contact 比值单调上升，并 clamp 到 [0, 1]：
    confidence = clamp(ratio / (2×contact_ratio_thr), 0, 1)。"""
    base = [100.0] * 8
    t170 = identify_takeoff_steps(_make_steps(base + [170.0]))[0]
    t280 = identify_takeoff_steps(_make_steps(base + [280.0]))[0]
    t560 = identify_takeoff_steps(_make_steps(base + [560.0]))[0]

    # 已知答案：ratio=1.7 → confidence = 1.7/2.8 ≈ 0.6071
    assert t170['confidence'] == pytest.approx(1.7 / 2.8, abs=1e-4)
    # 比值越大 → 置信度越高
    assert t280['confidence'] > t170['confidence']
    # ratio=2.8=2×阈值 → 恰好 1.0；ratio=5.6 → 饱和 clamp 到 1.0
    assert t280['confidence'] == pytest.approx(1.0)
    assert t560['confidence'] == 1.0
    assert all(0.0 <= t['confidence'] <= 1.0
               for t in (t170, t280, t560))
