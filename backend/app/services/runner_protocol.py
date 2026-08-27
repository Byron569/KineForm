"""执行体（runner）协议与共享异常定义。

真实实现见同包 report_runner.py（POST /api/analysis/submit 的 P0 执行体，
纯标准库、并行开发）。为保证「框架层捕获/映射」与「执行体抛出」的是同一
个异常类，这里优先复用 report_runner 已定义的 ValidationError /
TaskCancelled；report_runner 尚未落地时退化为本地定义，框架仍可独立装配
（get_runner 为请求路径上的延迟 import，见 dependencies.py）。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Protocol

try:  # report_runner 已存在 → 复用其异常类，保证 isinstance 判定一致
    from .report_runner import TaskCancelled, ValidationError
except ImportError:  # pragma: no cover —— report_runner 未落地时的兜底
    class ValidationError(Exception):
        """请求校验失败（框架层映射为 HTTP 400）。code 为契约 §4.6 机器码。"""

        def __init__(self, code: str, message: str) -> None:
            super().__init__(message)
            self.code = code
            self.message = message

    class TaskCancelled(Exception):
        """协作取消：执行体在检查点检测到 cancel_event 置位后抛出。"""


ProgressCallback = Callable[[str, int, str], None]


class RunnerProtocol(Protocol):
    """submit 执行体协议（report_runner.build_runner() 的返回类型）。"""

    def validate(self, payload: dict, outputs_dir: Path) -> None:
        """同步快速校验；失败抛 ValidationError(code, message)。"""
        ...

    def run(self, payload: dict, outputs_dir: Path,
            progress_cb: ProgressCallback,
            cancel_event: threading.Event, task_id: str) -> dict:
        """在 worker 线程内执行；取消抛 TaskCancelled；其他异常 → failed。

        返回 dict 至少含 result_path: str（如 'outputs/<video_id>/score_report.json'）。
        """
        ...
