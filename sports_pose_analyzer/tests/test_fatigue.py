"""疲劳趋势分析（前/后半程每步特征对比）测试。

合成数据：10 步已知特征——前 5 步（前半程，未疲劳）
contact_time_ms=100、swing.min_knee_angle=50；后 5 步（后半程，
疲劳）contact_time_ms=115、swing.min_knee_angle=55——模拟
Hanley 2020 马拉松疲劳现象（疲劳后触地时间延长、midswing
最小膝角后程增加约 5°，见 references.py marathon_m 条目）。

已知答案：first/second 触地均值 100.0/115.0（delta=15.0、
delta_pct=15%）；摆动期最小膝角 50.0/55.0（delta=5.0、10%）。
"""
import inspect

from app.events.fatigue import fatigue_trend

_ALL_METRICS = {
    'contact_time_ms', 'flight_time_ms', 'stride_time_ms',
    'stance_ratio', 'pelvis_vertical_range_px', 'stride_length_px',
    'touchdown.knee_angle', 'stance.min_knee_angle',
    'stance.knee_collapse_deg', 'swing.min_knee_angle',
    'swing.max_thigh_angle', 'touchdown.shoulder_angle',
}


def _make_steps(n: int = 10, contact=(100, 115),
                swing_knee=(50, 55)) -> list[dict]:
    """n 步最小 step dict：前半用各元组第 0 个值、后半用第 1 个值；
    td_frame 递增模拟时间推进（对半分界 = (n+1)//2）。"""
    half = (n + 1) // 2
    return [{
        'side': 'left',
        'td_frame': 30 * i,
        'contact_time_ms': contact[0] if i < half else contact[1],
        'swing': {
            'min_knee_angle': swing_knee[0] if i < half else swing_knee[1],
        },
    } for i in range(n)]


def test_fatigue_known_values():
    """10 步对半分（5/5）：触地 100→115（+15.0ms / +15%）、
    摆动期最小膝角 50→55（+5.0° / +10%，Hanley 疲劳现象）。"""
    r = fatigue_trend(_make_steps())

    assert r['n_steps'] == 10
    assert r['split_at'] == 5
    assert r['halves']['first']['contact_time_ms'] == 100.0
    assert r['halves']['second']['contact_time_ms'] == 115.0
    assert r['delta']['contact_time_ms'] == 15.0
    assert r['delta_pct']['contact_time_ms'] == 15.0

    assert r['halves']['first']['swing.min_knee_angle'] == 50.0
    assert r['halves']['second']['swing.min_knee_angle'] == 55.0
    assert r['delta']['swing.min_knee_angle'] == 5.0
    assert r['delta_pct']['swing.min_knee_angle'] == 10.0


def test_fatigue_all_metric_keys_present():
    """halves 两半均包含全部 12 个指标键（无数据为 None，含嵌套
    子字典整体缺失的情形）；delta/delta_pct 仅含有数据的指标。"""
    r = fatigue_trend(_make_steps())

    assert set(r['halves']['first']) == _ALL_METRICS
    assert set(r['halves']['second']) == _ALL_METRICS
    # 合成数据仅有 2 个指标有值（其余键不存在 → None）
    assert r['halves']['first']['stance.min_knee_angle'] is None
    assert r['halves']['second']['stride_length_px'] is None
    assert set(r['delta']) == {'contact_time_ms', 'swing.min_knee_angle'}
    assert set(r['delta_pct']) == {'contact_time_ms', 'swing.min_knee_angle'}


def test_fatigue_too_few_steps_returns_none():
    """步数 < min_steps（默认 6）→ None；空列表 → None；
    恰好达 min_steps 或显式放宽阈值均可分析。"""
    assert fatigue_trend(_make_steps(n=5)) is None
    assert fatigue_trend([]) is None
    assert fatigue_trend(_make_steps(n=6)) is not None
    assert fatigue_trend(_make_steps(n=5), min_steps=5) is not None


def test_fatigue_missing_values_skipped():
    """None 指标值安全跳过：均值仅基于有效样本（两半各 3/4 步有效），
    结果与无缺失时一致；某指标两半都无数据 → None 且不进 delta。"""
    steps = _make_steps()
    for i in (1, 2, 6):                          # 前 5 步缺 2、后 5 步缺 1
        steps[i]['contact_time_ms'] = None
    steps[3]['swing']['min_knee_angle'] = None   # 嵌套值缺失同理

    r = fatigue_trend(steps)
    assert r['halves']['first']['contact_time_ms'] == 100.0   # 3 个有效
    assert r['halves']['second']['contact_time_ms'] == 115.0  # 4 个有效
    assert r['delta']['contact_time_ms'] == 15.0
    assert r['halves']['first']['swing.min_knee_angle'] == 50.0
    # 两半都无数据（合成数据本就不含该键）
    assert r['halves']['first']['flight_time_ms'] is None
    assert r['halves']['second']['flight_time_ms'] is None
    assert 'flight_time_ms' not in r['delta']
    assert 'flight_time_ms' not in r['delta_pct']


def test_fatigue_one_half_only_no_delta():
    """仅单半有数据的指标：该半出均值、另一半 None，不进入
    delta/delta_pct（delta 需两半均有值）。"""
    steps = _make_steps()
    for i, s in enumerate(steps):
        s['flight_time_ms'] = 90.0 if i >= 5 else None

    r = fatigue_trend(steps)
    assert r['halves']['first']['flight_time_ms'] is None
    assert r['halves']['second']['flight_time_ms'] == 90.0
    assert 'flight_time_ms' not in r['delta']
    assert 'flight_time_ms' not in r['delta_pct']


def test_fatigue_odd_split_first_half_longer():
    """7 步 → 前半 4 步、后半 3 步（split_at=4，奇数时前半多一步）。"""
    r = fatigue_trend(_make_steps(n=7))
    assert r['n_steps'] == 7
    assert r['split_at'] == 4
    assert r['halves']['first']['contact_time_ms'] == 100.0   # 步 0-3
    assert r['halves']['second']['contact_time_ms'] == 115.0  # 步 4-6


def test_fatigue_sorts_by_td_frame():
    """输入乱序：内部按 td_frame 升序后再对半，与有序输入结果一致。"""
    r = fatigue_trend(list(reversed(_make_steps())))
    assert r['split_at'] == 5
    assert r['halves']['first']['contact_time_ms'] == 100.0
    assert r['halves']['second']['contact_time_ms'] == 115.0
    assert r['delta']['contact_time_ms'] == 15.0


def test_fatigue_module_no_heavy_imports():
    """模块源码不依赖 torch/cv2（纯 numpy/标准库，
    CPU-only 环境可导入）。"""
    import app.events.fatigue as fatigue_module
    src = inspect.getsource(fatigue_module)
    assert 'import torch' not in src
    assert 'import cv2' not in src
