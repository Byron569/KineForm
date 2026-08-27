"""FastAPI 依赖注入提供者（测试经 app.dependency_overrides 注入假实现）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, Request

from .core.config import OUTPUTS_DIR
from .services.runner_protocol import RunnerProtocol
from .services.task_manager import TaskManager


def get_outputs_dir() -> Path:
    """输出根目录（契约 §4.1 outputs/<video_id>/ 的父目录）。"""
    return OUTPUTS_DIR


def get_task_manager(request: Request) -> TaskManager:
    """lifespan 中创建并启动的任务表单例（挂载于 app.state）。"""
    return request.app.state.task_manager


def get_runner() -> RunnerProtocol:
    """submit 执行体。

    必须函数体内延迟 import：真实模块 app.services.report_runner 与本框架
    并行开发，仅在请求路径上触发导入，保证装配期（from app.main import app）
    不依赖该模块存在；假 runner 只存在于测试（dependency_overrides）。
    """
    from .services.report_runner import build_runner
    return build_runner()


def get_analysis_runner() -> RunnerProtocol:
    """start（视频姿态分析）执行体。

    同 get_runner 的延迟 import 模式：真实管线链路含 cv2/torch 重依赖
    （analysis_runner 内部再延迟到首次 run 才加载），装配期不触碰。
    """
    from .services.analysis_runner import build_analysis_runner
    return build_analysis_runner()
