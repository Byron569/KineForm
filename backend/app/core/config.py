r"""服务级配置常量（桌面单用户本地服务：无需配置文件/注册中心）。

对齐说明（重要）：本服务的项目目录根与推理管线单一事实来源保持一致——
sports_pose_analyzer/app/config/defaults.py 的
``PROJECTS_DIR = <sports_pose_analyzer 根>/projects``（已有真实分析项目
落盘于此，故本服务跟随、不迁移数据）。契约 client/API_CONTRACT.md 中的
``outputs/<video_id>/`` 为展示性前缀（result_path 字段），实际根目录以
此处为准；可用环境变量 KINEFORM_OUTPUTS_DIR 覆盖（测试/特殊部署用）。
"""
from __future__ import annotations

import os
from pathlib import Path

OUTPUTS_DIR = Path(os.environ.get(
    'KINEFORM_OUTPUTS_DIR',
    Path(__file__).resolve().parents[3] / 'sports_pose_analyzer' / 'projects'))

SERVICE_VERSION = '0.1.0'      # 契约 §4.5：客户端据此做主/次版本比对
QUEUE_CAPACITY = 1             # 契约 §4.1：排队位上限（总并发 = 1 运行 + 1 排队）
WATCHDOG_TIMEOUT_SEC = 900     # running 且无进度超过该秒数 → failed（watchdog）
MAX_FINISHED_TASKS = 50        # 终态任务内存保留条数（FIFO 淘汰，重启即清空）
