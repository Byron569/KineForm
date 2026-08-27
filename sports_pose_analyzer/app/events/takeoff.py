"""跳高起跳步识别（从每步特征序列中甄别起跳步）。

定义（与 app/biomechanics/references.py 中 hj_takeoff_success 的
context 一致）：起跳步 = 触地时间显著更长 + 其后无同侧触地的步。

文献依据：
- Nicholson et al. 2024, Front Sports Act Living (fspor.2024.1352725)：
  世界室内锦标赛男子跳高，同一运动员同高度成功尝试起跳触地
  0.169 s / 失败尝试 0.178 s——远长于助跑步；
- WA2017 世锦赛决赛起跳触地 0.14–0.19 s；
- 正常跑步步触地约 0.10–0.30 s（短跑约 0.10 s，Mattes 2021），
  但跳高助跑最后一步（起跳步）之后接长腾空（过杆落垫），
  该侧不再有下一次触地。

判据（保守，宁可漏报不误报）：
1. 该步 next_td_frame 为 None——该侧最后一步（起跳后腾空，
   不再有同侧触地）；
2. contact_time_ms > contact_ratio_thr × 全部有效步
   contact_time_ms 的中位数（默认 1.4×，严格大于；对应起跳触地
   ≈0.17 s vs 助跑 ≈0.10–0.12 s 的文献量级差）；
3. 有效步（contact_time_ms 为有限数）≥ 4，否则中位数不可靠，
   返回空列表。

置信度公式（单调映射）：
    confidence = clamp(ratio / (2 × contact_ratio_thr), 0, 1)
比值恰为阈值（1.4）时置信度 0.5，比值达 2×阈值（2.8）时饱和为 1。

局限（使用方必读）：
- 若视频在起跳后继续拍到落垫，落垫接触可能被步态检测识别为
  另一个"末步"，其触地时间也可能较长（落垫缓冲），从而被误报
  为起跳步——需结合该步触地时长与其前腾空时长（起跳前腾空应
  显著短于起跳后过杆腾空）人工甄别；
- 当前保守判据（双条件 + 最少步数限制）宁可漏报不误报：起跳
  触地不够长、或视频截断导致末步不完整时不会报出；
- contact_ratio_thr=1.4 为工程约定（基于文献触地时间量级差），
  非统计检验阈值。
"""
from __future__ import annotations

import numpy as np

__all__ = ['identify_takeoff_steps']

_MIN_STEPS = 4      # 计算触地时间中位数所需最少有效步数


def _finite_contact(step: dict) -> float | None:
    """步的有限触地时间（ms）；缺失/NaN/非数值 → None。"""
    v = step.get('contact_time_ms')
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if np.isfinite(v) else None


def identify_takeoff_steps(steps: list[dict],
                           contact_ratio_thr: float = 1.4) -> list[dict]:
    """从 gait_step_features 输出的步列表中识别跳高起跳步。

    参数：
    - steps：step dict 列表（关键字段 side / td_frame /
      next_td_frame / contact_time_ms，见 app/events/gait.py）；
    - contact_ratio_thr：触地时间相对中位数的判定倍率（默认 1.4，
      严格大于才判定）。

    返回按 td_frame 升序的 dict 列表（无起跳步时为空）：
    [{td_frame, side, contact_time_ms, contact_median_ms,
      ratio, confidence, reason}]
    - ratio = contact_time_ms / contact_median_ms（中位数取自全部
      有效步的 contact_time_ms）；
    - confidence = clamp(ratio / (2×contact_ratio_thr), 0, 1)；
    - reason：中文判据说明（供报告展示）。

    判据与局限详见模块 docstring。
    """
    valid = [s for s in steps if _finite_contact(s) is not None]
    if len(valid) < _MIN_STEPS:
        return []

    median = float(np.median(
        [s['contact_time_ms'] for s in valid]))
    if not np.isfinite(median) or median <= 0.0:
        return []

    takeoffs: list[dict] = []
    for s in valid:
        if s.get('next_td_frame') is not None:
            continue                     # 该侧其后仍有触地 → 非末步
        contact = _finite_contact(s)
        ratio = contact / median
        if ratio <= contact_ratio_thr:
            continue                     # 触地不够长（严格大于判据）
        takeoffs.append({
            'td_frame': int(s['td_frame']),
            'side': s['side'],
            'contact_time_ms': round(contact, 1),
            'contact_median_ms': round(median, 2),
            'ratio': round(ratio, 3),
            'confidence': round(
                min(max(ratio / (2.0 * contact_ratio_thr), 0.0), 1.0), 4),
            'reason': (
                f'末步（其后无同侧触地）触地 {contact:.0f} ms > '
                f'{contact_ratio_thr}×中位数 {median:.0f} ms'
                f'（比值 {ratio:.2f}），触地显著延长符合跳高起跳步'
                f'特征（文献 0.14–0.19 s）'),
        })
    takeoffs.sort(key=lambda t: (t['td_frame'], t['side']))
    return takeoffs
