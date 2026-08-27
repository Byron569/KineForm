"""GUI 对话框集合：视频信息详情、结果概览详情、模型下载确认框。

模块顶层不 import torch/mmpose/cv2 等重依赖，保证界面启动秒开。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QLabel, QMessageBox,
                               QScrollArea, QTabWidget, QTableWidget,
                               QTableWidgetItem, QTextEdit, QVBoxLayout,
                               QWidget)

from ..common.data_models import AnalysisResult, VideoInfo

# 角度键 → 中文显示名（主窗口概览与结果详情对话框共用）
ANGLE_LABELS: dict[str, str] = {
    'left_knee': '左膝角',
    'right_knee': '右膝角',
    'left_hip': '左髋角',
    'right_hip': '右髋角',
    'left_ankle': '左踝角',
    'right_ankle': '右踝角',
    'left_elbow': '左肘角',
    'right_elbow': '右肘角',
    'torso_lean': '躯干倾角',
}


def angle_label(key: str) -> str:
    """角度键 → 中文名；未登记的键原样返回。"""
    return ANGLE_LABELS.get(key, key)


def vfr_text(vfr: Optional[bool]) -> str:
    """可变帧率三态文案：是(将转CFR) / 否 / 未知。"""
    if vfr is True:
        return '是(将转CFR)'
    if vfr is False:
        return '否'
    return '未知'


def format_duration(seconds: float) -> str:
    """秒数 → 'h:mm:ss.s' 或 'm:ss.s'；非正数返回 '—'。"""
    if seconds is None or seconds <= 0:
        return '—'
    total = float(seconds)
    h = int(total // 3600)
    m = int(total % 3600 // 60)
    s = total % 60
    if h:
        return f'{h}:{m:02d}:{s:04.1f}'
    return f'{m}:{s:04.1f}'


def confirm_missing_checkpoint(parent, model_name: str) -> bool:
    """模型权重缺失确认框：用户确认自动下载（需联网）时返回 True。"""
    answer = QMessageBox.question(
        parent, '模型权重缺失',
        f'模型「{model_name}」的权重文件缺失，将自动下载（需联网）。\n是否继续？',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No)
    return answer == QMessageBox.StandardButton.Yes


def _selectable(text: str) -> QLabel:
    """构造可鼠标选中复制的文本标签。"""
    label = QLabel(str(text))
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _make_table(rows: int, headers: list[str]) -> QTableWidget:
    """构造只读表格（隐藏行号、不可编辑、不可选中）。"""
    table = QTableWidget(rows, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.horizontalHeader().setStretchLastSection(True)
    return table


class VideoInfoDialog(QDialog):
    """视频信息详情对话框：显示探测到的完整字段。"""

    def __init__(self, parent, info: VideoInfo):
        super().__init__(parent)
        self.setWindowTitle(f'视频信息 - {Path(info.path).name}')
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        rows = [
            ('文件路径', info.path),
            ('宽 × 高', f'{info.width} × {info.height} 像素'),
            ('帧率', f'{info.fps:.3f} fps'),
            ('总帧数（探测值）', f'{info.frame_count}'),
            ('时长', format_duration(info.duration_s)),
            ('是否可变帧率', vfr_text(info.vfr)),
            ('视频编码', info.video_codec or '未知'),
            ('是否含音频', '是' if info.has_audio else '否'),
            ('探测方式', info.probe_method or '未知'),
        ]
        for name, value in rows:
            form.addRow(name, _selectable(value))
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class ResultDetailDialog(QDialog):
    """分析结果概览详情：汇总指标、角度统计、事件列表与警告。"""

    def __init__(self, parent, result: AnalysisResult):
        super().__init__(parent)
        self.setWindowTitle(f'分析结果详情 - {result.project_dir.name}')
        self.setMinimumSize(600, 520)

        layout = QVBoxLayout(self)
        summary = result.summary
        manifest = result.manifest

        # 基本信息
        form = QFormLayout()
        form.addRow('项目目录', _selectable(str(result.project_dir)))
        form.addRow('姿态模型', _selectable(manifest.pose_model))
        form.addRow('输出帧率', _selectable(f'{manifest.fps:.3f} fps'))
        form.addRow('总帧数', _selectable(str(summary.total_frames)))
        form.addRow('有效帧比例', _selectable(
            f'{summary.valid_ratio * 100:.1f}%'
            f'（{summary.valid_frames}/{summary.total_frames} 帧）'))
        form.addRow('平均姿态质量',
                    _selectable(f'{summary.avg_pose_quality * 100:.1f}%'))
        form.addRow('推理耗时', _selectable(
            f'{manifest.inference_ms_per_frame:.1f} ms/帧'))
        form.addRow('事件数', _selectable(str(len(summary.events))))
        layout.addLayout(form)

        # 角度统计表
        layout.addWidget(QLabel('角度统计（度）'))
        stats = list(summary.angle_stats.items())
        angle_table = _make_table(len(stats), ['角度', '最小', '最大', '均值'])
        for r, (key, st) in enumerate(stats):
            angle_table.setItem(r, 0, QTableWidgetItem(angle_label(key)))
            angle_table.setItem(r, 1, QTableWidgetItem(f"{st['min']:.1f}"))
            angle_table.setItem(r, 2, QTableWidgetItem(f"{st['max']:.1f}"))
            angle_table.setItem(r, 3, QTableWidgetItem(f"{st['mean']:.1f}"))
        layout.addWidget(angle_table, 2)

        # 事件表
        layout.addWidget(QLabel(f'事件（{len(summary.events)} 个）'))
        events = summary.events
        event_table = _make_table(
            len(events), ['类型', '帧号', '时间(ms)', '数值', '单位', '置信度'])
        for r, ev in enumerate(events):
            event_table.setItem(r, 0, QTableWidgetItem(ev.type))
            event_table.setItem(r, 1, QTableWidgetItem(str(ev.frame_index)))
            event_table.setItem(
                r, 2, QTableWidgetItem(f'{ev.timestamp_ms:.0f}'))
            event_table.setItem(r, 3, QTableWidgetItem(f'{ev.value:.2f}'))
            event_table.setItem(r, 4, QTableWidgetItem(ev.unit))
            event_table.setItem(
                r, 5, QTableWidgetItem(f'{ev.confidence:.3f}'))
        layout.addWidget(event_table, 2)

        # 警告列表
        layout.addWidget(QLabel('警告'))
        warn_edit = QTextEdit()
        warn_edit.setReadOnly(True)
        warn_edit.setPlainText(
            '\n'.join(summary.warnings) if summary.warnings else '无警告')
        warn_edit.setMaximumHeight(96)
        layout.addWidget(warn_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


# 步态指标键 → 中文显示名（步态详情对话框用）。键为 step dict 的顶层键
# 或 '子字典.键' 点号嵌套路径，与 events/gait.py、events/fatigue.py、
# biomechanics/references.py 的指标路径约定一致。
GAIT_METRIC_LABELS: dict[str, str] = {
    # 顶层：时空参数 + 距离/振幅
    'contact_time_ms': '触地时间',
    'flight_time_ms': '腾空时间',
    'stride_time_ms': '步态周期',
    'stance_ratio': '支撑比',
    'flight_support_ratio': '腾空/支撑比',
    'stride_length_px': '步长',
    'stride_length_norm': '步长(归一化)',
    'stride_length_m': '步长',
    'pelvis_vertical_range_px': '骨盆垂直振幅',
    'pelvis_vertical_range_norm': '骨盆垂直振幅(归一化)',
    # 触地瞬间
    'touchdown.knee_angle': '触地膝角',
    'touchdown.hip_angle': '触地髋角',
    'touchdown.ankle_angle': '触地踝角',
    'touchdown.torso_lean_angle': '触地躯干倾角',
    'touchdown.thigh_angle': '触地大腿角',
    'touchdown.shank_angle': '触地小腿角',
    'touchdown.shoulder_angle': '触地肩角',
    'touchdown.elbow_angle': '触地肘角',
    'touchdown.foot_pelvis_dist_px': '触地脚-骨盆距离',
    'touchdown.foot_pelvis_dist_norm': '触地脚-骨盆距离(归一化)',
    'touchdown.foot_rel_vx_px_s': '触地前脚相对速度',
    # 支撑中期 / 离地瞬间
    'midstance.knee_angle': '支撑中期膝角',
    'midstance.hip_angle': '支撑中期髋角',
    'midstance.ankle_angle': '支撑中期踝角',
    'midstance.shoulder_angle': '支撑中期肩角',
    'midstance.elbow_angle': '支撑中期肘角',
    'toe_off.knee_angle': '离地膝角',
    'toe_off.hip_angle': '离地髋角',
    'toe_off.ankle_angle': '离地踝角',
    'toe_off.shoulder_angle': '离地肩角',
    'toe_off.elbow_angle': '离地肘角',
    # 支撑期 / 摆动期
    'stance.min_knee_angle': '支撑期最小膝角',
    'stance.knee_collapse_deg': '支撑期膝塌陷',
    'stance.knee_rom_deg': '支撑期膝活动度',
    'stance.ankle_rom_deg': '支撑期踝活动度',
    'stance.hip_rom_deg': '支撑期髋活动度',
    'swing.min_knee_angle': '摆动期最小膝角',
    'swing.max_thigh_angle': '摆动期最大大腿角',
    # 全局指标
    'cadence_hz': '步频',
}


def gait_metric_label(path: str) -> str:
    """步态指标键（含 'touchdown.knee_angle' 点号嵌套路径）→ 中文名；
    未登记的键原样返回。"""
    return GAIT_METRIC_LABELS.get(path, path)


class GaitDetailDialog(QDialog):
    """步态分析详情：每步特征、精英参考对比、疲劳趋势与起跳步。

    数据来自 events.json 的 gait_summary（orchestrator 产出）。
    任何子键都可能缺失或为 None，展示层全部 .get 容错、缺值显示 '—'。
    """

    # band → 单元格背景色（deviated 浅黄、outlier 浅红；common/None 不着色）
    _BAND_COLORS = {
        'deviated': QColor(255, 249, 196),
        'outlier': QColor(255, 205, 210),
    }
    _BAND_LABELS = {'common': '常见', 'deviated': '偏离', 'outlier': '离群'}

    def __init__(self, parent, gait_summary: dict):
        super().__init__(parent)
        self.setWindowTitle('步态分析详情')
        self.resize(820, 600)
        self.setMinimumSize(640, 420)

        gs = gait_summary if isinstance(gait_summary, dict) else {}
        steps = [s for s in (gs.get('steps') or []) if isinstance(s, dict)]

        layout = QVBoxLayout(self)

        # 顶部摘要：步数（左右分计）+ 步频（如有）
        if gs:
            n_left = sum(1 for s in steps if s.get('side') == 'left')
            n_right = sum(1 for s in steps if s.get('side') == 'right')
            text = f'步数：{len(steps)}（左 {n_left} / 右 {n_right}）'
            cadence = self._num(gs.get('cadence_spm'))
            if cadence is not None:
                text += f'　步频：{cadence:.1f} 步/分'
        else:
            text = '未生成步态分析数据。'
        summary = QLabel(text)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        tabs = QTabWidget()
        tabs.addTab(self._build_steps_tab(steps), '每步特征')
        tabs.addTab(self._build_references_tab(gs), '精英参考对比')
        tabs.addTab(self._build_fatigue_tab(gs), '疲劳趋势')
        tabs.addTab(self._build_takeoff_tab(gs), '起跳步')
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    # ---------------- 各页构建 ----------------
    def _build_steps_tab(self, steps: list) -> QWidget:
        """① 每步特征：一行一步，缺值显示 '—'。"""
        page = QWidget()
        vl = QVBoxLayout(page)
        if not steps:
            hint = QLabel('未检测到有效步数据（缺少步态触地/离地事件）。')
            hint.setWordWrap(True)
            vl.addWidget(hint)
            vl.addStretch(1)
            return page

        headers = ['步序', '侧', '触地帧', '触地(ms)', '腾空(ms)', '周期(ms)',
                   '支撑比', '步长', '触地膝角', '支撑最小膝角', '膝塌陷(°)',
                   '摆动最小膝角']
        table = _make_table(len(steps), headers)
        for r, s in enumerate(steps):
            td = s.get('touchdown') or {}
            stance = s.get('stance') or {}
            swing = s.get('swing') or {}
            vals = [
                str(r + 1),
                self._side_text(s.get('side')),
                self._int_text(s.get('td_frame')),
                self._fmt(s.get('contact_time_ms')),
                self._fmt(s.get('flight_time_ms')),
                self._fmt(s.get('stride_time_ms')),
                self._fmt(s.get('stance_ratio'), 3),
                self._stride_text(s),
                self._fmt(td.get('knee_angle')),
                self._fmt(stance.get('min_knee_angle')),
                self._fmt(stance.get('knee_collapse_deg')),
                self._fmt(swing.get('min_knee_angle')),
            ]
            for c, text in enumerate(vals):
                table.setItem(r, c, QTableWidgetItem(text))
        table.resizeColumnsToContents()
        vl.addWidget(table, 1)
        vl.addWidget(self._small_label(
            '角度单位度、时间毫秒；步长优先显示米（已标定身高时），'
            '否则像素；"—" 表示该步数据缺失。'))
        return page

    def _build_references_tab(self, gs: dict) -> QWidget:
        """② 精英参考对比：每个参考一节（QGroupBox 纵向排列）。"""
        page = QWidget()
        vl = QVBoxLayout(page)
        refs = [r for r in (gs.get('reference_comparison') or [])
                if isinstance(r, dict)]
        if not refs:
            hint = QLabel('无精英参考对比数据。')
            hint.setWordWrap(True)
            vl.addWidget(hint)
            vl.addStretch(1)
            return page

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_vl = QVBoxLayout(inner)
        for ref in refs:
            inner_vl.addWidget(self._build_reference_group(ref))
        inner_vl.addStretch(1)
        scroll.setWidget(inner)
        vl.addWidget(scroll)
        return page

    def _build_reference_group(self, ref: dict) -> QGroupBox:
        """单个参考的小节：标题 + 每步对比表 + 侧汇总 + 小字说明。"""
        title = (f"{ref.get('reference') or '未知参考'} - "
                 f"{ref.get('source') or '来源未知'}"
                 f"（{ref.get('sample') or '样本未知'}）")
        box = QGroupBox(title)
        vl = QVBoxLayout(box)

        ref_steps = [s for s in (ref.get('steps') or [])
                     if isinstance(s, dict)]
        # 列 = 该参考下出现过的全部指标路径（保持首次出现顺序）
        paths: list[str] = []
        for st in ref_steps:
            for p in (st.get('metrics') or {}):
                if p not in paths:
                    paths.append(p)
        headers = ['触地帧', '侧'] + [gait_metric_label(p) for p in paths]
        table = _make_table(len(ref_steps), headers)
        for r, st in enumerate(ref_steps):
            table.setItem(r, 0,
                          QTableWidgetItem(self._int_text(st.get('td_frame'))))
            table.setItem(r, 1,
                          QTableWidgetItem(self._side_text(st.get('side'))))
            metrics = st.get('metrics') or {}
            for c, p in enumerate(paths):
                item = QTableWidgetItem(self._metric_cell_text(metrics.get(p)))
                color = self._BAND_COLORS.get((metrics.get(p) or {}).get('band'))
                if color is not None:
                    item.setBackground(color)
                table.setItem(r, c + 2, item)
        table.resizeColumnsToContents()
        vl.addWidget(table)

        # side_summary：每侧每指标 mean_z + band 的紧凑表
        side_summary = ref.get('side_summary') or {}
        rows = [(side, p, info)
                for side, per in side_summary.items()
                for p, info in (per or {}).items()]
        if rows:
            sum_table = _make_table(len(rows), ['侧', '指标', '平均z', '分层'])
            for r, (side, p, info) in enumerate(rows):
                info = info if isinstance(info, dict) else {}
                band = info.get('band')
                sum_table.setItem(r, 0,
                                  QTableWidgetItem(self._side_text(side)))
                sum_table.setItem(r, 1,
                                  QTableWidgetItem(gait_metric_label(p)))
                sum_table.setItem(r, 2, QTableWidgetItem(
                    self._fmt(info.get('mean_z'), 2)))
                sum_table.setItem(r, 3, QTableWidgetItem(
                    self._BAND_LABELS.get(band, '—') if band else '—'))
            sum_table.resizeColumnsToContents()
            vl.addWidget(sum_table)

        # 全局指标（如步频）
        global_out = ref.get('global') or {}
        parts = []
        for name, m in global_out.items():
            if not isinstance(m, dict):
                continue
            v = self._num(m.get('value'))
            if v is None:
                continue
            seg = f'{gait_metric_label(name)} {v:.2f}'
            ref_mean = self._num(m.get('ref_mean'))
            if ref_mean is not None:
                seg += f'（参考 {ref_mean:.2f}）'
            z = self._num(m.get('z'))
            if z is not None:
                seg += f'，z={z:+.2f}'
            parts.append(seg)
        if parts:
            vl.addWidget(self._small_label('全局指标：' + '；'.join(parts)))

        # 不比较指标原因
        skipped = ref.get('skipped_metrics') or {}
        if skipped:
            lines = '\n'.join(f'• {gait_metric_label(p)}：{reason}'
                              for p, reason in skipped.items())
            vl.addWidget(self._small_label('不比较指标：\n' + lines))

        if ref.get('disclaimer'):
            vl.addWidget(self._small_label(str(ref.get('disclaimer'))))
        return box

    def _build_fatigue_tab(self, gs: dict) -> QWidget:
        """③ 疲劳趋势：前/后半程逐指标均值对比。"""
        page = QWidget()
        vl = QVBoxLayout(page)
        ft = gs.get('fatigue_trend')
        if not isinstance(ft, dict) or not ft:
            hint = QLabel('步数不足，无法计算疲劳趋势。')
            hint.setWordWrap(True)
            vl.addWidget(hint)
            vl.addStretch(1)
            return page

        halves = ft.get('halves') or {}
        first = halves.get('first') or {}
        second = halves.get('second') or {}
        keys = list(first) + [k for k in second if k not in first]
        delta = ft.get('delta') or {}
        delta_pct = ft.get('delta_pct') or {}

        header = QLabel('前/后半程均值对比（Δ = 后半 − 前半，正值 = 后程增大）')
        header.setWordWrap(True)
        vl.addWidget(header)

        table = _make_table(len(keys),
                            ['指标', '前半均值', '后半均值', 'Δ', 'Δ%'])
        for r, k in enumerate(keys):
            # stance_ratio 量级约 0.2，1 位小数过粗（见 fatigue.py 约定）
            nd = 3 if k == 'stance_ratio' else 1
            table.setItem(r, 0, QTableWidgetItem(gait_metric_label(k)))
            table.setItem(r, 1, QTableWidgetItem(self._fmt(first.get(k), nd)))
            table.setItem(r, 2, QTableWidgetItem(self._fmt(second.get(k), nd)))
            table.setItem(r, 3, QTableWidgetItem(self._fmt(delta.get(k), nd)))
            table.setItem(r, 4, QTableWidgetItem(
                self._fmt(delta_pct.get(k), 1, '%')))
        table.resizeColumnsToContents()
        vl.addWidget(table, 1)

        n_txt = self._int_text(ft.get('n_steps'))
        split_txt = self._int_text(ft.get('split_at'))
        if n_txt != '—' and split_txt != '—':
            second_n = int(float(ft.get('n_steps'))) \
                - int(float(ft.get('split_at')))
            vl.addWidget(self._small_label(
                f'共 {n_txt} 步：前半 {split_txt} 步 / 后半 {second_n} 步'
                '（按触地帧顺序对半切分，奇数步时前半多一步）'))
        return page

    def _build_takeoff_tab(self, gs: dict) -> QWidget:
        """④ 起跳步：识别结果 + 局限说明。"""
        page = QWidget()
        vl = QVBoxLayout(page)
        takeoffs = [t for t in (gs.get('takeoff_steps') or [])
                    if isinstance(t, dict)]
        if not takeoffs:
            hint = QLabel('未识别到起跳步。')
            hint.setWordWrap(True)
            vl.addWidget(hint)
        else:
            table = _make_table(len(takeoffs),
                                ['触地帧', '侧', '触地(ms)', '中位数(ms)',
                                 '比值', '置信度', '判据说明'])
            for r, t in enumerate(takeoffs):
                vals = [
                    self._int_text(t.get('td_frame')),
                    self._side_text(t.get('side')),
                    self._fmt(t.get('contact_time_ms')),
                    self._fmt(t.get('contact_median_ms')),
                    self._fmt(t.get('ratio'), 2),
                    self._fmt(t.get('confidence'), 2),
                    str(t.get('reason') or '—'),
                ]
                for c, text in enumerate(vals):
                    table.setItem(r, c, QTableWidgetItem(text))
            table.resizeColumnsToContents()
            vl.addWidget(table, 1)
        vl.addWidget(self._small_label(
            '局限：若视频在起跳后继续拍到落垫，落垫缓冲步的触地时间'
            '也可能较长，可能被误报为起跳步；需结合该步触地时长与'
            '其前后腾空时长人工甄别。'))
        vl.addStretch(1)
        return page

    # ---------------- 格式化辅助 ----------------
    @staticmethod
    def _num(v):
        """数值清洗：None/bool/非数值 → None，否则 float。"""
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        return float(v)

    def _fmt(self, v, nd: int = 1, suffix: str = '') -> str:
        """数值 → '123.4suffix'；缺失/非数值 → '—'。"""
        n = self._num(v)
        return '—' if n is None else f'{n:.{nd}f}{suffix}'

    def _int_text(self, v) -> str:
        """整数（如帧号/计数）→ 文本；缺失 → '—'。"""
        n = self._num(v)
        return '—' if n is None else f'{n:.0f}'

    @staticmethod
    def _side_text(side) -> str:
        """侧别 → 左/右；未知 → '—'。"""
        return {'left': '左', 'right': '右'}.get(side, '—')

    def _stride_text(self, s: dict) -> str:
        """步长文本：有 stride_length_m 用米，否则像素，缺失 '—'。"""
        m = self._num(s.get('stride_length_m'))
        if m is not None:
            return f'{m:.2f} m'
        px = self._num(s.get('stride_length_px'))
        if px is not None:
            return f'{px:.1f} px'
        return '—'

    def _metric_cell_text(self, m) -> str:
        """参考对比单元格：'值 (z=+1.25)'；无 z（无 SD 文献值）只显示值。"""
        if not isinstance(m, dict):
            return '—'
        v = self._num(m.get('value'))
        if v is None:
            return '—'
        z = self._num(m.get('z'))
        if z is None:
            return f'{v:.1f}'
        return f'{v:.1f} (z={z:+.2f})'

    @staticmethod
    def _small_label(text: str) -> QLabel:
        """小字号说明标签（自动换行）。"""
        label = QLabel(str(text))
        label.setWordWrap(True)
        font = label.font()
        font.setPointSize(8)
        label.setFont(font)
        return label
