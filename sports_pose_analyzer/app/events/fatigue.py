"""疲劳趋势分析：每步特征前/后半程对比（split-half）。

方法：将 gait_step_features 产出的 step dict 列表按 td_frame 升序
后对半切分（奇数步时前半多一步），逐指标比较两半均值——项目研究
报告结论"比较第 1 分钟 vs 接近力竭姿态"是长跑系统核心评价方式，
本模块为其在步粒度上的实现（前半 ≈ 早期、后半 ≈ 后期接近力竭）。

文献依据（与 app/biomechanics/references.py 同源登记）：
    Hanley B, et al. Front Sports Act Living 2020 (fspor.2020.00102)，
    2017 世锦赛马拉松 28 男/28 女，29.5 vs 40 km——
    —— 疲劳后触地时间（contact_time_ms）延长；
    —— midswing 最小膝角（swing.min_knee_angle）后半程较前半程
       增加约 5°（男子 50±6 → ≈55±7）。
    本模块只输出 delta/delta_pct 供与上述方向性结论对照（正值 =
    后程增大），不做疲劳阈值判定（个体差异大，解读交由报告层）。

输出约定：
    {n_steps, split_at,
     halves: {first/second: {指标: 均值(1位小数)|None}},
     delta: {指标: second-first},         # 仅两半均有值的指标
     delta_pct: {指标: 百分比(1位小数)}}   # (second-first)/first×100
指标键沿用 references.py 点号嵌套约定（如 swing.min_knee_angle）。

假设（模糊判据，显式声明）：
- split_at = 前半步数（亦即后半起始索引）；
- None 指标值求均值时跳过；某半无有效样本 → 该半为 None，
  两半均无 → halves 中为 None 且不进入 delta/delta_pct；
- halves 显示 1 位小数，delta/delta_pct 基于未舍入均值计算
  （stance_ratio 量级约 0.2，1 位小数显示较粗，其变化请以
  delta_pct 为准）；
- first 均值为 0 时不输出该指标 delta_pct（除零保护）。
"""
from __future__ import annotations

import numpy as np

__all__ = ['fatigue_trend']

# 顶层指标：step dict 直接键（时空参数 + 距离/振幅）
_TOP_METRICS = (
    'contact_time_ms',
    'flight_time_ms',
    'stride_time_ms',
    'stance_ratio',
    'pelvis_vertical_range_px',
    'stride_length_px',
)

# 嵌套指标：'子字典.键'（事件条件化角度，Hanley 疲劳判据相关）
_NESTED_METRICS = (
    'touchdown.knee_angle',
    'stance.min_knee_angle',
    'stance.knee_collapse_deg',
    'swing.min_knee_angle',
    'swing.max_thigh_angle',
    'touchdown.shoulder_angle',
)

_METRICS = _TOP_METRICS + _NESTED_METRICS


def _step_value(step: dict, metric: str) -> float | None:
    """提取 step dict 指标值：'a.b' → step['a']['b']，否则顶层键；
    子字典缺失/非 dict 或值缺失 → None。"""
    if '.' in metric:
        sub, key = metric.split('.', 1)
        nested = step.get(sub)
        if not isinstance(nested, dict):
            return None
        return nested.get(key)
    return step.get(metric)


def _half_mean(half_steps: list[dict], metric: str) -> float | None:
    """半程指标均值（未舍入，显示层再取 1 位小数）；
    无有效样本 → None（None 值跳过）。"""
    values = [v for s in half_steps
              if (v := _step_value(s, metric)) is not None]
    if not values:
        return None
    return float(np.mean(values))


def fatigue_trend(steps: list[dict], min_steps: int = 6) -> dict | None:
    """每步特征前/后半程疲劳趋势对比。

    参数：
        steps：gait_step_features 输出的 step dict 列表
            （内部按 td_frame 升序重排，不修改入参）；
        min_steps：最小步数门限（步数不足 → None）。

    返回结构见模块 docstring；len(steps) < min_steps 时返回 None。
    """
    if len(steps) < min_steps:
        return None

    ordered = sorted(steps, key=lambda s: s.get('td_frame', 0))
    split_at = (len(ordered) + 1) // 2           # 奇数步时前半多一步
    half_steps = {'first': ordered[:split_at],
                  'second': ordered[split_at:]}

    raw = {name: {m: _half_mean(hs, m) for m in _METRICS}
           for name, hs in half_steps.items()}
    halves = {name: {m: None if v is None else round(v, 1)
                     for m, v in means.items()}
              for name, means in raw.items()}

    delta: dict[str, float] = {}
    delta_pct: dict[str, float] = {}
    for m in _METRICS:
        first, second = raw['first'][m], raw['second'][m]
        if first is None or second is None:
            continue
        delta[m] = round(second - first, 1)
        if first != 0:
            delta_pct[m] = round((second - first) / first * 100.0, 1)

    return {
        'n_steps': len(ordered),
        'split_at': split_at,
        'halves': halves,
        'delta': delta,
        'delta_pct': delta_pct,
    }
