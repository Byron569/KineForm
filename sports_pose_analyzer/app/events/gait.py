"""步态事件检测（触地/离地）与时空参数计算。

检测算法移植自 IDMDataHub/myogait（MIT License），其实现了多种
文献引用的经典步态事件检测方法；本模块移植其中默认且验证最广的
Zeni 方法并适配本项目数据结构。

版权声明（myogait, MIT License）：
    Copyright (c) Institut de Myologie / IDMDataHub
    https://github.com/IDMDataHub/myogait
   Permission is hereby granted, free of charge, to any person obtaining
    a copy of this software and associated documentation files (the
    "Software"), to deal in the Software without restriction...

方法文献：
    Zeni JA Jr, Richards JG, Higginson JS. Two simple methods for
    determining gait events during treadmill and overground walking
    using kinematic data. Gait Posture. 2008;27(4):710-714.
    doi:10.1016/j.gaitpost.2007.07.007

判据（Zeni）：
    信号 = 脚跟 x − 骨盆 x（前后相对位置，低通滤波后）——
    - 触地 touchdown = 信号峰值（脚相对骨盆最靠前）
    - 离地 toe_off   = 信号谷值（脚相对骨盆最靠后）
    prominence 自动取信号峰峰值的 10%（对不同分辨率鲁棒）；
    峰间距 ≥ min_cycle_duration × fps。

适配说明：
- myogait 原实现在脚跟缺失时回退踝点；本项目 trajectories 已含
  left_heel / right_heel，直接使用；
- 行进方向按骨盆 x 位移判断（首帧 vs 末帧有效值）；跑步机原地跑
  场景位移≈0 时默认向右，若运动员实际朝左则 TD/TO 会互换，
  后续可补充脚尖朝向判别；
- 跑步支撑比远低于走路（短跑约 20%），故不做走路合理性强校验
  （myogait 的 30-80% 支撑比门限仅适用于步行）；
- 30fps 下短跑支撑期仅约 3 帧，事件帧精度受限（±1 帧 ≈ ±33ms），
  高帧率视频（≥120fps）精度相应提高。
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

from ..common.data_models import Event, MetricsResult
from .detector import register_event_detector

__all__ = [
    'gait_temporal_params',
    'gait_step_features',
    'detect_gait_contact_events',
]

# Zeni 方法参数（与 myogait 默认值一致）
_CUTOFF_HZ = 6.0            # 低通截止频率
_MIN_CYCLE_S = 0.4          # 相邻事件最小间隔（秒）
_PROM_SCALE = 0.10          # prominence = 峰峰值 × 10%


# ---------------- 内部工具（移植自 myogait/events.py） ----------------
def _fill_nan(arr: np.ndarray) -> np.ndarray:
    """前向填充后反向填充 NaN（保持序列连续性供滤波/寻峰）。"""
    out = arr.copy()
    for i in range(1, len(out)):
        if np.isnan(out[i]):
            out[i] = out[i - 1]
    for i in range(len(out) - 2, -1, -1):
        if np.isnan(out[i]):
            out[i] = out[i + 1]
    return out


def _lowpass(sig: np.ndarray, cutoff: float, fs: float,
             order: int = 4) -> np.ndarray:
    """零相位 Butterworth 低通滤波（样本不足时原样返回）。"""
    nyq = 0.5 * fs
    if cutoff >= nyq:
        return sig
    b, a = butter(order, cutoff / nyq, btype='low')
    if len(sig) < 3 * max(len(b), len(a)):
        return sig
    return filtfilt(b, a, sig)


def _frame_ms(frames: int, fps: float) -> float:
    """帧数 → 毫秒。"""
    return frames * 1000.0 / fps


def _stats(values_ms: list[float]) -> dict | None:
    """毫秒序列统计 {mean,std,min,max,count}；空序列返回 None。"""
    if not values_ms:
        return None
    arr = np.asarray(values_ms, dtype=float)
    return {
        'mean': round(float(arr.mean()), 2),
        'std': round(float(arr.std()), 2),
        'min': round(float(arr.min()), 2),
        'max': round(float(arr.max()), 2),
        'count': int(arr.size),
    }


# ---------------- 步态事件检测（Zeni 方法） ----------------
@register_event_detector('gait_contact_events')
def _detect_gait_contact_events(metrics: MetricsResult,
                                statuses: list[str]) -> list[Event]:
    """Zeni 方法检测左/右脚触地（touchdown）与离地（toe_off）事件。

    输出 Event：type ∈ {left,right}_{touchdown,toe_off}，
    value = 该帧脚跟相对骨盆的前后位置（px，正值=脚在前方），
    unit='px'，confidence = 峰 prominence 归一化值（myogait 约定）。
    """
    traj = getattr(metrics, 'trajectories', None) or {}
    pelvis = np.asarray(traj.get('pelvis', np.nan), dtype=float)
    if pelvis.ndim != 2 or pelvis.shape[0] < 3:
        return []
    pelvis_x = _fill_nan(pelvis[:, 0])
    if not np.isfinite(pelvis_x).any():
        return []

    # 行进方向：骨盆 x 位移（末帧 > 首帧 = 向右）；跑步机场景默认向右
    valid = pelvis_x[np.isfinite(pelvis_x)]
    walking_right = valid[-1] > valid[0] if valid.size >= 2 else True

    fps = float(metrics.fps) if metrics.fps > 0 else 30.0
    min_distance = max(1, int(_MIN_CYCLE_S * fps))

    events: list[Event] = []
    for side, key in (('left', 'left_heel'), ('right', 'right_heel')):
        heel = np.asarray(traj.get(key, np.nan), dtype=float)
        if heel.ndim != 2 or not np.isfinite(heel[:, 0]).any():
            continue
        rel = _fill_nan(heel[:, 0]) - pelvis_x
        if not walking_right:
            rel = -rel                      # 翻转使峰值恒=脚在前方
        rel = _lowpass(rel, _CUTOFF_HZ, fps)

        valid_rel = rel[np.isfinite(rel)]
        if valid_rel.size < 3:
            continue
        prom = max(1e-6, float(np.ptp(valid_rel)) * _PROM_SCALE)

        # TD = 峰（脚最前），TO = 谷（脚最后）
        for event_type, target, find_max in (
                (f'{side}_touchdown', rel, True),
                (f'{side}_toe_off', rel, False)):
            peaks, props = find_peaks(
                target if find_max else -target,
                distance=min_distance, prominence=prom)
            if peaks.size == 0:
                continue
            proms = props['prominences']
            max_prom = float(np.max(proms)) if proms.size else 1.0
            for i, fi in enumerate(peaks):
                conf = float(proms[i] / max_prom) if max_prom > 0 else 1.0
                events.append(Event(
                    type=event_type,
                    frame_index=int(metrics.frame_indices[fi]),
                    timestamp_ms=float(metrics.timestamps_ms[fi]),
                    value=round(float(rel[fi]), 2),
                    unit='px',
                    confidence=min(max(conf, 0.0), 1.0)))
    return events


# 兼容直接调用（测试用）
detect_gait_contact_events = _detect_gait_contact_events


# ---------------- 时空参数 ----------------
def gait_temporal_params(events: list[Event], fps: float) -> dict:
    """从步态事件表计算时空参数汇总。

    per-side：触地/腾空/步态周期时间（ms）、支撑比；
    全局：步时间（相邻触地间隔，左右交替）与步频（steps/min）。
    每项统计为 {mean,std,min,max,count} 或 None（样本不足）。
    """
    if fps <= 0:
        fps = 30.0

    def frames_of(t: str) -> list[int]:
        return sorted(e.frame_index for e in events if e.type == t)

    summary: dict = {}
    all_tds: list[int] = []
    for side in ('left', 'right'):
        tds = frames_of(f'{side}_touchdown')
        tos = frames_of(f'{side}_toe_off')
        all_tds.extend(tds)

        # 触地时间：TD 后第一个同侧 TO
        contact_ms = [
            _frame_ms(next(t for t in tos if t > td) - td, fps)
            for td in tds if any(t > td for t in tos)]
        # 腾空时间：TO 后第一个同侧 TD
        flight_ms = [
            _frame_ms(next(t for t in tds if t > to) - to, fps)
            for to in tos if any(t > to for t in tds)]
        # 步态周期：相邻同侧 TD 间隔
        stride_ms = [
            _frame_ms(tds[i + 1] - tds[i], fps)
            for i in range(len(tds) - 1)]
        # 支撑比：触地时间 / 步态周期（帧比，避免毫秒舍入）
        stance_ratio = []
        for i, td in enumerate(tds):
            to_next = [t for t in tos if t > td]
            if i + 1 < len(tds) and to_next:
                stride_f = tds[i + 1] - td
                if stride_f > 0:
                    stance_ratio.append(
                        (to_next[0] - td) / stride_f)

        summary[side] = {
            'n_touchdowns': len(tds),
            'n_toe_offs': len(tos),
            'contact_time_ms': _stats(contact_ms),
            'flight_time_ms': _stats(flight_ms),
            'stride_time_ms': _stats(stride_ms),
            'stance_ratio': _stats([r * 100.0 for r in stance_ratio]),
        }
        if stance_ratio:
            # 同时给出无量纲均值（便于直接比较文献支撑比）
            summary[side]['stance_ratio']['mean_frac'] = round(
                float(np.mean(stance_ratio)), 4)

    # 全局：步时间 = 相邻触地（左右交替合并）间隔；步频 = 60000/步时间
    all_tds.sort()
    step_ms = [
        _frame_ms(all_tds[i + 1] - all_tds[i], fps)
        for i in range(len(all_tds) - 1)]
    step_stats = _stats(step_ms)
    cadence = None
    if step_stats and step_stats['mean'] > 0:
        cadence = round(60000.0 / step_stats['mean'], 1)

    summary['step_time_ms'] = step_stats
    summary['cadence_spm'] = cadence
    return summary


# ---------------- 每步事件条件化特征 ----------------
def _finite_slice(series, sl) -> np.ndarray | None:
    """切片内有限值数组；序列缺失或全 NaN 返回 None。"""
    if series is None:
        return None
    a = np.asarray(series, dtype=float)[sl]
    a = a[np.isfinite(a)]
    return a if a.size else None


def _wrap180(a: float) -> float:
    """角度归一到 (-180, 180]。"""
    return (a + 180.0) % 360.0 - 180.0


def _flip_angle(v, direction: int, nd: int = 1):
    """方向翻转的角度快照：左向跑 θ → −θ；None 透传。"""
    if v is None:
        return None
    return round(-v, nd) if direction < 0 else v


def gait_step_features(metrics: MetricsResult, events: list[Event],
                       n_pre_td_frames: int = 3,
                       body_scale: dict | None = None) -> list[dict]:
    """从步态事件 + 指标序列提取"每步"的事件条件化特征。

    返回按 td_frame 升序的 step dict 列表（角度单位度、时间 ms、
    距离/速度像素，均 1 位小数）：
    {side, td_frame, to_frame, next_td_frame,
     contact_time_ms, flight_time_ms, stride_time_ms,
     stance_ratio, flight_support_ratio,
     stride_length_px[, stride_length_norm, stride_length_m],
     pelvis_vertical_range_px[, pelvis_vertical_range_norm],
     touchdown: {knee/hip/ankle/torso_lean/thigh/shank/shoulder/
                 elbow_angle, foot_pelvis_dist_px[,
                 foot_pelvis_dist_norm], foot_rel_vx_px_s},
     midstance: {frame, knee/hip/ankle/shoulder/elbow_angle},
     toe_off: {knee/hip/ankle/shoulder/elbow_angle},
     stance: {min_knee_angle, knee_collapse_deg,
              knee/ankle/hip_rom_deg},
     swing: {min_knee_angle, max_thigh_angle}}

    文献依据（研究报告 1/3）：评价必须事件条件化——TD 姿态 +
    支撑期变化量（膝塌陷/ROM）+ 摆动期特征优于单帧绝对角度；
    foot_pelvis_dist_px 为 Nicholson 跳高 CM-foot 距离与短跑
    "着地点相对质心"的同源指标；foot_rel_vx_px_s 负值 = 触地前
    脚相对身体向后回摆（Morin 2015 "主动扒地"视觉代理）。

    尺度归一化（body_scale，来自 biomechanics.scale.body_scale）：
    - body_height_px 有效时输出 *_norm 无量纲字段（距离/身高）；
    - m_per_px（用户提供真实身高时）额外输出 stride_length_m。

    约定：行进方向按骨盆 x 首末自动检测；左向跑自动翻转
    thigh（180°−θ wrap）、shank/shoulder（−θ）、
    foot_pelvis_dist（−rel）。midstance 取支撑期内 |脚跟−骨盆 x|
    最小帧（Hanley 中足位定义的 2D 近似）。角度缺失帧输出
    None（旧数据兼容）。肩角为 Hanley 解剖约定（0°=下垂，
    前摆为正）。
    """
    fps = float(metrics.fps) if getattr(metrics, 'fps', 0) > 0 else 30.0
    traj = getattr(metrics, 'trajectories', None) or {}
    pelvis = traj.get('pelvis')
    if pelvis is None:
        return []
    pelvis = np.asarray(pelvis, dtype=float)
    pelvis_x, pelvis_y = pelvis[:, 0], pelvis[:, 1]

    idx_of = {int(fi): i for i, fi in
              enumerate(np.asarray(metrics.frame_indices).tolist())}

    vpx = pelvis_x[np.isfinite(pelvis_x)]
    direction = 1 if (vpx.size < 2 or vpx[-1] >= vpx[0]) else -1

    angles = dict(getattr(metrics, 'angles', None) or {})
    seg = dict(getattr(metrics, 'segment_angles', None) or {})
    scale = body_scale or {}
    body_h = scale.get('body_height_px')
    m_per_px = scale.get('m_per_px')

    def norm(px: float | None) -> float | None:
        """距离/身高 无量纲化（身高无效或数据缺失 → None）。"""
        if px is None or not body_h or body_h <= 0:
            return None
        return round(px / body_h, 4)

    def snap(series, i, nd=1):
        """单帧值快照：缺失/NaN → None，否则保留 nd 位小数。"""
        if series is None:
            return None
        try:
            v = float(np.asarray(series)[i])
        except (IndexError, TypeError, ValueError):
            return None
        return round(v, nd) if np.isfinite(v) else None

    steps: list[dict] = []
    for side in ('left', 'right'):
        heel = traj.get(f'{side}_heel')
        if heel is None:
            continue
        heel_x = np.asarray(heel, dtype=float)[:, 0]
        rel = heel_x - pelvis_x        # 正 = 脚在 +x 侧（右向跑=前方）

        tds = sorted(idx_of[e.frame_index] for e in events
                     if e.type == f'{side}_touchdown'
                     and e.frame_index in idx_of)
        tos = sorted(idx_of[e.frame_index] for e in events
                     if e.type == f'{side}_toe_off'
                     and e.frame_index in idx_of)
        if not tds:
            continue

        knee = angles.get(f'{side}_knee')
        hip = angles.get(f'{side}_hip')
        ankle = angles.get(f'{side}_ankle')
        elbow = angles.get(f'{side}_elbow')
        thigh = seg.get(f'{side}_thigh')
        shank = seg.get(f'{side}_shank')
        shoulder = seg.get(f'{side}_shoulder')

        for k, td in enumerate(tds):
            to_c = [t for t in tos if t > td]
            if not to_c:
                continue
            to = to_c[0]
            ntd = tds[k + 1] if k + 1 < len(tds) else None

            stance_sl = slice(td, to + 1)
            knee_fs = _finite_slice(knee, stance_sl)
            ankle_fs = _finite_slice(ankle, stance_sl)
            hip_fs = _finite_slice(hip, stance_sl)

            # midstance：支撑期内 |rel| 最小帧（脚最接近骨盆正下方）
            seg_rel = np.abs(rel[stance_sl])
            ms = None
            if np.isfinite(seg_rel).any():
                local = np.where(np.isfinite(seg_rel), seg_rel, np.inf)
                ms = td + int(np.argmin(local))

            # 触地前 n 帧脚跟相对骨盆水平速度（后向差分均值）
            pre_vx = None
            j0 = max(1, td - n_pre_td_frames)
            if td - j0 >= 1:
                win = rel[j0:td + 1]
                if np.isfinite(win).all():
                    dv = (win[1:] - win[:-1]) * fps
                    pre_vx = round(float(np.mean(dv)), 1)

            # 摆动期特征（to → 下一 td，不含端点）
            swing_min_knee = None
            swing_max_thigh = None
            if ntd is not None:
                swing_sl = slice(to + 1, ntd)
                sw_knee = _finite_slice(knee, swing_sl)
                if sw_knee is not None:
                    swing_min_knee = round(float(sw_knee.min()), 1)
                sw_thigh = _finite_slice(thigh, swing_sl)
                if sw_thigh is not None:
                    if direction < 0:
                        sw_thigh = _wrap180(180.0 - sw_thigh)
                    swing_max_thigh = round(float(sw_thigh.max()), 1)

            # 骨盆垂直振幅（整周期；末步仅支撑期）
            cyc_sl = slice(td, ntd) if ntd is not None else stance_sl
            y_fs = _finite_slice(pelvis_y, cyc_sl)
            vert_range = (round(float(y_fs.max() - y_fs.min()), 1)
                          if y_fs is not None else None)

            # 步长（整周期骨盆水平位移；方向无关）
            stride_len_px = None
            if ntd is not None and np.isfinite(pelvis_x[td]) \
                    and np.isfinite(pelvis_x[ntd]):
                stride_len_px = round(
                    float(abs(pelvis_x[ntd] - pelvis_x[td])), 1)

            td_knee = snap(knee, td)
            td_thigh = snap(thigh, td)
            td_shoulder = snap(shoulder, td)
            td_dist = (round(float(direction * rel[td]), 2)
                       if np.isfinite(rel[td]) else None)
            steps.append({
                'side': side,
                'td_frame': int(metrics.frame_indices[td]),
                'to_frame': int(metrics.frame_indices[to]),
                'next_td_frame': (int(metrics.frame_indices[ntd])
                                  if ntd is not None else None),
                'contact_time_ms': round((to - td) * 1000.0 / fps, 1),
                'flight_time_ms': (round((ntd - to) * 1000.0 / fps, 1)
                                   if ntd is not None else None),
                'stride_time_ms': (round((ntd - td) * 1000.0 / fps, 1)
                                   if ntd is not None else None),
                'stance_ratio': (round((to - td) / (ntd - td), 4)
                                 if ntd is not None else None),
                'flight_support_ratio': (round((ntd - to) / (to - td), 2)
                                         if ntd is not None else None),
                'stride_length_px': stride_len_px,
                'stride_length_norm': norm(stride_len_px),
                'stride_length_m': (
                    round(stride_len_px * m_per_px, 3)
                    if stride_len_px is not None and m_per_px else None),
                'pelvis_vertical_range_px': vert_range,
                'pelvis_vertical_range_norm': norm(vert_range),
                'touchdown': {
                    'knee_angle': td_knee,
                    'hip_angle': snap(hip, td),
                    'ankle_angle': snap(ankle, td),
                    'torso_lean_angle': snap(
                        getattr(metrics, 'torso_lean', None), td),
                    'thigh_angle': (
                        round(_wrap180(180.0 - td_thigh), 1)
                        if td_thigh is not None and direction < 0
                        else td_thigh),
                    'shank_angle': _flip_angle(snap(shank, td), direction),
                    'shoulder_angle': _flip_angle(td_shoulder, direction),
                    'elbow_angle': snap(elbow, td),
                    'foot_pelvis_dist_px': td_dist,
                    'foot_pelvis_dist_norm': norm(td_dist),
                    'foot_rel_vx_px_s': pre_vx,
                },
                'midstance': ({
                    'frame': int(metrics.frame_indices[ms]),
                    'knee_angle': snap(knee, ms),
                    'hip_angle': snap(hip, ms),
                    'ankle_angle': snap(ankle, ms),
                    'shoulder_angle': _flip_angle(snap(shoulder, ms),
                                                  direction),
                    'elbow_angle': snap(elbow, ms),
                } if ms is not None else None),
                'toe_off': {
                    'knee_angle': snap(knee, to),
                    'hip_angle': snap(hip, to),
                    'ankle_angle': snap(ankle, to),
                    'shoulder_angle': _flip_angle(snap(shoulder, to),
                                                  direction),
                    'elbow_angle': snap(elbow, to),
                },
                'stance': {
                    'min_knee_angle': (round(float(knee_fs.min()), 1)
                                       if knee_fs is not None else None),
                    'knee_collapse_deg': (
                        round(td_knee - float(knee_fs.min()), 1)
                        if td_knee is not None and knee_fs is not None
                        else None),
                    'knee_rom_deg': (
                        round(float(knee_fs.max() - knee_fs.min()), 1)
                        if knee_fs is not None else None),
                    'ankle_rom_deg': (
                        round(float(ankle_fs.max() - ankle_fs.min()), 1)
                        if ankle_fs is not None else None),
                    'hip_rom_deg': (
                        round(float(hip_fs.max() - hip_fs.min()), 1)
                        if hip_fs is not None else None),
                },
                'swing': {
                    'min_knee_angle': swing_min_knee,
                    'max_thigh_angle': swing_max_thigh,
                },
            })
    steps.sort(key=lambda s: (s['td_frame'], s['side']))
    return steps
