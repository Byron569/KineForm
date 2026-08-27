"""任务状态相关响应模型（契约 §4.2/§4.3/§4.4）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TaskStatusLiteral = Literal['queued', 'running', 'cancelling',
                            'succeeded', 'failed', 'cancelled']


class TaskStatusResponse(BaseModel):
    task_id: str
    video_id: str
    type: Literal['report', 'analyze']    # 任务类型（既有 report 为默认）
    status: TaskStatusLiteral
    stage: str | None = None
    percent: int
    detail: str | None = None
    error: str | None = None
    result_path: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class TaskListResponse(BaseModel):
    tasks: list[TaskStatusResponse]
    queue_length: int


class CancelResponse(BaseModel):
    task_id: str
    status: Literal['cancelling', 'cancelled']
