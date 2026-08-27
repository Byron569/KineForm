"""步态事件检测（Zeni 方法）与时空参数计算测试。

合成数据：30 fps、周期 60 帧（2.0s/步态周期）的三角余弦摆动信号，
支撑期 9 帧（0.3s）、摆动期 51 帧（1.7s）——
- 左脚 TD 在 0, 60, 120, ...（数组内部峰：60, 120, 180, 240, 300）
- 左脚 TO 在 9, 69, 129, ...
- 右脚整体相位偏移 30 帧（TD 在 30, 90, ...）

已知答案：触地时间 = 9 帧 = 300ms，步态周期 = 60 帧 = 2000ms，
步时间 = 30 帧 = 1000ms → 步频 = 60 spm。
"""
import json

import numpy as np
import pytest

from app.common.data_models import Event, MetricsResult
from app.events.detector import EVENT_DETECTORS, detect_events
from app.events.gait import (
    _detect_gait_contact_events,
    gait_step_features,
    gait_temporal_params,
)
from app.exporters.writers import export_events_json

FPS = 30.0
CYCLE = 60          # 帧/步态周期
STANCE = 9          # 帧/支撑期
N_FRAMES = 360      # 6 个周期
A = 60.0            # 摆动信号幅值（px）


def _swing_signal(t: np.ndarray, phase_offset: int) -> np.ndarray:
    """相位扭曲余弦：支撑期 [TD, TD+9] 从 +A 降到 -A，
    摆动期 [TD+9, TD+60] 从 -A 回升到 +A。关节处导数连续为 0。"""
    sig = np.empty_like(t, dtype=float)
    tt = (t + phase_offset) % CYCLE
    stance_mask = tt < STANCE
    # 支撑期：phase 0→π
    sig[stance_mask] = A * np.cos(np.pi * tt[stance_mask] / STANCE)
    # 摆动期：phase 0→π
    sw = tt[~stance_mask] - STANCE
    sig[~stance_mask] = -A * np.cos(np.pi * sw / (CYCLE - STANCE))
    return sig


def _make_metrics(n_frames: int = N_FRAMES, drift: float = 2.0):
    """构造带骨盆漂移（向右跑）的合成 MetricsResult。"""
    t = np.arange(n_frames, dtype=float)
    pelvis_x = 100.0 + drift * t
    pelvis_y = 500.0 + np.zeros(n_frames)
    l_heel_x = pelvis_x + _swing_signal(t, 0)
    r_heel_x = pelvis_x + _swing_signal(t, CYCLE // 2)
    ts = t * 1000.0 / FPS

    n = n_frames
    trajectories = {
        'pelvis': np.stack([pelvis_x, pelvis_y], axis=1),
        'head': np.full((n, 2), np.nan),
        'left_heel': np.stack([l_heel_x, np.zeros(n)], axis=1),
        'right_heel': np.stack([r_heel_x, np.zeros(n)], axis=1),
    }
    return MetricsResult(
        fps=FPS,
        frame_indices=np.arange(n, dtype=np.int64),
        timestamps_ms=ts,
        angles={},
        angular_velocity={},
        torso_lean=np.full(n, np.nan),
        trajectories=trajectories,
        keypoint_speeds=np.full((n, 26), np.nan),
        pelvis_speed=np.full(n, np.nan),
        pose_quality=np.ones(n),
        valid_ratio=np.ones(n),
        missing_ratio=np.zeros(n),
        symmetry_index={},
    )


def _within_one(actual: list[int], expected: list[int]) -> bool:
    """逐项比较：检测位置允许 ±1 帧滤波容差，数量与顺序一致。"""
    if len(actual) != len(expected):
        return False
    return all(abs(a - e) <= 1 for a, e in zip(actual, expected))


def test_zeni_detects_touchdown_and_toe_off_frames():
    """Zeni 判据：左脚 TD=60/120/180/240/300，TO=9/69/...；
    右脚相位偏移 30 帧。低通滤波允许 ±1 帧位置容差。"""
    metrics = _make_metrics()
    events = _detect_gait_contact_events(metrics, ['ok'] * N_FRAMES)

    td_l = sorted(e.frame_index for e in events if e.type == 'left_touchdown')
    to_l = sorted(e.frame_index for e in events if e.type == 'left_toe_off')
    td_r = sorted(e.frame_index for e in events if e.type == 'right_touchdown')

    # 左脚：数组内部峰从 60 开始（0 与 360 是边界，find_peaks 不检出）
    assert _within_one(td_l, [60, 120, 180, 240, 300])
    assert _within_one(to_l, [9, 69, 129, 189, 249, 309])
    # 右脚 = 左脚 + 30（30/90/.../330 均为内部峰，共 6 个）
    assert _within_one(td_r, [30, 90, 150, 210, 270, 330])
    # 置信度在 (0, 1]
    assert all(0.0 < e.confidence <= 1.0 for e in events)


def _known_gait_events() -> list[Event]:
    """直接构造已知帧号的事件表（绕过检测器滤波，验证纯数学）。"""
    events: list[Event] = []
    for k in range(5):
        events.append(Event('left_touchdown', 60 + 60 * k,
                            (60 + 60 * k) * 1000 / FPS, 25.0, 'px', 0.9))
        events.append(Event('right_touchdown', 90 + 60 * k,
                            (90 + 60 * k) * 1000 / FPS, 24.0, 'px', 0.9))
    for k in range(6):
        events.append(Event('left_toe_off', 9 + 60 * k,
                            (9 + 60 * k) * 1000 / FPS, -20.0, 'px', 0.9))
        events.append(Event('right_toe_off', 39 + 60 * k,
                            (39 + 60 * k) * 1000 / FPS, -21.0, 'px', 0.9))
    return events


def test_gait_temporal_params_known_math():
    """已知答案：触地 300ms、腾空 1700ms、周期 2000ms、步频 60 spm。"""
    s = gait_temporal_params(_known_gait_events(), FPS)

    left = s['left']
    assert left['n_touchdowns'] == 5
    assert left['n_toe_offs'] == 6
    ct = left['contact_time_ms']
    assert ct['count'] == 5
    assert ct['mean'] == 300.0                 # 9 帧 @ 30fps
    assert ct['std'] == 0.0
    ft = left['flight_time_ms']
    assert ft['mean'] == 1700.0                # 51 帧
    st = left['stride_time_ms']
    assert st['mean'] == 2000.0                # 60 帧
    # 支撑比 = 9/60 = 15%（百分比，与 myogait stance_pct 约定一致）
    assert abs(left['stance_ratio']['mean'] - 15.0) < 1e-9
    assert abs(left['stance_ratio']['mean_frac'] - 0.15) < 1e-9
    # 全局步频：相邻 TD 间隔 30 帧 = 1s → 60 步/分
    assert s['step_time_ms']['mean'] == 1000.0
    assert s['cadence_spm'] == 60.0


def test_gait_detector_registered_and_integrated():
    """检测器已注册，detect_events 全流程能产出步态事件。"""
    assert 'gait_contact_events' in EVENT_DETECTORS
    metrics = _make_metrics()
    events = detect_events(metrics, ['ok'] * N_FRAMES)
    types = {e.type for e in events}
    assert 'left_touchdown' in types
    assert 'right_toe_off' in types


def test_gait_nan_and_empty_safe():
    """全 NaN 轨迹不产出事件、不崩溃；空事件表输出 None 字段。"""
    metrics = _make_metrics(n_frames=10)
    metrics.trajectories = {
        k: np.full((10, 2), np.nan) for k in metrics.trajectories}
    events = _detect_gait_contact_events(metrics, ['ok'] * 10)
    assert events == []

    s = gait_temporal_params([], FPS)
    assert s['left']['n_touchdowns'] == 0
    assert s['left']['contact_time_ms'] is None
    assert s['cadence_spm'] is None


def test_gait_left_walking_direction_flipped():
    """向左跑（骨盆 x 递减、脚在前方为负偏移）时信号翻转，
    TD/TO 判据与向右跑一致。"""
    metrics = _make_metrics(drift=-2.0)
    # 物理一致性：向左跑时脚在"前方"= x 更小 → 偏移信号取负
    t = np.arange(N_FRAMES, dtype=float)
    metrics.trajectories['left_heel'] = np.stack(
        [metrics.trajectories['pelvis'][:, 0] - _swing_signal(t, 0),
         np.zeros(N_FRAMES)], axis=1)
    events = _detect_gait_contact_events(metrics, ['ok'] * N_FRAMES)
    td_l = sorted(e.frame_index for e in events if e.type == 'left_touchdown')
    assert _within_one(td_l, [60, 120, 180, 240, 300])


def test_export_events_json_with_gait_summary(tmp_path):
    """events.json 增加 gait_summary 键（向后兼容：不传则无该键）。"""
    events = [Event('left_touchdown', 60, 2000.0, 25.3, 'px', 0.9)]
    summary = gait_temporal_params(events, FPS)

    p1 = tmp_path / 'a.json'
    export_events_json(p1, events, gait_summary=summary)
    d1 = json.loads(p1.read_text(encoding='utf-8'))
    assert 'gait_summary' in d1
    assert d1['gait_summary']['left']['n_touchdowns'] == 1

    p2 = tmp_path / 'b.json'
    export_events_json(p2, events)
    assert 'gait_summary' not in json.loads(p2.read_text(encoding='utf-8'))


# ---------------- 每步事件条件化特征 ----------------
def _make_step_metrics():
    """带已知角度/节段角/骨盆垂直振荡的左脚步态指标数据。

    支撑期 tt∈[0,9]：膝 150+10cos（TD=160°、TO/最小=140°），
    踝 120+5cos（TD=125°、最小 115°），髋恒 165°；
    摆动期：膝恒 60°，大腿角在 tt=30 处达 21°（最大抬腿）；
    骨盆 y 振荡 ±10px（周期 60 帧）→ 每周期垂直振幅 20px。
    """
    m = _make_metrics()
    tt = np.arange(N_FRAMES) % CYCLE
    stance = tt <= STANCE
    m.angles = {
        'left_knee': np.where(
            stance, 150.0 + 10.0 * np.cos(np.pi * tt / STANCE), 60.0),
        'left_hip': np.where(stance, 165.0, 140.0),
        'left_ankle': np.where(
            stance, 120.0 + 5.0 * np.cos(np.pi * tt / STANCE), 90.0),
        'left_elbow': np.where(stance, 69.0, 70.0),   # Hanley IC 肘角
    }
    thigh = np.full(N_FRAMES, -90.0)
    thigh[tt == 30] = 21.0                       # 最大抬腿（摆动期）
    m.segment_angles = {
        'left_thigh': thigh,
        'left_shank': np.where(stance, 5.0, 0.0),  # 支撑期前倾 5°
        # 肩角（Hanley 约定）：TD 同侧臂后摆 −47°（Hanley 男子 IC 参考）
        'left_shoulder': np.where(stance, -47.0, 10.0),
    }
    m.trajectories['pelvis'][:, 1] = (
        500.0 - 10.0 * np.cos(2 * np.pi * np.arange(N_FRAMES) / CYCLE))
    return m


def test_gait_step_features_known_values():
    """已知答案逐步校验（左脚第一步 TD=60/TO=69/下一TD=120）。"""
    steps = gait_step_features(_make_step_metrics(), _known_gait_events())
    assert len(steps) == 10                       # 左 5 步 + 右 5 步
    s0 = steps[0]                                 # 已按 td_frame 升序
    assert s0['side'] == 'left'
    assert s0['td_frame'] == 60
    assert s0['to_frame'] == 69
    assert s0['next_td_frame'] == 120
    assert s0['contact_time_ms'] == 300.0
    assert s0['flight_time_ms'] == 1700.0
    assert s0['stride_time_ms'] == 2000.0
    assert s0['stance_ratio'] == 0.15
    assert s0['flight_support_ratio'] == 5.67
    assert s0['pelvis_vertical_range_px'] == 20.0

    td = s0['touchdown']
    assert td['knee_angle'] == 160.0
    assert td['hip_angle'] == 165.0
    assert td['ankle_angle'] == 125.0
    assert td['thigh_angle'] == -90.0
    assert td['shank_angle'] == 5.0
    assert td['foot_pelvis_dist_px'] == 60.0
    assert td['torso_lean_angle'] is None         # 全 NaN → None

    ms = s0['midstance']
    assert ms['frame'] == 64                      # tt=4，|rel| 最小
    assert ms['knee_angle'] == pytest.approx(151.7, abs=0.1)

    to = s0['toe_off']
    assert to['knee_angle'] == 140.0
    assert to['ankle_angle'] == 115.0
    assert to['hip_angle'] == 165.0

    st = s0['stance']
    assert st['min_knee_angle'] == 140.0
    assert st['knee_collapse_deg'] == 20.0
    assert st['knee_rom_deg'] == 20.0
    assert st['ankle_rom_deg'] == 10.0
    assert st['hip_rom_deg'] == 0.0

    sw = s0['swing']
    assert sw['min_knee_angle'] == 60.0
    assert sw['max_thigh_angle'] == 21.0

    # 触地前 3 帧脚跟相对骨盆水平速度（后向差分均值）
    rel57 = -A * np.cos(np.pi * (57 - STANCE) / (CYCLE - STANCE))
    expected = (A - rel57) / 3 * FPS
    assert td['foot_rel_vx_px_s'] == pytest.approx(expected, abs=0.1)

    # 右侧无角度数据 → 角度字段 None，时序字段仍在
    s_r = next(s for s in steps if s['side'] == 'right')
    assert s_r['touchdown']['knee_angle'] is None
    assert s_r['contact_time_ms'] == 300.0


def test_gait_step_features_missing_angles_and_empty():
    """旧 MetricsResult（无角度）安全降级；空事件表返回空。"""
    steps = gait_step_features(_make_metrics(), _known_gait_events())
    assert len(steps) == 10
    assert steps[0]['touchdown']['knee_angle'] is None
    assert steps[0]['stance']['min_knee_angle'] is None
    assert steps[0]['midstance'] is not None     # 仅依赖轨迹
    assert steps[0]['contact_time_ms'] == 300.0
    assert gait_step_features(_make_metrics(), []) == []


def test_gait_step_features_leftward_direction():
    """左向跑：foot_pelvis_dist / thigh / shank / shoulder 按行进方向翻转。"""
    m = _make_metrics(drift=-2.0)
    t = np.arange(N_FRAMES, dtype=float)
    m.trajectories['left_heel'] = np.stack(
        [m.trajectories['pelvis'][:, 0] - _swing_signal(t, 0),
         np.zeros(N_FRAMES)], axis=1)
    tt = np.arange(N_FRAMES) % CYCLE
    stance = tt <= STANCE
    m.angles = {'left_knee': np.where(stance, 160.0, 60.0)}
    thigh = np.full(N_FRAMES, -90.0)
    thigh[tt == 30] = 180.0 - 21.0               # 左向跑最大抬腿原始角
    m.segment_angles = {'left_thigh': thigh,
                        'left_shank': np.where(stance, -5.0, 0.0),
                        # 左向跑臂后摆 = 指向 +x → 原始角为正
                        'left_shoulder': np.where(stance, 47.0, -10.0)}
    steps = gait_step_features(m, _known_gait_events())
    s0 = next(s for s in steps if s['side'] == 'left')
    assert s0['touchdown']['foot_pelvis_dist_px'] == 60.0
    assert s0['touchdown']['shank_angle'] == 5.0
    assert s0['swing']['max_thigh_angle'] == pytest.approx(21.0, abs=0.1)
    # 翻转后：TD 同侧臂后摆 → −47°（Hanley 约定一致）
    assert s0['touchdown']['shoulder_angle'] == -47.0


def test_gait_step_features_shoulder_elbow_and_scale():
    """肩/肘快照（Hanley 约定）+ 尺度归一化字段。

    骨盆漂移 2px/帧 × 60 帧周期 → 步长 120px；
    body_height 500px → norm 0.24；m_per_px 0.0036 → 0.432 m。
    """
    m = _make_step_metrics()
    bs = {'body_height_px': 500.0, 'leg_length_px': 200.0,
          'm_per_px': 0.0036}
    steps = gait_step_features(m, _known_gait_events(), body_scale=bs)
    s0 = steps[0]

    # 肩（−47° 后摆）/ 肘（69°）快照
    assert s0['touchdown']['shoulder_angle'] == -47.0
    assert s0['touchdown']['elbow_angle'] == 69.0
    assert s0['toe_off']['elbow_angle'] == 69.0
    assert s0['midstance']['shoulder_angle'] == -47.0

    # 步长与归一化
    assert s0['stride_length_px'] == 120.0        # 2px/帧 × 60 帧
    assert s0['stride_length_norm'] == pytest.approx(0.24)
    assert s0['stride_length_m'] == pytest.approx(0.432, abs=0.001)
    assert s0['touchdown']['foot_pelvis_dist_norm'] == pytest.approx(0.12)
    assert s0['pelvis_vertical_range_norm'] == pytest.approx(0.04)

    # 不传 body_scale → norm 字段为 None，px 值仍在
    s_no = gait_step_features(m, _known_gait_events())[0]
    assert s_no['stride_length_norm'] is None
    assert s_no['stride_length_px'] == 120.0
    assert s_no['stride_length_m'] is None
    assert s_no['touchdown']['foot_pelvis_dist_norm'] is None
