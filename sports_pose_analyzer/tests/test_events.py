"""事件检测单元测试（无 GPU 依赖）。"""
import numpy as np
import pytest

from app.common.data_models import ANGLE_KEYS, MetricsResult
from app.events.detector import detect_events


def _make_metrics(n=100, fps=25.0, angles=None, torso_lean=None,
                  pelvis_y=None, angular_velocity=None, pose_quality=None):
    """构造测试用 MetricsResult；未显式指定的序列使用安全默认值。"""
    if angles is None:
        angles = {k: np.full(n, 170.0) for k in ANGLE_KEYS}
    if torso_lean is None:
        torso_lean = np.zeros(n)
    if angular_velocity is None:
        angular_velocity = {k: np.zeros(n) for k in ANGLE_KEYS}
    y = 400.0 if pelvis_y is None else pelvis_y
    traj = {'pelvis': np.column_stack([np.full(n, 320.0), np.full(n, y)]),
            'head': np.zeros((n, 2)),
            'left_heel': np.zeros((n, 2)),
            'right_heel': np.zeros((n, 2))}
    return MetricsResult(
        fps=fps,
        frame_indices=np.arange(n),
        timestamps_ms=np.arange(n) / fps * 1000.0,
        angles=angles,
        angular_velocity=angular_velocity,
        torso_lean=torso_lean,
        trajectories=traj,
        keypoint_speeds=np.zeros((n, 26)),
        pelvis_speed=np.zeros(n),
        pose_quality=np.full(n, 0.8) if pose_quality is None else pose_quality,
        valid_ratio=np.ones(n),
        missing_ratio=np.zeros(n),
        symmetry_index={})


def test_sine_knee_angle_minima_frames():
    """正弦角度序列：极小值事件帧号正确（周期 40 → 极小在 30/70/110）。"""
    n = 120
    t = np.arange(n)
    sine = 90.0 + 40.0 * np.sin(2.0 * np.pi * t / 40.0)
    angles = {k: np.full(n, 170.0) for k in ANGLE_KEYS}
    angles['left_knee'] = sine
    metrics = _make_metrics(n=n, angles=angles)
    events = detect_events(metrics, ['ok'] * n)

    knee = [e for e in events if e.type == 'min_left_knee_angle']
    frames = sorted(e.frame_index for e in knee)
    assert frames == [30, 70, 110]           # sin=-1 处：t = 30 + 40k
    for e in knee:
        assert e.unit == 'degree'
        assert e.value == pytest.approx(50.0)     # 90 - 40
        assert e.timestamp_ms == pytest.approx(e.frame_index / 25.0 * 1000.0)
        assert e.confidence == pytest.approx(0.8)
    # 结果按 frame_index 升序
    all_frames = [e.frame_index for e in events]
    assert all_frames == sorted(all_frames)


def test_global_minimum_not_duplicated_when_already_peak():
    """全局极小已在峰值列表中 → 不重复追加（同 type+帧只有一个）。"""
    n = 60
    t = np.arange(n)
    sine = 90.0 + 40.0 * np.sin(2.0 * np.pi * t / 60.0)   # 唯一极小在 t=45
    angles = {k: np.full(n, 170.0) for k in ANGLE_KEYS}
    angles['left_knee'] = sine
    events = detect_events(_make_metrics(n=n, angles=angles), ['ok'] * n)
    knee = [e for e in events if e.type == 'min_left_knee_angle']
    assert len(knee) == 1
    assert knee[0].frame_index == 45


def test_pose_lost_start_end_frames():
    """ok→非 ok 为 start，非 ok→ok 为 end，帧号与属性正确。"""
    n = 8
    metrics = _make_metrics(n=n)
    statuses = ['ok', 'ok', 'person_not_found', 'person_not_found', 'ok',
                'low_pose_confidence', 'ok', 'ok']
    events = detect_events(metrics, statuses)
    starts = [e.frame_index for e in events if e.type == 'pose_lost_start']
    ends = [e.frame_index for e in events if e.type == 'pose_lost_end']
    assert starts == [2, 5]     # 1→2 ok→丢失；4→5 ok→低置信度
    assert ends == [4, 6]       # 3→4 丢失→ok；5→6 低置信度→ok
    for e in events:
        if e.type in ('pose_lost_start', 'pose_lost_end'):
            assert e.value == 0.0
            assert e.unit == 'frame'


def test_duplicate_type_frame_deduplicated():
    """两条角速度序列全局最大同帧 → 同 (type, frame) 只留一个。"""
    n = 30
    av = {k: np.zeros(n) for k in ANGLE_KEYS}
    av['left_knee'][10] = 300.0
    av['right_knee'][10] = 280.0
    events = detect_events(_make_metrics(n=n, angular_velocity=av), ['ok'] * n)
    dup = [e for e in events
           if e.type == 'max_joint_angular_velocity' and e.frame_index == 10]
    assert len(dup) == 1
    assert dup[0].value == pytest.approx(300.0)   # 保留先产出的 left_knee
    assert dup[0].unit == 'deg/s'


def test_constant_series_does_not_crash():
    """恒定序列（std=0）不崩溃：无局部峰值，仅保留全局极值事件。"""
    n = 50
    events = detect_events(_make_metrics(n=n), ['ok'] * n)
    types = {e.type for e in events}
    assert 'min_left_knee_angle' in types        # 全局最小帧事件仍存在
    # 任意 (type, frame_index) 至多一个
    seen = set()
    for e in events:
        assert (e.type, e.frame_index) not in seen
        seen.add((e.type, e.frame_index))


def test_event_confidence_clamp_and_nan():
    """confidence = pose_quality clamp(0,1)，NaN → 0。"""
    n = 10
    pq = np.full(n, 0.8)
    pq[2] = 1.5        # 超上界 → 1.0
    pq[5] = np.nan     # → 0.0
    statuses = ['ok', 'ok', 'person_not_found', 'ok', 'ok',
                'person_not_found', 'ok', 'ok', 'ok', 'ok']
    events = detect_events(_make_metrics(n=n, pose_quality=pq), statuses)
    by_key = {(e.type, e.frame_index): e for e in events}
    assert by_key[('pose_lost_start', 2)].confidence == pytest.approx(1.0)
    assert by_key[('pose_lost_start', 5)].confidence == pytest.approx(0.0)


def test_all_nan_series_skipped():
    """全 NaN 序列安全跳过（不崩溃、不产生对应事件）。"""
    n = 40
    angles = {k: np.full(n, np.nan) for k in ANGLE_KEYS}
    metrics = _make_metrics(n=n, angles=angles,
                            torso_lean=np.full(n, np.nan))
    events = detect_events(metrics, ['ok'] * n)
    types = {e.type for e in events}
    assert 'min_left_knee_angle' not in types
    assert 'max_torso_lean' not in types


def test_partial_nan_series_safe():
    """含 NaN 缺口的序列：缺口外极小值仍被检出，全程不崩溃。"""
    n = 120
    t = np.arange(n)
    sine = 90.0 + 40.0 * np.sin(2.0 * np.pi * t / 40.0)
    sine[60:68] = np.nan                      # 中段挖 8 帧缺口
    angles = {k: np.full(n, 170.0) for k in ANGLE_KEYS}
    angles['left_knee'] = sine
    events = detect_events(_make_metrics(n=n, angles=angles), ['ok'] * n)
    knee = sorted(e.frame_index for e in events
                  if e.type == 'min_left_knee_angle')
    assert 30 in knee and 110 in knee         # 缺口两侧的极小仍在


def test_pelvis_height_events():
    """骨盆 y 局部极小=最高、局部极大=最低，unit='px'。"""
    n = 60
    t = np.arange(n)
    y = 400.0 + 30.0 * np.sin(2.0 * np.pi * t / 60.0)   # y 最小在 t=45
    events = detect_events(_make_metrics(n=n, pelvis_y=y), ['ok'] * n)
    top = [e for e in events if e.type == 'max_pelvis_height']
    bottom = [e for e in events if e.type == 'min_pelvis_height']
    assert [e.frame_index for e in top] == [45]
    assert [e.frame_index for e in bottom] == [15]
    assert all(e.unit == 'px' for e in top + bottom)
    assert top[0].value == pytest.approx(370.0)
    assert bottom[0].value == pytest.approx(430.0)


def test_max_torso_lean_event():
    """|躯干倾角| 局部极大 + 全局最大，unit='degree'，value 取幅值。"""
    n = 60
    t = np.arange(n)
    lean = 20.0 * np.sin(2.0 * np.pi * t / 60.0)   # 峰 ±20 在 t=15/45
    events = detect_events(_make_metrics(n=n, torso_lean=lean), ['ok'] * n)
    tl = sorted(e.frame_index for e in events if e.type == 'max_torso_lean')
    assert tl == [15, 45]
    for e in events:
        if e.type == 'max_torso_lean':
            assert e.unit == 'degree'
            assert e.value == pytest.approx(20.0)  # 取 |lean| 幅值
