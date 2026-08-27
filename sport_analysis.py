"""运动分析：基于 pose_cli.py 输出的关键点 JSON 生成分析报告。

用法:
    python sport_analysis.py outputs/xxx_keypoints.json --mode run    # 跑步步态分析
    python sport_analysis.py outputs/xxx_keypoints.json --mode jump   # 跳跃分析(CMJ等)
    python sport_analysis.py outputs/xxx_keypoints.json               # 自动判断模式

说明:
    - 角度为 2D 投影角：侧面拍摄得到矢状面真实角度，正面拍摄为额状面投影
    - 跳高估算采用飞行时间法 h = g*t^2/8，只依赖帧率，无需像素标定
    - 长度类指标以「身高像素」为单位归一化（头顶17至踝中点的像素距离）
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

try:
    from scipy.signal import find_peaks, savgol_filter
except ImportError as e:
    raise SystemExit('需要 scipy: pip install scipy') from e

# halpe26 索引
Nose, LEye, REye, LEar, REar, LSho, RSho, LElb, RElb, LWri, RWri, \
    LHip, RHip, LKnee, RKnee, LAnk, RAnk, Head, Neck, Hip, \
    LBigToe, RBigToe, LSmallToe, RSmallToe, LHeel, RHeel = range(26)

ANGLE_DEFS = {
    '左膝': (LHip, LKnee, LAnk), '右膝': (RHip, RKnee, RAnk),
    '左髋': (LSho, LHip, LKnee), '右髋': (RSho, RHip, RKnee),
    '左踝': (LKnee, LAnk, LBigToe), '右踝': (RKnee, RAnk, RBigToe),
    '左肘': (LSho, LElb, LWri), '右肘': (RSho, RElb, RWri),
}

G = 9.81  # 重力加速度 m/s^2


def load_keypoints(path):
    """返回 (kpts(F,26,2), scores(F,26), fps, meta)，无效帧已剔除。"""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    meta, frames = data['meta'], data['frames']
    if not frames:
        raise SystemExit('JSON 中没有有效姿态帧')
    kpts = np.array([f['keypoints'] for f in frames], dtype=float)
    scores = np.array([f['scores'] for f in frames], dtype=float)
    frame_ids = [f['frame'] for f in frames]
    # 用原始帧号重建时间轴，保证漏检帧不压缩时间
    t = np.array(frame_ids, dtype=float) / meta['fps']
    return kpts, scores, t, meta


def nan_low_confidence(kpts, scores, thr=0.3):
    """低置信度关键点置 NaN，避免抖动污染分析。"""
    out = kpts.copy()
    out[scores < thr] = np.nan
    return out


def smooth_series(x, fps):
    """Savitzky-Golay 平滑，跳过 NaN。"""
    if len(x) < 9:
        return x
    win = max(5, int(round(fps * 0.15)) | 1)  # ~0.15s，奇数
    if win >= len(x):
        win = (len(x) // 2) * 2 - 1
        win = max(3, win)
    y = x.copy()
    mask = np.isfinite(x)
    if mask.sum() < win:
        return y
    filled = np.interp(np.arange(len(x)), np.flatnonzero(mask), x[mask])
    sm = savgol_filter(filled, win, 2)
    y[mask] = sm[mask]
    return y


def angle_series(kpts, scores, i1, i2, i3, thr=0.3):
    """逐帧计算三点角度（度），任一点低置信度则为 NaN。"""
    valid = (scores[:, i1] > thr) & (scores[:, i2] > thr) & (scores[:, i3] > thr)
    out = np.full(len(kpts), np.nan)
    if valid.sum() == 0:
        return out
    p1, p2, p3 = kpts[valid, i1], kpts[valid, i2], kpts[valid, i3]
    v1 = p1 - p2
    v2 = p3 - p2
    cos = np.sum(v1 * v2, axis=1) / (
        np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1) + 1e-9)
    out[valid] = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    return out


def interp_nan(arr):
    mask = np.isfinite(arr)
    if mask.sum() < 2:
        return arr
    out = arr.copy()
    out[~mask] = np.interp(np.flatnonzero(~mask), np.flatnonzero(mask), arr[mask])
    return out


def body_scale(kpts, scores):
    """身高像素尺度：头顶(17)到双踝中点的距离，取视频稳健值。"""
    head_y = interp_nan(kpts[:, Head, 1])
    ank_y = interp_nan((kpts[:, LAnk, 1] + kpts[:, RAnk, 1]) / 2)
    stature = np.nanmedian(head_y - ank_y)
    return abs(stature) if np.isfinite(stature) and stature > 10 else None


def foot_y(kpts, side):
    """某侧脚的 y 坐标（踝+大脚趾平均），向下为正。"""
    ank = interp_nan(kpts[:, LAnk if side == 'L' else RAnk, 1])
    toe = interp_nan(kpts[:, LBigToe if side == 'L' else RBigToe, 1])
    with np.errstate(invalid='ignore'):
        y = np.where(np.isfinite(toe), (ank + toe) / 2, ank)
    return interp_nan(y)


# ---------------- 跑步模式 ----------------
def report_run(kpts, scores, t, fps, meta):
    print('=' * 52)
    print('跑步步态分析')
    print('=' * 52)

    # 关节角度摘要
    print('\n[关节角度摘要] (2D 投影，侧面拍摄=矢状面)')
    print(f"  {'关节':<6}{'最小°':>8}{'最大°':>8}{'平均°':>8}{'活动范围°':>10}")
    angles_all = {}
    for name, (i1, i2, i3) in ANGLE_DEFS.items():
        a = angle_series(kpts, scores, i1, i2, i3)
        if np.isfinite(a).sum() < 5:
            continue
        angles_all[name] = a
        print(f"  {name:<6}{np.nanmin(a):>8.0f}{np.nanmax(a):>8.0f}"
              f"{np.nanmean(a):>8.0f}{np.nanmax(a) - np.nanmin(a):>10.0f}")

    # 触地事件：脚 y 平滑序列的局部极大值（脚最低点）
    print('\n[步态时序]')
    events = {}
    for side, label in (('L', '左脚'), ('R', '右脚')):
        y = smooth_series(foot_y(kpts, side), fps)
        if not np.isfinite(y).all() and np.isfinite(y).sum() < 10:
            continue
        dist = max(int(0.25 * fps), 3)  # 同一脚两次触地最少间隔 0.25s
        peaks, _ = find_peaks(y, distance=dist,
                              prominence=np.nanstd(y) * 0.3)
        if len(peaks) >= 1:
            events[side] = peaks
            print(f'  {label}触地 {len(peaks)} 次 @ '
                  f'{[round(t[p], 2) for p in peaks]}s')

    all_ev = sorted([(p, s) for s, ps in events.items() for p in ps])
    if len(all_ev) >= 2:
        gaps = np.diff([e[0] for e in all_ev]) / fps
        cadence = 60 / gaps.mean()
        print(f'  步频: {cadence:.1f} 步/分（{len(all_ev)} 步，平均步时 {gaps.mean():.2f}s）')
        if 'L' in events and 'R' in events and len(events['L']) >= 2 and len(events['R']) >= 2:
            tl = np.diff(events['L']).mean() / fps
            tr = np.diff(events['R']).mean() / fps
            sym = abs(tl - tr) / ((tl + tr) / 2) * 100
            print(f'  左右周期: 左 {tl:.2f}s / 右 {tr:.2f}s，不对称度 {sym:.1f}%')
    else:
        print('  （触地事件不足，无法计算步频——可能视频太短或非跑步内容）')

    # 步长（像素，归一化到身高）
    scale = body_scale(kpts, scores)
    if scale and all_ev and len(all_ev) >= 2:
        px = kpts[:, [LAnk, RAnk], 0]
        steps = []
        for (p1, s1), (p2, s2) in zip(all_ev[:-1], all_ev[1:]):
            if s1 != s2:  # 左右交替的一步
                d = abs(np.nanmean(px[p2]) - np.nanmean(px[p1]))
                if np.isfinite(d):
                    steps.append(d)
        if steps:
            m = np.mean(steps)
            print(f'  平均步长: {m:.0f}px ≈ {m / scale:.2f} 身高单位（需侧面固定机位）')

    print('\n提示: 角度最可靠的条件是固定侧面机位（运动平面平行于画面）。')


# ---------------- 跳跃模式 ----------------
def report_jump(kpts, scores, t, fps, meta):
    print('=' * 52)
    print('跳跃分析（飞行时间法）')
    print('=' * 52)

    scale = body_scale(kpts, scores)
    # 质心 proxy：骨盆中心(19)，缺失时用双髋平均
    com_y = interp_nan(kpts[:, Hip, 1])
    hip_mid = interp_nan((kpts[:, LHip, 1] + kpts[:, RHip, 1]) / 2)
    com_y = np.where(np.isfinite(com_y), com_y, hip_mid)
    com_y = smooth_series(com_y, fps)

    # 双脚最低 y（图像向下为正 → 值大=低）
    foot_low = np.fmax(foot_y(kpts, 'L'), foot_y(kpts, 'R'))
    ground = np.nanpercentile(foot_low, 90)  # 站立基线
    margin = 0.05 * scale if scale else np.nanstd(foot_low)
    airborne = foot_low < ground - margin  # 双脚均离地

    # 连续腾空段
    segs, s = [], None
    for i, a in enumerate(airborne):
        if a and s is None:
            s = i
        elif not a and s is not None:
            segs.append((s, i))
            s = None
    if s is not None:
        segs.append((s, len(airborne)))
    segs = [(a, b) for a, b in segs if b - a >= max(3, int(0.15 * fps))]

    if not segs:
        print('未检测到腾空段（双脚同时离地 >0.15s）。')
        print('可能原因: 原地纵跳幅度小/帧率低/脚部关键点不稳。')
        print(f'  地面基线 y={ground:.0f}px, 离地判定 margin={margin:.0f}px')
        return

    stand_com = np.nanpercentile(com_y, 25)  # 站立/浅蹲质心高度
    print(f'\n检测到 {len(segs)} 次腾空:')
    for n, (a, b) in enumerate(segs, 1):
        tf = (b - a) / fps
        h = G * tf ** 2 / 8 * 100  # cm
        peak = np.nanmin(com_y[a:b])  # 质心最高点(y最小)
        dip = np.nanmin(com_y[max(0, a - int(fps)):a + 1])
        depth_px = dip - stand_com if np.isfinite(dip) else np.nan
        depth = f'{depth_px / scale * 100:.0f}%身高' if scale and np.isfinite(depth_px) else 'N/A'
        print(f'  第{n}跳: 起跳 {t[a]:.2f}s → 落地 {t[b]:.2f}s，'
              f'腾空 {tf * 1000:.0f}ms，跳高 ≈ {h:.1f}cm，下蹲深度 {depth}')

    # 起跳瞬间膝关节角度（蹬伸特征）
    a0, b0 = segs[0]
    pre = slice(max(0, a0 - int(0.2 * fps)), a0 + 1)
    for name, (i1, i2, i3) in (('左膝', (LHip, LKnee, LAnk)), ('右膝', (RHip, RKnee, RAnk))):
        ang = angle_series(kpts, scores, *ANGLE_DEFS[name])
        if np.isfinite(ang[pre]).sum():
            print(f'  起跳前{name}最小角: {np.nanmin(ang[pre]):.0f}°'
                  f'（越小=反向运动越深）')

    print('\n说明: 跳高 h=g·t²/8 由腾空时间推算，与测力台一致性 ICC≈0.985（文献）。')
    print('      腾空判定基于双脚关键点，建议固定机位、全身入镜。')


def main():
    parser = argparse.ArgumentParser(description='运动姿态数据分析')
    parser.add_argument('json_path', help='pose_cli.py 输出的关键点 JSON')
    parser.add_argument('--mode', choices=['run', 'jump', 'auto'], default='auto')
    args = parser.parse_args()

    kpts, scores, t, meta = load_keypoints(args.json_path)
    fps = meta['fps']
    print(f"源: {meta['source']}  帧数: {len(kpts)}  fps: {fps}")

    mode = args.mode
    if mode == 'auto':
        # 有明显腾空段则视为跳跃
        scale = body_scale(kpts, scores)
        foot_low = np.fmax(foot_y(kpts, 'L'), foot_y(kpts, 'R'))
        ground = np.nanpercentile(foot_low, 90)
        margin = 0.05 * scale if scale else np.nanstd(foot_low)
        airborne = foot_low < ground - margin
        longest = 0
        s = None
        for i, a in enumerate(airborne):
            if a and s is None:
                s = i
            elif not a and s is not None:
                longest = max(longest, i - s)
                s = None
        mode = 'jump' if longest >= max(3, int(0.2 * fps)) else 'run'
        print(f'自动判断模式: {mode}\n')

    (report_run if mode == 'run' else report_jump)(kpts, scores, t, fps, meta)


if __name__ == '__main__':
    main()
