"""精英参考数据库与 z-score 对比测试。"""
import pytest

from app.biomechanics.references import (
    AUTO_COMPARE_REFS, ELITE_REFERENCES, compare_steps_to_reference,
    z_band)


def test_database_integrity():
    """每条参考库必含 source/sample/angle_definition；
    指标条目必含 mean；SD 为正或 None；可比性标志存在。"""
    assert set(AUTO_COMPARE_REFS) <= set(ELITE_REFERENCES)
    for key, ref in ELITE_REFERENCES.items():
        assert ref['source'] and ref['sample'] and ref['angle_definition'], key
        for group in ('step_metrics', 'global_metrics'):
            for path, e in ref[group].items():
                assert isinstance(e['mean'], (int, float)), (key, path)
                assert e['sd'] is None or e['sd'] > 0
                assert isinstance(e['comparable'], bool)


def test_z_band_boundaries():
    assert z_band(0.0) == 'common'
    assert z_band(1.0) == 'common'          # |z|≤1 含边界
    assert z_band(-1.0) == 'common'
    assert z_band(1.01) == 'deviated'
    assert z_band(-1.5) == 'deviated'
    assert z_band(2.0) == 'deviated'        # |z|≤2 含边界
    assert z_band(2.01) == 'outlier'
    assert z_band(-3.0) == 'outlier'


def _step(knee_td=156.0, contact_ms=96.0, side='left', td_frame=60):
    return {
        'side': side,
        'td_frame': td_frame,
        'contact_time_ms': contact_ms,
        'touchdown': {'knee_angle': knee_td},
    }


def test_compare_z_score_math():
    """z = (值−均值)/SD：knee=168 → z=2 deviated（|z|≤2 边界含）；
    159 → 0.5 common；169 → 2.17 outlier。"""
    out = compare_steps_to_reference([_step(knee_td=168.0)],
                                     'sprint_max_v')
    m = out['steps'][0]['metrics']['touchdown.knee_angle']
    assert m['z'] == pytest.approx(2.0)
    assert m['band'] == 'deviated'

    out = compare_steps_to_reference([_step(knee_td=159.0)],
                                     'sprint_max_v')
    m = out['steps'][0]['metrics']['touchdown.knee_angle']
    assert m['z'] == pytest.approx(0.5)
    assert m['band'] == 'common'

    out = compare_steps_to_reference([_step(knee_td=169.0)],
                                     'sprint_max_v')
    m = out['steps'][0]['metrics']['touchdown.knee_angle']
    assert m['z'] == pytest.approx(2.17, abs=0.01)
    assert m['band'] == 'outlier'


def test_compare_band_edges_and_summary():
    """z=1 → common；side_summary 为同侧均值 z。"""
    steps = [_step(knee_td=162.0, td_frame=60),   # z=1 → common
             _step(knee_td=165.0, td_frame=120)]  # z=1.5 → deviated
    out = compare_steps_to_reference(steps, 'sprint_max_v')
    assert out['steps'][0]['metrics']['touchdown.knee_angle']['band'] == 'common'
    assert out['steps'][1]['metrics']['touchdown.knee_angle']['band'] == 'deviated'
    s = out['side_summary']['left']['touchdown.knee_angle']
    assert s['mean_z'] == pytest.approx(1.25)
    assert s['band'] == 'deviated'
    assert s['n'] == 2


def test_compare_non_comparable_skipped():
    """马拉松踝角（定义不同）不进入 metrics，登记 skipped_metrics。"""
    step = _step()
    step['touchdown']['ankle_angle'] = 95.0
    out = compare_steps_to_reference([step], 'marathon_m')
    assert 'touchdown.ankle_angle' not in out['steps'][0]['metrics']
    assert 'touchdown.ankle_angle' in out['skipped_metrics']
    assert '110' in out['skipped_metrics']['touchdown.ankle_angle']


def test_compare_value_only_when_no_sd():
    """无 SD（马拉松髋角）→ z/band 为 None，参考值与实测值仍在。"""
    step = _step()
    step['touchdown']['hip_angle'] = 151.0
    out = compare_steps_to_reference([step], 'marathon_m')
    m = out['steps'][0]['metrics']['touchdown.hip_angle']
    assert m['z'] is None and m['band'] is None
    assert m['ref_mean'] == 143          # 马拉松男子 TD 髋参考
    assert m['value'] == 151
    assert 'touchdown.knee_angle' in out['steps'][0]['metrics']


def test_compare_global_cadence():
    """全局步频对比：4.9 Hz → z≈1.55 → deviated；未提供时不输出。"""
    out = compare_steps_to_reference([_step()], 'sprint_max_v',
                                     cadence_hz=4.9)
    g = out['global']['cadence_hz']
    assert g['z'] == pytest.approx(1.55, abs=0.01)
    assert g['band'] == 'deviated'

    out2 = compare_steps_to_reference([_step()], 'sprint_max_v')
    assert 'cadence_hz' not in out2['global']


def test_compare_safety():
    """空步列表安全；未知参考库抛 ValueError；缺失指标静默跳过。"""
    out = compare_steps_to_reference([], 'sprint_max_v')
    assert out['steps'] == [] and out['side_summary'] == {}
    with pytest.raises(ValueError):
        compare_steps_to_reference([], 'no_such_ref')
    out2 = compare_steps_to_reference([{'side': 'left', 'td_frame': 1}],
                                      'sprint_max_v')
    assert out2['steps'][0]['metrics'] == {}


def test_high_jump_and_800m_not_auto():
    """跳高/800m 参考库存在但不自动比较（auto_compare=False）。"""
    assert 'hj_takeoff_success' in ELITE_REFERENCES
    assert 'hj_takeoff_success' not in AUTO_COMPARE_REFS
    assert 'marathon_800m_f' not in AUTO_COMPARE_REFS
    assert ELITE_REFERENCES['hj_takeoff_success']['context']
