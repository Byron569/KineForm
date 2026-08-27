"""分析结果导出：manifest / 关键点 JSON / 指标 CSV / 事件 JSON /
motion.json / HTML 报告。

只依赖标准库 + numpy（JSON 写出统一走 data_models.write_json），
模块顶层不 import torch/mmpose，保证可在无 GPU 环境下运行与测试。
"""
from __future__ import annotations

import csv
import html
import math
from pathlib import Path
from typing import Sequence

import numpy as np

from ..common.data_models import (
    ANGLE_KEYS, AnalysisSummary, Event, FrameRecord, MetricsResult,
    ProjectManifest, SCHEMA_VERSION, write_json)
from ..common.halpe26 import ANGLE_DISPLAY_NAMES, KEYPOINT_NAMES


# ---------------- JSON 导出 ----------------
def export_manifest(path: str | Path, manifest: ProjectManifest) -> None:
    """导出 manifest.json（字段顺序按 dataclass 定义序，由 asdict 保证）。"""
    write_json(Path(path), manifest.to_dict())


def export_keypoints_json(path: str | Path, meta: dict,
                          frames: Sequence[FrameRecord]) -> None:
    """导出 keypoints.json：{"schema_version", "meta", "frames"}。"""
    write_json(Path(path), {
        'schema_version': SCHEMA_VERSION,
        'meta': meta,
        'frames': [f.to_dict() for f in frames],
    })


def export_events_json(path: str | Path, events: Sequence[Event],
                       gait_summary: dict | None = None) -> None:
    """导出 events.json：{"schema_version", "events"[, "gait_summary"]}。

    gait_summary 为步态时空参数汇总（app.events.gait.gait_temporal_params
    的输出），可选传入，向后兼容。
    """
    payload: dict = {
        'schema_version': SCHEMA_VERSION,
        'events': [e.to_dict() for e in events],
    }
    if gait_summary is not None:
        payload['gait_summary'] = gait_summary
    write_json(Path(path), payload)


# ---------------- motion.json（自研标注客户端数据源） ----------------
def _num(v, nd: int = 2):
    """数值 JSON 化：None/NaN/Inf → None；否则保留 nd 位小数。"""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return round(v, nd)


def export_motion_json(path: str | Path, manifest: ProjectManifest,
                       metrics: MetricsResult, video_id: str) -> None:
    """导出 motion.json：自研标注客户端（Electron）的时序数据源。

    结构：
    {"schema_version", "video_id", "source_video", "fps", "frame_count",
     "width", "height", "created_at",
     "frames": [{"frameIndex", "timestampMs", "metrics": {...}}]}

    - metrics 键与 metrics.csv 列名一致（left_knee_angle 等），
      另含 8 个关节角速度（*_angvel）；
    - 无效帧（NaN）指标序列化为 null（JSON 不允许 NaN）；
    - 客户端帧对齐约定：跳帧一律用 frames[i].timestampMs 查表，
      不要用 fps 自行换算（29.97 等非整数帧率会漂移）。
    """
    n = metrics.frame_count
    angles = dict(getattr(metrics, 'angles', None) or {})
    angvel = dict(getattr(metrics, 'angular_velocity', None) or {})
    seg = dict(getattr(metrics, 'segment_angles', None) or {})
    traj = dict(getattr(metrics, 'trajectories', None) or {})
    pelvis_x, pelvis_y = _col2(traj.get('pelvis'))
    head_x, head_y = _col2(traj.get('head'))
    lheel_x, lheel_y = _col2(traj.get('left_heel'))
    rheel_x, rheel_y = _col2(traj.get('right_heel'))

    frames = []
    for i in range(n):
        fi = _at(metrics.frame_indices, i)
        m: dict = {}
        # 8 个关节角 + 角速度（2 位小数）
        for k in ANGLE_KEYS:
            m[f'{k}_angle'] = _num(_at(angles.get(k), i))
            m[f'{k}_angvel'] = _num(_at(angvel.get(k), i))
        # 躯干倾角 / 节段角 / 轨迹 / 速度（2 位小数）
        m['torso_lean_angle'] = _num(_at(metrics.torso_lean, i))
        for k in ('left_thigh', 'right_thigh', 'left_shank', 'right_shank',
                  'left_shoulder', 'right_shoulder'):
            m[f'{k}_angle'] = _num(_at(seg.get(k), i))
        m['pelvis_x'] = _num(_at(pelvis_x, i))
        m['pelvis_y'] = _num(_at(pelvis_y, i))
        m['pelvis_speed_px_s'] = _num(_at(getattr(metrics, 'pelvis_speed', None), i))
        m['head_x'] = _num(_at(head_x, i))
        m['head_y'] = _num(_at(head_y, i))
        m['left_heel_x'] = _num(_at(lheel_x, i))
        m['left_heel_y'] = _num(_at(lheel_y, i))
        m['right_heel_x'] = _num(_at(rheel_x, i))
        m['right_heel_y'] = _num(_at(rheel_y, i))
        # 姿态质量（4 位小数）
        m['pose_quality'] = _num(_at(getattr(metrics, 'pose_quality', None), i), 4)
        m['valid_ratio'] = _num(_at(getattr(metrics, 'valid_ratio', None), i), 4)
        frames.append({
            'frameIndex': int(fi) if fi is not None else None,
            'timestampMs': _num(_at(metrics.timestamps_ms, i), 1),
            'metrics': m,
        })

    write_json(Path(path), {
        'schema_version': SCHEMA_VERSION,
        'video_id': str(video_id),
        'source_video': manifest.source_video,
        'fps': round(float(manifest.fps), 3),
        'frame_count': n,
        'width': manifest.width,
        'height': manifest.height,
        'created_at': manifest.created_at,
        'frames': frames,
    })


# ---------------- 指标 CSV ----------------
# 角度列顺序（与规范列名一一对应）
_ANGLE_COLUMN_ORDER = ('left_knee', 'right_knee', 'left_hip', 'right_hip',
                       'left_ankle', 'right_ankle', 'left_elbow', 'right_elbow')


def _fmt(v, nd: int = 2) -> str:
    """数值格式化：None/NaN/Inf → 空串；否则固定小数位。"""
    if v is None:
        return ''
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ''
    if not math.isfinite(v):
        return ''
    return f'{v:.{nd}f}'


def _at(seq, i):
    """一维序列安全取值（越界/缺失返回 None）。"""
    if seq is None:
        return None
    try:
        return seq[i]
    except (IndexError, TypeError):
        return None


def _at2(mat, i, j):
    """二维数组安全取值（越界/缺失返回 None）。"""
    if mat is None:
        return None
    try:
        return mat[i, j]
    except (IndexError, TypeError):
        return None


def _col2(seq) -> tuple:
    """(F,2) 轨迹 → (x 列, y 列)；非法返回 (None, None)。"""
    if seq is None:
        return None, None
    arr = np.asarray(seq, dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        return None, None
    return arr[:, 0], arr[:, 1]


def export_metrics_csv(path: str | Path, metrics: MetricsResult) -> None:
    """导出逐帧指标 CSV（NaN 写空串；角度保留 2 位小数）。"""
    n = metrics.frame_count
    header = (['frame_index', 'timestamp_ms']
              + [f'{k}_angle' for k in _ANGLE_COLUMN_ORDER]
              + ['torso_lean_angle',
                 'left_thigh_angle', 'right_thigh_angle',
                 'left_shank_angle', 'right_shank_angle',
                 'left_shoulder_angle', 'right_shoulder_angle',
                 'pelvis_x', 'pelvis_y', 'pelvis_speed_px_s',
                 'head_x', 'head_y',
                 'left_heel_x', 'left_heel_y',
                 'right_heel_x', 'right_heel_y',
                 'pose_quality', 'valid_ratio', 'missing_ratio']
              + [f'speed_{name}' for name in KEYPOINT_NAMES]
              + [f'angvel_{k}' for k in ANGLE_KEYS])

    traj = dict(getattr(metrics, 'trajectories', None) or {})
    pelvis_x, pelvis_y = _col2(traj.get('pelvis'))
    head_x, head_y = _col2(traj.get('head'))
    lheel_x, lheel_y = _col2(traj.get('left_heel'))
    rheel_x, rheel_y = _col2(traj.get('right_heel'))
    angles = dict(getattr(metrics, 'angles', None) or {})
    angvel = dict(getattr(metrics, 'angular_velocity', None) or {})
    seg = dict(getattr(metrics, 'segment_angles', None) or {})
    speeds = getattr(metrics, 'keypoint_speeds', None)
    pelvis_speed = getattr(metrics, 'pelvis_speed', None)
    quality = getattr(metrics, 'pose_quality', None)
    valid_ratio = getattr(metrics, 'valid_ratio', None)
    missing_ratio = getattr(metrics, 'missing_ratio', None)

    rows = []
    for i in range(n):
        fi = _at(metrics.frame_indices, i)
        row = [int(fi) if fi is not None else '', _fmt(_at(metrics.timestamps_ms, i))]
        # 8 个关节角 + 躯干倾角（2 位小数）
        for k in _ANGLE_COLUMN_ORDER:
            row.append(_fmt(_at(angles.get(k), i)))
        row.append(_fmt(_at(metrics.torso_lean, i)))
        # 6 条节段角
        row.extend(_fmt(_at(seg.get(k), i))
                   for k in ('left_thigh', 'right_thigh',
                             'left_shank', 'right_shank',
                             'left_shoulder', 'right_shoulder'))
        # 骨盆/头部/脚跟轨迹与骨盆速度
        row.extend([
            _fmt(_at(pelvis_x, i)), _fmt(_at(pelvis_y, i)),
            _fmt(_at(pelvis_speed, i)),
            _fmt(_at(head_x, i)), _fmt(_at(head_y, i)),
            _fmt(_at(lheel_x, i)), _fmt(_at(lheel_y, i)),
            _fmt(_at(rheel_x, i)), _fmt(_at(rheel_y, i)),
        ])
        # 质量/有效比例/缺失比例（4 位小数）
        row.extend([
            _fmt(_at(quality, i), 4),
            _fmt(_at(valid_ratio, i), 4),
            _fmt(_at(missing_ratio, i), 4),
        ])
        # 26 个关键点速度
        row.extend(_fmt(_at2(speeds, i, j)) for j in range(len(KEYPOINT_NAMES)))
        # 8 个角度角速度
        row.extend(_fmt(_at(angvel.get(k), i)) for k in ANGLE_KEYS)
        rows.append(row)

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ---------------- HTML 报告 ----------------
_HTML_CSS = """
body { font-family: 'Microsoft YaHei', 'PingFang SC', 'Segoe UI', sans-serif;
       margin: 0; background: #f5f6f8; color: #1a202c; }
.container { max-width: 960px; margin: 0 auto; padding: 28px 20px 40px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; border-left: 4px solid #2b6cb0; padding-left: 10px;
     margin: 30px 0 10px; }
.meta { color: #718096; font-size: 13px; margin: 0 0 8px; }
table { border-collapse: collapse; width: 100%; background: #fff;
        font-size: 13px; }
th, td { border: 1px solid #d8dde3; padding: 6px 10px; text-align: left; }
th { background: #edf2f7; white-space: nowrap; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
.chart { background: #fff; border: 1px solid #d8dde3; padding: 8px; }
svg { display: block; }
svg text.tick { font-size: 11px; fill: #4a5568; }
svg text.legend { font-size: 12px; fill: #2d3748; }
p.nodata { color: #718096; background: #fff; border: 1px dashed #cbd5e0;
           padding: 14px; font-size: 13px; }
footer { margin-top: 34px; padding: 10px 14px; background: #fff8e1;
         border: 1px solid #e6c34d; color: #6b5900; font-size: 12px;
         line-height: 1.6; }
"""

_DISCLAIMER = ('二维未标定数据：仅像素坐标与二维投影角度，'
               '不代表真实三维角度/速度/距离')


def _esc(v) -> str:
    """HTML 文本转义。"""
    return html.escape(str(v))


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]],
           num_cols: set[int] | None = None) -> str:
    """生成简单两段式表格 HTML。"""
    num_cols = num_cols or set()
    th = ''.join(f'<th>{h}</th>' for h in headers)
    trs = []
    for r in rows:
        tds = []
        for j, c in enumerate(r):
            cls = ' class="num"' if j in num_cols else ''
            tds.append(f'<td{cls}>{c}</td>')
        trs.append('<tr>' + ''.join(tds) + '</tr>')
    return ('<table><thead><tr>' + th + '</tr></thead>'
            '<tbody>' + ''.join(trs) + '</tbody></table>')


def _trend_svg(metrics: MetricsResult, width: int = 880, height: int = 340) -> str:
    """左右膝角 + 躯干倾角随时间折线图（内联 SVG，含图例与坐标轴）。

    超过 1500 个数据点时等间隔降采样；NaN 断点处折线断开。
    """
    series_def = (
        ('左膝角', '#2f855a', (metrics.angles or {}).get('left_knee')),
        ('右膝角', '#2b6cb0', (metrics.angles or {}).get('right_knee')),
        ('躯干倾角', '#dd6b20', metrics.torso_lean),
    )
    series = [(label, color, np.asarray(arr, dtype=float))
              for label, color, arr in series_def if arr is not None]
    t_ms = np.asarray(metrics.timestamps_ms, dtype=float)
    n = len(t_ms)
    if n == 0 or not series:
        return '<p class="nodata">无逐帧指标数据</p>'

    # 大数据量等间隔降采样（上限约 1500 点）
    if n > 1500:
        step = math.ceil(n / 1500)
        idx = np.arange(0, n, step)
    else:
        idx = np.arange(n)
    t_s = t_ms / 1000.0

    # y 域取全部序列有限值的 min/max 并留边距
    vals = [float(v) for _, _, arr in series for v in arr[idx]
            if np.isfinite(v)]
    if not vals:
        return '<p class="nodata">无有效角度数据</p>'
    ymin, ymax = min(vals), max(vals)
    if ymax - ymin < 1e-6:
        ymax = ymin + 1.0
    pad = (ymax - ymin) * 0.08
    ymin, ymax = ymin - pad, ymax + pad
    xmin, xmax = float(t_s[idx[0]]), float(t_s[idx[-1]])
    if xmax - xmin < 1e-9:
        xmax = xmin + 1.0

    ml, mr, mt, mb = 64, 18, 18, 46       # 绘图区边距
    pw, ph = width - ml - mr, height - mt - mb

    def x_of(t: float) -> float:
        return ml + (t - xmin) / (xmax - xmin) * pw

    def y_of(v: float) -> float:
        return mt + (ymax - v) / (ymax - ymin) * ph

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" '
             f'viewBox="0 0 {width} {height}" width="100%" '
             f'role="img" aria-label="关节角随时间折线图">']
    # 水平网格线 + y 刻度
    for k in range(5):
        v = ymin + (ymax - ymin) * k / 4
        y = y_of(v)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{width - mr}" '
                     f'y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(f'<text x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end" '
                     f'class="tick">{v:.0f}</text>')
    # 垂直网格线 + x 刻度（时间，秒）
    for k in range(6):
        t = xmin + (xmax - xmin) * k / 5
        x = x_of(t)
        parts.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" '
                     f'y2="{height - mb}" stroke="#e2e8f0" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{height - mb + 18}" '
                     f'text-anchor="middle" class="tick">{t:.1f}s</text>')
    # 坐标轴
    parts.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{height - mb}" '
                 f'stroke="#4a5568" stroke-width="1.5"/>')
    parts.append(f'<line x1="{ml}" y1="{height - mb}" x2="{width - mr}" '
                 f'y2="{height - mb}" stroke="#4a5568" stroke-width="1.5"/>')
    # y 轴标题
    parts.append(f'<text x="14" y="{mt + ph / 2:.0f}" class="tick" '
                 f'transform="rotate(-90 14 {mt + ph / 2:.0f})" '
                 f'text-anchor="middle">角度 (°)</text>')

    # 折线（NaN 断点拆成多段）
    for label, color, arr in series:
        segs, cur = [], []
        for i in idx:
            v = float(arr[int(i)])
            if math.isfinite(v):
                cur.append(f'{x_of(float(t_s[int(i)])):.1f},{y_of(v):.1f}')
            elif cur:
                segs.append(' '.join(cur))
                cur = []
        if cur:
            segs.append(' '.join(cur))
        for s in segs:
            parts.append(f'<polyline points="{s}" fill="none" stroke="{color}" '
                         f'stroke-width="1.6" stroke-linejoin="round"/>')

    # 图例（绘图区左上角）
    for j, (label, color, _) in enumerate(series):
        ly = mt + 16 + j * 22
        parts.append(f'<rect x="{ml + 14}" y="{ly - 10}" width="18" '
                     f'height="4" fill="{color}" rx="2"/>')
        parts.append(f'<text x="{ml + 40}" y="{ly}" class="legend">'
                     f'{_esc(label)}</text>')
    parts.append('</svg>')
    return ''.join(parts)


def export_html_report(path: str | Path, project_name: str,
                       manifest: ProjectManifest, summary: AnalysisSummary,
                       metrics: MetricsResult,
                       events: Sequence[Event]) -> None:
    """导出单文件自包含 HTML 分析报告（内联 CSS + 内联 SVG 折线图）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # 视频与模型信息（来自 manifest）
    meta_rows = [
        ('源视频', _esc(manifest.source_video)),
        ('帧率 / 帧数', f'{manifest.fps:.3f} fps / {manifest.frame_count} 帧'),
        ('分辨率', f'{manifest.width} x {manifest.height}'),
        ('姿态模型', _esc(manifest.pose_model)),
        ('检测器', _esc(manifest.detector)),
        ('创建时间', _esc(manifest.created_at)),
        ('分析状态', _esc(manifest.analysis_status)),
    ]

    # 概要统计
    overview_rows = [
        ('总帧数', f'{summary.total_frames}'),
        ('有效帧数', f'{summary.valid_frames}'),
        ('有效帧比例', f'{summary.valid_ratio * 100:.1f}%'),
        ('平均姿态质量', f'{summary.avg_pose_quality:.3f}'),
    ]

    # 角度统计（min/max/mean）
    stats = getattr(summary, 'angle_stats', None) or {}
    angle_rows = []
    for k in ANGLE_KEYS:
        st = stats.get(k)
        if not st:
            continue
        angle_rows.append((
            _esc(ANGLE_DISPLAY_NAMES.get(k, k)),
            _fmt(st.get('min')) or '—',
            _fmt(st.get('max')) or '—',
            _fmt(st.get('mean')) or '—',
        ))

    # 事件表
    event_rows = []
    for e in events or []:
        event_rows.append((
            f'#{int(e.frame_index)}',
            f'{float(e.timestamp_ms) / 1000.0:.2f} s',
            _esc(e.type),
            _fmt(e.value) or '—',
            _esc(e.unit),
            _fmt(e.confidence, 3) or '—',
        ))

    # 折线图（左膝角 + 右膝角 + 躯干倾角）
    svg = _trend_svg(metrics) if metrics is not None else \
        '<p class="nodata">无逐帧指标数据</p>'

    parts = []
    parts.append('<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
                 '<meta charset="utf-8">\n'
                 f'<title>{_esc(project_name)} - 姿态分析报告</title>\n'
                 f'<style>{_HTML_CSS}</style>\n</head>\n<body>\n'
                 '<div class="container">\n')
    parts.append(f'<h1>{_esc(project_name)} 姿态分析报告</h1>\n')
    parts.append(f'<p class="meta">源视频：{_esc(manifest.source_video)} · '
                 f'生成时间：{_esc(manifest.created_at)}</p>\n')

    parts.append('<h2>概要统计</h2>\n')
    parts.append(_table(('指标', '数值'), overview_rows, num_cols={1}))

    parts.append('<h2>视频与模型信息</h2>\n')
    parts.append(_table(('项目', '内容'), meta_rows))

    parts.append('<h2>角度统计（度）</h2>\n')
    if angle_rows:
        parts.append(_table(('角度', '最小', '最大', '平均'),
                            angle_rows, num_cols={1, 2, 3}))
    else:
        parts.append('<p class="nodata">无角度统计数据</p>')

    parts.append('<h2>关节角随时间变化</h2>\n')
    parts.append(f'<div class="chart">{svg}</div>\n')

    parts.append('<h2>关键事件</h2>\n')
    if event_rows:
        parts.append(_table(('帧', '时间', '类型', '数值', '单位', '置信度'),
                            event_rows, num_cols={0, 1, 3, 5}))
    else:
        parts.append('<p class="nodata">未检测到关键事件</p>')

    parts.append(f'<footer>免责声明：{_DISCLAIMER}</footer>\n')
    parts.append('</div>\n</body>\n</html>\n')

    p.write_text(''.join(parts), encoding='utf-8')
