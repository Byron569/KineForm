"""外部视频分析播放器（Tracker）启动器：路径校验、带视频启动、资源管理器打开。

仅使用标准库，模块顶层不 import torch/mmpose/cv2。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def validate_player_exe(path: str | Path) -> bool:
    """校验外部播放器可执行文件路径：文件存在且扩展名为 .exe。"""
    p = Path(path)
    return p.is_file() and p.suffix.lower() == '.exe'


def launch_player(exe_path: str | Path,
                  video_path: str | Path) -> tuple[bool, str]:
    """启动外部播放器（Tracker）并打开指定视频。

    返回 (是否成功, 错误信息)：成功时错误信息为空串，
    失败时给出中文错误信息（路径无效 / 未找到可执行文件 / 系统错误）。
    """
    exe, video = Path(exe_path), Path(video_path)
    if not validate_player_exe(exe):
        return False, f'Tracker 路径无效或不是 .exe 文件: {exe}'
    if not video.is_file():
        return False, f'视频文件不存在: {video}'
    try:
        # 不等待退出：Tracker 作为独立外部程序运行
        subprocess.Popen([str(exe), str(video)])
    except FileNotFoundError:
        return False, f'未找到 Tracker 可执行文件: {exe}'
    except OSError as e:
        return False, f'启动 Tracker 失败: {e}'
    return True, ''


def open_in_explorer(path: str | Path) -> None:
    """用系统资源管理器打开文件或所在目录（Windows 用 os.startfile）。"""
    p = Path(path)
    if sys.platform == 'win32':
        os.startfile(str(p))   # noqa: S606 文件/目录均可用资源管理器打开
    else:
        # 非 Windows 兜底（本项目主要面向 Windows）
        subprocess.Popen(['xdg-open', str(p)])
