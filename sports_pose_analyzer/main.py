"""离线运动姿态分析器 —— 图形界面入口。

用法（项目根目录下）:
    python main.py
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName('离线运动姿态分析器')
    # Fusion 风格 + 浅灰背景（不引外部资源文件）
    app.setStyle('Fusion')
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor('#F0F0F0'))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
