"""主窗口：离线运动姿态分析器（PySide6 中文界面）。

设计要点：
- 模块顶层只 import 轻量依赖（PySide6 / 配置 / 启动器），
  torch/mmpose/cv2 一律延迟到工作线程 run() 内导入，保证启动秒开；
- 视频探测与分析均在 QThread 中执行，UI 线程永不阻塞；
- 取消分析通过 threading.Event 传递给分析管线。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QTextEdit,
                               QVBoxLayout, QWidget)

from ..common.data_models import AnalysisResult, VideoInfo
from ..config.defaults import DEFAULT_MODEL_KEY, MODEL_REGISTRY, PROJECTS_DIR
from ..config.settings import (UserSettings, find_tracker, load_settings,
                               save_settings)
from ..external_player.launcher import (launch_player, open_in_explorer,
                                        validate_player_exe)
from .dialogs import (GaitDetailDialog, ResultDetailDialog, VideoInfoDialog,
                      angle_label, confirm_missing_checkpoint, format_duration,
                      vfr_text)


class ProbeWorker(QThread):
    """视频探测线程：调用 probe_video（子进程/解码较慢），避免阻塞 UI。"""

    probed = Signal(object)   # 携带 VideoInfo
    failed = Signal(str)

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self._video_path = video_path

    def run(self):
        try:
            # 延迟导入：ffmpeg_tools 顶层 import cv2，较重
            from ..video.ffmpeg_tools import probe_video
            info = probe_video(self._video_path)
        except Exception as e:
            self.failed.emit(str(e) or type(e).__name__)
            return
        self.probed.emit(info)


class AnalysisWorker(QThread):
    """分析线程：封装 AnalysisPipeline.run，信号回传进度与结果。"""

    progress = Signal(str, int, str)   # (阶段, 百分比, 明细)
    finished_ok = Signal(object)       # 携带 AnalysisResult
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, settings: UserSettings, video_path: str, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._video_path = video_path
        self._cancel_event = threading.Event()

    def request_cancel(self):
        """请求取消：置位事件，由管线在帧/阶段边界响应。"""
        self._cancel_event.set()

    def run(self):
        # 延迟导入：orchestrator 依赖 cv2/numpy 等较重模块
        from ..pipeline.errors import PipelineCancelled
        from ..pipeline.orchestrator import AnalysisPipeline
        try:
            pipeline = AnalysisPipeline(self._settings)
            result = pipeline.run(
                self._video_path,
                progress_cb=lambda stage, pct, detail:
                    self.progress.emit(stage, pct, detail),
                cancel_event=self._cancel_event)
        except PipelineCancelled:
            self.cancelled.emit()
            return
        except Exception as e:
            self.failed.emit(str(e) or type(e).__name__)
            return
        self.finished_ok.emit(result)


class MainWindow(QMainWindow):
    """主窗口：分析设置 → 视频信息 → 进度 → 结果。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle('离线运动姿态分析器')
        self.setMinimumSize(900, 640)

        self._settings = load_settings()
        self._video_path: Optional[Path] = None
        self._video_info: Optional[VideoInfo] = None
        self._result: Optional[AnalysisResult] = None
        self._probe_worker: Optional[ProbeWorker] = None
        self._worker: Optional[AnalysisWorker] = None
        self._closing = False   # 关闭窗口过程中：忽略线程残余回调

        self._build_ui()
        self._restore_settings()
        self._set_analyzing(False)
        self.statusBar().showMessage('就绪')

    # ---------------- 界面构建 ----------------
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        self.settings_group = self._build_settings_group()
        root.addWidget(self.settings_group)
        root.addWidget(self._build_video_info_group())
        root.addWidget(self._build_progress_group())
        self.result_group = self._build_result_group()
        root.addWidget(self.result_group)
        self.setCentralWidget(central)

    def _build_settings_group(self) -> QGroupBox:
        box = QGroupBox('分析设置')
        layout = QVBoxLayout(box)

        # 视频选择行
        video_row = QHBoxLayout()
        self.btn_choose_video = QPushButton('选择视频…')
        self.btn_choose_video.clicked.connect(self._choose_video)
        self.video_path_label = QLabel('未选择视频')
        video_row.addWidget(self.btn_choose_video)
        video_row.addWidget(self.video_path_label, 1)
        layout.addLayout(video_row)

        # 模型 / FP16 / 渲染叠加选项行
        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel('模型'))
        self.model_combo = QComboBox()
        for key, spec in MODEL_REGISTRY.items():
            self.model_combo.addItem(spec.display_name, key)
        opt_row.addWidget(self.model_combo, 2)
        self.fp16_check = QCheckBox('FP16')
        self.fp16_check.setChecked(True)
        opt_row.addWidget(self.fp16_check)
        opt_row.addSpacing(16)
        self.angle_check = QCheckBox('角度')
        self.trajectory_check = QCheckBox('轨迹')
        self.event_label_check = QCheckBox('事件标签')
        for check in (self.angle_check, self.trajectory_check,
                      self.event_label_check):
            check.setChecked(True)
            opt_row.addWidget(check)
        opt_row.addStretch(1)
        layout.addLayout(opt_row)

        # Tracker 路径行
        tracker_row = QHBoxLayout()
        tracker_row.addWidget(QLabel('Tracker'))
        self.tracker_edit = QLineEdit()
        self.tracker_edit.setReadOnly(True)
        self.tracker_edit.setPlaceholderText('未配置（点击「检测」自动查找）')
        tracker_row.addWidget(self.tracker_edit, 1)
        self.btn_browse_tracker = QPushButton('浏览…')
        self.btn_browse_tracker.clicked.connect(self._browse_tracker)
        self.btn_detect_tracker = QPushButton('检测')
        self.btn_detect_tracker.clicked.connect(self._detect_tracker)
        self.tracker_status_label = QLabel('未配置')
        self.tracker_status_label.setStyleSheet('color: red;')
        tracker_row.addWidget(self.btn_browse_tracker)
        tracker_row.addWidget(self.btn_detect_tracker)
        tracker_row.addWidget(self.tracker_status_label)
        layout.addLayout(tracker_row)
        return box

    def _build_video_info_group(self) -> QGroupBox:
        box = QGroupBox('视频信息')
        layout = QHBoxLayout(box)
        form = QFormLayout()
        self.info_name_value = QLabel('—')
        self.info_duration_value = QLabel('—')
        self.info_fps_value = QLabel('—')
        self.info_frames_value = QLabel('—')
        self.info_size_value = QLabel('—')
        self.info_vfr_value = QLabel('—')
        form.addRow('文件名', self.info_name_value)
        form.addRow('时长', self.info_duration_value)
        form.addRow('帧率', self.info_fps_value)
        form.addRow('总帧数', self.info_frames_value)
        form.addRow('宽高', self.info_size_value)
        form.addRow('是否可变帧率', self.info_vfr_value)
        layout.addLayout(form, 1)
        self.btn_video_detail = QPushButton('详情…')
        self.btn_video_detail.setEnabled(False)
        self.btn_video_detail.clicked.connect(self._show_video_info_dialog)
        layout.addWidget(self.btn_video_detail, 0,
                         Qt.AlignmentFlag.AlignTop)
        return box

    def _build_progress_group(self) -> QGroupBox:
        box = QGroupBox('进度')
        layout = QVBoxLayout(box)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        row = QHBoxLayout()
        self.stage_label = QLabel('阶段：—')
        self.detail_label = QLabel('')
        row.addWidget(self.stage_label)
        row.addWidget(self.detail_label, 1)
        layout.addLayout(row)
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton('开始分析')
        self.btn_start.clicked.connect(self._start_analysis)
        self.btn_cancel = QPushButton('取消')
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_analysis)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        return box

    def _build_result_group(self) -> QGroupBox:
        box = QGroupBox('结果')
        box.setEnabled(False)   # 分析完成后启用
        layout = QVBoxLayout(box)

        # 概览表
        self.summary_table = QTableWidget(0, 2)
        self.summary_table.setHorizontalHeaderLabels(['指标', '数值'])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.summary_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.summary_table.horizontalHeader().setStretchLastSection(True)
        self.summary_table.setMaximumHeight(190)
        layout.addWidget(self.summary_table)

        # 警告列表
        self.warnings_edit = QTextEdit()
        self.warnings_edit.setReadOnly(True)
        self.warnings_edit.setPlaceholderText('无警告')
        self.warnings_edit.setMaximumHeight(64)
        layout.addWidget(self.warnings_edit)

        # 按钮行 1：本地打开
        row1 = QHBoxLayout()
        self.btn_open_analysis = QPushButton('打开分析视频')
        self.btn_open_analysis.clicked.connect(self._open_analysis_video)
        self.btn_open_skeleton = QPushButton('打开纯骨架视频')
        self.btn_open_skeleton.clicked.connect(self._open_skeleton_video)
        self.btn_open_project = QPushButton('打开项目目录')
        self.btn_open_project.clicked.connect(self._open_project_dir)
        self.btn_open_report = QPushButton('打开 HTML 报告')
        self.btn_open_report.clicked.connect(self._open_html_report)
        self.btn_result_detail = QPushButton('详情…')
        self.btn_result_detail.clicked.connect(self._show_result_dialog)
        self.btn_gait_detail = QPushButton('步态详情…')
        self.btn_gait_detail.clicked.connect(self._show_gait_dialog)
        for btn in (self.btn_open_analysis, self.btn_open_skeleton,
                    self.btn_open_project, self.btn_open_report,
                    self.btn_result_detail, self.btn_gait_detail):
            row1.addWidget(btn)
        row1.addStretch(1)
        layout.addLayout(row1)

        # 按钮行 2：Tracker
        row2 = QHBoxLayout()
        self.btn_tracker_source = QPushButton('在 Tracker 打开原视频')
        self.btn_tracker_source.clicked.connect(self._open_source_in_tracker)
        self.btn_tracker_analysis = QPushButton('在 Tracker 打开分析视频')
        self.btn_tracker_analysis.clicked.connect(
            self._open_analysis_in_tracker)
        row2.addWidget(self.btn_tracker_source)
        row2.addWidget(self.btn_tracker_analysis)
        row2.addStretch(1)
        layout.addLayout(row2)
        return box

    def _restore_settings(self):
        """把持久化设置恢复到界面控件。"""
        index = self.model_combo.findData(self._settings.model_key)
        if index < 0:
            index = self.model_combo.findData(DEFAULT_MODEL_KEY)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)
        self.fp16_check.setChecked(bool(self._settings.fp16))
        overlay = self._settings.overlay
        self.angle_check.setChecked(bool(overlay.draw_angles))
        self.trajectory_check.setChecked(bool(overlay.draw_trajectory))
        self.event_label_check.setChecked(bool(overlay.draw_event_labels))
        self.tracker_edit.setText(self._settings.tracker_path)
        self._set_tracker_status(validate_player_exe(self._settings.tracker_path))

    # ---------------- 视频选择与探测 ----------------
    def _choose_video(self):
        start_dir = self._settings.last_video_dir or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, '选择视频', start_dir,
            '视频文件 (*.mp4 *.avi *.mov *.mkv *.webm *.m4v *.wmv);;'
            '所有文件 (*)')
        if not path:
            return
        self._video_path = Path(path)
        self._settings.last_video_dir = str(self._video_path.parent)
        self._update_video_path_label()
        self.statusBar().showMessage(f'已选择视频: {path}')
        self._probe_video(path)

    def _update_video_path_label(self):
        """视频路径过长时中段省略号显示，完整路径放气泡提示。"""
        if self._video_path is None:
            self.video_path_label.setText('未选择视频')
            self.video_path_label.setToolTip('')
            return
        text = str(self._video_path)
        metrics = self.video_path_label.fontMetrics()
        elided = metrics.elidedText(
            text, Qt.TextElideMode.ElideMiddle,
            max(self.video_path_label.width(), 80))
        self.video_path_label.setText(elided)
        self.video_path_label.setToolTip(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_video_path_label()

    def _probe_video(self, path: str):
        """后台线程探测视频信息，避免 ffprobe/解码阻塞 UI。"""
        self._clear_video_info()
        # 旧探测若仍在运行：断开其信号，交给 deleteLater 自行收尾
        old = self._probe_worker
        if old is not None:
            for sig in (old.probed, old.failed, old.finished):
                try:
                    sig.disconnect()
                except RuntimeError:
                    pass
            old.finished.connect(old.deleteLater)
        self.statusBar().showMessage('正在探测视频信息…')
        worker = ProbeWorker(path)
        self._probe_worker = worker
        worker.probed.connect(self._on_probed)
        worker.failed.connect(self._on_probe_failed)
        worker.finished.connect(self._on_probe_thread_finished)
        worker.start()

    def _clear_video_info(self):
        self._video_info = None
        self.btn_video_detail.setEnabled(False)
        for label in (self.info_name_value, self.info_duration_value,
                      self.info_fps_value, self.info_frames_value,
                      self.info_size_value, self.info_vfr_value):
            label.setText('—')
        if self._video_path is not None:
            self.info_name_value.setText(self._video_path.name)

    def _on_probed(self, info: VideoInfo):
        if self.sender() is not self._probe_worker:
            return   # 过期的探测结果，忽略
        self._video_info = info
        self.info_name_value.setText(Path(info.path).name)
        self.info_duration_value.setText(format_duration(info.duration_s))
        self.info_fps_value.setText(f'{info.fps:.3f} fps')
        self.info_frames_value.setText(str(info.frame_count))
        self.info_size_value.setText(f'{info.width} × {info.height}')
        self.info_vfr_value.setText(vfr_text(info.vfr))
        self.btn_video_detail.setEnabled(True)
        self.statusBar().showMessage('视频探测完成')

    def _on_probe_failed(self, message: str):
        if self.sender() is not self._probe_worker:
            return
        self.statusBar().showMessage('视频探测失败')
        QMessageBox.warning(self, '视频探测失败', message)

    def _on_probe_thread_finished(self):
        if self.sender() is self._probe_worker:
            self._probe_worker = None

    def _show_video_info_dialog(self):
        if self._video_info is not None:
            VideoInfoDialog(self, self._video_info).exec()

    # ---------------- Tracker 设置 ----------------
    def _browse_tracker(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 Tracker 可执行文件', '',
            '可执行文件 (*.exe);;所有文件 (*)')
        if path:
            self._set_tracker_path(path)

    def _detect_tracker(self):
        found = find_tracker(self._settings)
        if found:
            self._set_tracker_path(found)
            self.statusBar().showMessage(f'已找到 Tracker: {found}')
        else:
            self._set_tracker_status(False)
            self.statusBar().showMessage('未找到 Tracker，请手动指定路径')

    def _set_tracker_path(self, path: str):
        self.tracker_edit.setText(path)
        self._settings.tracker_path = path
        self._set_tracker_status(validate_player_exe(path))

    def _set_tracker_status(self, ok: bool):
        """更新 Tracker 状态标签：绿色「已就绪」/ 红色「未配置」。"""
        if ok:
            self.tracker_status_label.setText('已就绪')
            self.tracker_status_label.setStyleSheet('color: green;')
            self.tracker_edit.setStyleSheet('')
        else:
            self.tracker_status_label.setText('未配置')
            self.tracker_status_label.setStyleSheet('color: red;')

    def _highlight_tracker_row(self):
        """红色高亮 Tracker 路径输入框，提醒用户先完成配置。"""
        self.tracker_edit.setStyleSheet(
            'QLineEdit { border: 2px solid red; background: #FFF4F4; }')
        self.tracker_edit.setFocus()

    def _tracker_exe(self) -> Optional[str]:
        """当前可用的 Tracker 路径：输入框优先，其次设置与常见安装位置。"""
        current = self.tracker_edit.text().strip()
        if current and validate_player_exe(current):
            return current
        return find_tracker(self._settings)

    # ---------------- 分析流程 ----------------
    def _sync_settings_from_ui(self):
        """把界面选项写回设置对象（模型/FP16/渲染叠加/Tracker 路径）。"""
        key = self.model_combo.currentData()
        if key in MODEL_REGISTRY:
            self._settings.model_key = key
        self._settings.fp16 = self.fp16_check.isChecked()
        overlay = self._settings.overlay
        overlay.draw_angles = self.angle_check.isChecked()
        overlay.draw_trajectory = self.trajectory_check.isChecked()
        overlay.draw_event_labels = self.event_label_check.isChecked()
        self._settings.tracker_path = self.tracker_edit.text().strip()

    def _start_analysis(self):
        # 校验 1：视频已选且存在
        if self._video_path is None:
            QMessageBox.warning(self, '未选择视频',
                                '请先点击「选择视频…」选择要分析的视频。')
            return
        if not self._video_path.exists():
            QMessageBox.warning(self, '视频不存在',
                                f'视频文件不存在:\n{self._video_path}')
            return
        # 同步界面选项到设置对象
        self._sync_settings_from_ui()
        # 校验 2：模型权重（缺失时确认是否联网自动下载，管线内部会下载）
        spec = MODEL_REGISTRY.get(self._settings.model_key)
        if spec is None:
            QMessageBox.warning(self, '模型无效', '所选模型无效，请重新选择。')
            return
        if not spec.checkpoint_path.exists():
            if not confirm_missing_checkpoint(self, spec.display_name):
                return
        # 输出目录固定为 <项目根>/projects（UserSettings 默认值）
        self._settings.projects_root = str(PROJECTS_DIR)

        # 重置进度与结果区，启动分析线程
        self._result = None
        self.result_group.setEnabled(False)
        self.progress_bar.setValue(0)
        self.stage_label.setText('阶段：—')
        self.detail_label.setText('')
        self._worker = AnalysisWorker(self._settings, str(self._video_path))
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_analysis_ok)
        self._worker.failed.connect(self._on_analysis_failed)
        self._worker.cancelled.connect(self._on_analysis_cancelled)
        self._worker.finished.connect(self._on_worker_thread_finished)
        self._worker.start()
        self._set_analyzing(True)
        self.statusBar().showMessage('分析进行中…')

    def _set_analyzing(self, analyzing: bool):
        """分析中：禁用设置区与开始按钮、启用取消；结束时恢复。"""
        self.settings_group.setEnabled(not analyzing)
        self.btn_start.setEnabled(not analyzing)
        self.btn_cancel.setEnabled(analyzing)

    def _cancel_analysis(self):
        if self._worker is None:
            return
        self._worker.request_cancel()
        self.btn_cancel.setEnabled(False)
        self.statusBar().showMessage('正在取消，等待当前步骤结束…')

    def _on_progress(self, stage: str, pct: int, detail: str):
        self.progress_bar.setValue(int(pct))
        self.stage_label.setText(f'阶段：{stage}')
        self.detail_label.setText(detail)
        self.statusBar().showMessage(f'{stage} {pct}% {detail}'.strip())

    def _on_analysis_ok(self, result: AnalysisResult):
        if self._closing:
            return
        self._result = result
        self._fill_result(result)
        self.result_group.setEnabled(True)
        self._set_analyzing(False)
        self.progress_bar.setValue(100)
        self.stage_label.setText('阶段：完成')
        self.detail_label.setText(str(result.project_dir))
        # 保存设置：记住 last_video_dir / tracker_path 等
        try:
            save_settings(self._settings)
            self.statusBar().showMessage(f'分析完成: {result.project_dir.name}')
        except OSError as e:
            self.statusBar().showMessage(f'分析完成，但设置保存失败: {e}')
        QMessageBox.information(
            self, '分析完成', f'分析完成！\n结果目录:\n{result.project_dir}')

    def _on_analysis_failed(self, message: str):
        if self._closing:
            return
        self._set_analyzing(False)
        self.stage_label.setText('阶段：失败')
        self.statusBar().showMessage('分析失败')
        QMessageBox.critical(self, '分析失败', message)

    def _on_analysis_cancelled(self):
        if self._closing:
            return
        self._set_analyzing(False)
        self.stage_label.setText('阶段：已取消')
        self.statusBar().showMessage('已取消')
        QMessageBox.information(self, '已取消', '分析已取消。')

    def _on_worker_thread_finished(self):
        if self.sender() is self._worker:
            self._worker = None

    # ---------------- 结果展示 ----------------
    def _fill_result(self, result: AnalysisResult):
        """把 AnalysisSummary / manifest 填入概览表与警告列表。"""
        s = result.summary
        rows = [
            ('总帧数', str(s.total_frames)),
            ('有效帧比例',
             f'{s.valid_ratio * 100:.1f}%'
             f'（{s.valid_frames}/{s.total_frames} 帧）'),
            ('平均姿态质量', f'{s.avg_pose_quality * 100:.1f}%'),
            ('推理耗时', f'{result.manifest.inference_ms_per_frame:.1f} ms/帧'),
        ]
        for key in ('left_knee', 'right_knee', 'left_hip', 'right_hip',
                    'torso_lean'):
            stat = s.angle_stats.get(key)
            value = (f"{stat['min']:.1f}° ~ {stat['max']:.1f}°"
                     f"（均值 {stat['mean']:.1f}°）" if stat else '—')
            rows.append((f'{angle_label(key)} min/max', value))
        rows.append(('事件数', str(len(s.events))))
        self.summary_table.setRowCount(len(rows))
        for r, (name, value) in enumerate(rows):
            self.summary_table.setItem(r, 0, QTableWidgetItem(name))
            self.summary_table.setItem(r, 1, QTableWidgetItem(value))
        self.summary_table.resizeColumnToContents(0)
        self.warnings_edit.setPlainText(
            '\n'.join(f'• {w}' for w in s.warnings) if s.warnings else '无警告')

    def _show_result_dialog(self):
        if self._result is not None:
            ResultDetailDialog(self, self._result).exec()

    def _show_gait_dialog(self):
        if self._result is not None and self._result.gait_summary:
            GaitDetailDialog(self, self._result.gait_summary).exec()

    def _open_path(self, path, title: str):
        """用系统默认程序打开文件/目录（视频→默认播放器，HTML→默认浏览器）。"""
        path = Path(path)
        if not path.exists():
            QMessageBox.warning(self, title, f'文件或目录不存在:\n{path}')
            return
        try:
            open_in_explorer(path)
            self.statusBar().showMessage(f'已打开: {path}')
        except OSError as e:
            QMessageBox.warning(self, title, f'打开失败: {e}')

    def _open_analysis_video(self):
        if self._result is not None:
            self._open_path(self._result.paths['analysis'], '打开分析视频')

    def _open_skeleton_video(self):
        if self._result is not None:
            self._open_path(self._result.paths['analysis_skeleton'],
                            '打开纯骨架视频')

    def _open_project_dir(self):
        if self._result is not None:
            self._open_path(self._result.project_dir, '打开项目目录')

    def _open_html_report(self):
        if self._result is not None:
            self._open_path(self._result.paths['report'], '打开 HTML 报告')

    def _open_in_tracker(self, video_path):
        exe = self._tracker_exe()
        if exe is None:
            QMessageBox.warning(
                self, 'Tracker 未配置',
                'Tracker 尚未配置：请点击「检测」自动查找，'
                '或点击「浏览…」手动选择 Tracker.exe。')
            self._highlight_tracker_row()
            return
        ok, err = launch_player(exe, video_path)
        if ok:
            self.statusBar().showMessage(f'已在 Tracker 打开: {video_path}')
        else:
            QMessageBox.warning(self, 'Tracker 启动失败', err)

    def _open_source_in_tracker(self):
        if self._video_path is None:
            QMessageBox.warning(self, '未选择视频', '请先选择视频。')
            return
        self._open_in_tracker(self._video_path)

    def _open_analysis_in_tracker(self):
        if self._result is not None:
            self._open_in_tracker(self._result.paths['analysis'])

    # ---------------- 关闭 ----------------
    def closeEvent(self, event):
        # 探测线程收尾（本地文件探测通常瞬间完成）
        if self._probe_worker is not None and self._probe_worker.isRunning():
            self._probe_worker.wait()
        self._probe_worker = None

        # 分析进行中：确认后取消并等待线程退出
        if self._worker is not None and self._worker.isRunning():
            answer = QMessageBox.question(
                self, '分析进行中',
                '分析正在进行，关闭窗口将取消当前分析。\n是否仍要关闭？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._closing = True
            self._worker.request_cancel()
            self._worker.wait()   # 管线在帧/阶段边界响应取消，通常很快返回
        self._worker = None
        event.accept()
