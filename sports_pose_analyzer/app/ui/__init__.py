"""图形界面包（PySide6，中文界面）。

约定：本包模块顶层只 import 轻量依赖（PySide6 / 配置 / 启动器等），
torch / mmpose / cv2 等重依赖一律延迟到工作线程 run() 时导入，
保证 `python main.py` 启动与离屏自测秒开。
"""
