"""精英参考数据库与逐指标 z-score 对比（纯标准库，无 numpy 依赖）。

数据来源：项目研究报告 1/2/3（D:\\KineForm\\docs_extracted.txt、
研究报告_运动姿态评价体系.md）中的世界级/精英运动员实测值。

科学立场（报告 1 核心结论）：
- 不存在"某角度达到 X° 即好/坏"的通用标准；参考分布必须
  绑定 项目×阶段×人群条件，且仅用于相近条件比较；
- z 分层（±1 SD / ±2 SD）是工程统计约定，不是官方合格阈值；
- 二维未标定投影角与文献（部分为 3D/高速视频）对比存在投影
  误差，结果定位为"参考性提示"而非诊断。

可比性登记（angle_definition 必须随数据保存）：
- 膝/髋（短跑、跳高、马拉松）：三方均为"伸直≈180°"的矢状面
  节段夹角，与本项目 halpe26.ANGLE_DEFS 一致 → 可比；
- 肩（Hanley 解剖约定 0°=下垂）：本项目 segment_angles 已采用
  同一约定 → 可比；肘（伸直≈180°）→ 可比；
- 马拉松踝角：Hanley 站立参考 ≈110°，本项目 knee-ankle-toe
  站立 ≈90°，定义不同 → 标记不可比（不参与 z 计算）；
- 跳高踝角（WA 报告）：定义未在提取文本中明确 → 保守标记不可比。

仅报告"均值/范围"而无 SD 的文献值（马拉松事件角）：只输出
参考值与偏差方向，不计算 z（诚实原则，不伪造精度）。
"""
from __future__ import annotations

import math

__all__ = [
    'ELITE_REFERENCES',
    'AUTO_COMPARE_REFS',
    'z_band',
    'compare_steps_to_reference',
]


def _m(mean, sd=None, lo=None, hi=None, comparable=True, note=''):
    """构造单条参考指标：{mean, sd, range, comparable, note}。"""
    return {
        'mean': mean,
        'sd': sd,
        'range': [lo, hi] if lo is not None else None,
        'comparable': comparable,
        'note': note,
    }


_NC_ANKLE = '角度定义不同（Hanley 站立≈110° vs 本项目≈90°），不可直接比较'


# ---------------------------------------------------------------- 数据库
ELITE_REFERENCES: dict[str, dict] = {
    # ---- 短跑最大速度（Mattes 2021，26 名德国精英男子，10.6±0.4 m/s） ----
    'sprint_max_v': {
        'source': 'Mattes et al. 2021, J Human Kinetics (PMC8008308)',
        'sample': '26 名高水平男子短跑运动员，最大速度 10.6±0.4 m/s',
        'angle_definition': '矢状面节段夹角，伸直≈180°；'
                            '大腿角相对水平（与本项目定义一致）',
        'step_metrics': {
            'touchdown.hip_angle': _m(147, 8),
            'touchdown.knee_angle': _m(156, 6),
            'touchdown.ankle_angle': _m(127, 7),
            'toe_off.hip_angle': _m(181, 5),
            'toe_off.knee_angle': _m(155, 7),
            'toe_off.ankle_angle': _m(147, 7),
            'swing.min_knee_angle': _m(40, 8),
            'swing.max_thigh_angle': _m(21, 4),
            'contact_time_ms': _m(96, 7),
            'flight_time_ms': _m(124, 7),
        },
        'global_metrics': {
            'cadence_hz': _m(4.56, 0.22),
        },
    },

    # ---- 马拉松男子（Hanley 2020，世锦赛 28 男） ----
    'marathon_m': {
        'source': 'Hanley et al. 2020, Front Sports Act Living '
                  '(fspor.2020.00102)',
        'sample': '2017 世锦赛马拉松 28 名男子（29.5/40 km，50 Hz）',
        'angle_definition': '髋=躯干-大腿 180°站立；膝=大腿-小腿 180°站立；'
                            '肩=解剖约定 0°站立（本项目已采用）；'
                            '肘=伸直 180°；踝=站立≈110°（与本项目不同）',
        'step_metrics': {
            'touchdown.hip_angle': _m(143, None, 142, 144),
            'touchdown.knee_angle': _m(149, None),
            'touchdown.ankle_angle': _m(102.5, None, 102, 103,
                                        comparable=False, note=_NC_ANKLE),
            'touchdown.shoulder_angle': _m(-47.5, None, -48, -47),
            'touchdown.elbow_angle': _m(69, None, 68, 70),
            'midstance.hip_angle': _m(151, None),
            'midstance.knee_angle': _m(131, None),
            'midstance.ankle_angle': _m(82, None, comparable=False,
                                        note=_NC_ANKLE),
            'midstance.shoulder_angle': _m(-26, None),
            'midstance.elbow_angle': _m(71, None),
            'toe_off.hip_angle': _m(192, None),
            'toe_off.knee_angle': _m(163, None),
            'toe_off.ankle_angle': _m(127, None, comparable=False,
                                       note=_NC_ANKLE),
            'toe_off.shoulder_angle': _m(27, None),
            'toe_off.elbow_angle': _m(55, None),
            'swing.min_knee_angle': _m(50, 6,
                                        note='前半程值；后半程 ≈55±7（疲劳）'),
        },
        'global_metrics': {},
    },

    # ---- 马拉松女子（Hanley 2020，世锦赛 28 女） ----
    'marathon_f': {
        'source': 'Hanley et al. 2020, Front Sports Act Living '
                  '(fspor.2020.00102)',
        'sample': '2017 世锦赛马拉松 28 名女子（29.5/40 km，50 Hz）',
        'angle_definition': '同 marathon_m',
        'step_metrics': {
            'touchdown.hip_angle': _m(145.5, None, 145, 146),
            'touchdown.knee_angle': _m(148, None),
            'touchdown.ankle_angle': _m(98.5, None, 98, 99,
                                        comparable=False, note=_NC_ANKLE),
            'touchdown.shoulder_angle': _m(-50.5, None, -51, -50),
            'touchdown.elbow_angle': _m(66, None),
            'midstance.hip_angle': _m(152, None),
            'midstance.knee_angle': _m(131, None),
            'midstance.ankle_angle': _m(81, None, comparable=False,
                                        note=_NC_ANKLE),
            'midstance.shoulder_angle': _m(-28, None),
            'midstance.elbow_angle': _m(72, None),
            'toe_off.hip_angle': _m(191, None),
            'toe_off.knee_angle': _m(160, None),
            'toe_off.ankle_angle': _m(124, None, comparable=False,
                                       note=_NC_ANKLE),
            'toe_off.shoulder_angle': _m(27, None),
            'toe_off.elbow_angle': _m(58, None),
            'swing.min_knee_angle': _m(63, 10,
                                        note='前半程值；后半程 ≈65±11'),
        },
        'global_metrics': {},
    },

    # ---- 跳高起跳（Nicholson 2024 成功/失败对照；不自动比较） ----
    'hj_takeoff_success': {
        'source': 'Nicholson et al. 2024, Front Sports Act Living '
                  '(fspor.2024.1352725)',
        'sample': '2018 世界室内锦标赛男子跳高，同一运动员同高度成功尝试',
        'angle_definition': '膝角 180°=伸直（与本项目一致）；'
                            '值为 3D 高速摄像结果，2D 对比存在投影误差',
        'auto_compare': False,
        'context': '跳高起跳步——需先从步态序列中识别起跳步'
                   '（触地时间显著更长 + 其后无同侧触地），暂不自动比较',
        'step_metrics': {
            'touchdown.knee_angle': _m(162.77, 5.69),
            'stance.min_knee_angle': _m(140.22, 6.96),
            'toe_off.knee_angle': _m(170.53, 5.47),
            'contact_time_ms': _m(169, None, 140, 190,
                                  note='WA2017 决赛范围 0.14–0.19 s'),
        },
        'global_metrics': {},
    },

    # ---- 800m 女子（Hanley 2022；分段条件化，不自动比较） ----
    'marathon_800m_f': {
        'source': 'Hanley et al. 2022, Front Sports Act Living '
                  '(fspor.2022.834813)',
        'sample': '2017 世锦赛女子 800 m 决赛 8 人（150 Hz，350/750 m）',
        'angle_definition': '小腿角 = 膝→踝相对竖直（与本项目一致）',
        'auto_compare': False,
        'context': '数值随赛段（350 m vs 750 m）条件化：步频 3.29→3.52 Hz'
                   '（冲刺可至 ≈3.82），小腿初触地角 ≈7°→4°；'
                   '需结合赛段选择，暂不自动比较',
        'step_metrics': {},
        'global_metrics': {},
    },
}

# 自动比较的参考库（步态类）；跳高/800m 需事件上下文，人工选择
AUTO_COMPARE_REFS = ('sprint_max_v', 'marathon_m', 'marathon_f')

_DISCLAIMER = ('±1/±2 SD 为工程统计分层，非官方/医学阈值；参考分布来自'
               '特定人群（世界级/精英、特定速度与拍摄条件），仅用于相近'
               '条件比较；2D 未标定投影角与文献测量存在投影误差')


# ---------------------------------------------------------------- 对比
def z_band(z: float) -> str:
    """z 值分层：|z|≤1 common；1<|z|≤2 deviated；|z|>2 outlier。"""
    a = abs(z)
    if a <= 1.0:
        return 'common'
    if a <= 2.0:
        return 'deviated'
    return 'outlier'


def _dig(step: dict, path: str):
    """按 'touchdown.knee_angle' 形式取 step 内嵌值。"""
    cur = step
    for key in path.split('.'):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    if isinstance(cur, bool):
        return None
    if isinstance(cur, (int, float)) and math.isfinite(cur):
        return cur
    return None


def _metric_output(value: float, ref: dict) -> dict:
    """单指标对比输出：有 SD → z + band；无 SD → 仅参考值。"""
    out = {
        'value': round(value, 2),
        'ref_mean': ref['mean'],
        'ref_sd': ref['sd'],
        'ref_range': ref['range'],
        'z': None,
        'band': None,
    }
    if ref['sd'] and ref['sd'] > 0:
        z = (value - ref['mean']) / ref['sd']
        out['z'] = round(z, 2)
        out['band'] = z_band(z)
    return out


def compare_steps_to_reference(steps: list[dict], ref_key: str,
                               cadence_hz: float | None = None) -> dict:
    """把每步特征与精英参考库逐指标对比（z-score / 参考值）。

    返回 JSON 可序列化 dict：
    {reference, source, sample, angle_definition, disclaimer,
     skipped_metrics: {path: reason},
     steps: [{td_frame, side, metrics: {path: {value, ref_mean,
              ref_sd, ref_range, z, band}}}],
     side_summary: {side: {path: {mean_z, band}}},
     global: {cadence_hz: {...}}}

    - 不可比指标（定义不同）不进入 metrics，原因登记在 skipped_metrics；
    - 无 SD 的文献值只输出参考值（z/band = None）；
    - 步数据缺失该指标时静默跳过该步该指标。
    """
    if ref_key not in ELITE_REFERENCES:
        raise ValueError(f'未知参考库: {ref_key}')
    ref = ELITE_REFERENCES[ref_key]

    skipped: dict[str, str] = {}
    comparable: dict[str, dict] = {}
    for path, entry in ref['step_metrics'].items():
        if entry['comparable']:
            comparable[path] = entry
        else:
            skipped[path] = entry.get('note') or '角度定义不一致'

    step_results: list[dict] = []
    z_sums: dict[tuple[str, str], list[float]] = {}
    for step in steps:
        metrics: dict[str, dict] = {}
        for path, entry in comparable.items():
            v = _dig(step, path)
            if v is None:
                continue
            metrics[path] = _metric_output(v, entry)
            z = metrics[path]['z']
            if z is not None:
                z_sums.setdefault((step['side'], path), []).append(z)
        step_results.append({
            'td_frame': step.get('td_frame'),
            'side': step.get('side'),
            'metrics': metrics,
        })

    side_summary: dict[str, dict] = {}
    for (side, path), zs in z_sums.items():
        mean_z = sum(zs) / len(zs)
        side_summary.setdefault(side, {})[path] = {
            'mean_z': round(mean_z, 2),
            'band': z_band(mean_z),
            'n': len(zs),
        }

    global_out: dict = {}
    for name, entry in ref['global_metrics'].items():
        if name == 'cadence_hz' and cadence_hz is not None:
            global_out['cadence_hz'] = _metric_output(cadence_hz, entry)

    return {
        'reference': ref_key,
        'source': ref['source'],
        'sample': ref['sample'],
        'angle_definition': ref['angle_definition'],
        'context': ref.get('context'),
        'disclaimer': _DISCLAIMER,
        'skipped_metrics': skipped,
        'steps': step_results,
        'side_summary': side_summary,
        'global': global_out,
    }
