"""任务详情 / 取消 / 列表（契约 §4.2–§4.4）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_task_manager
from ..schemas.task import CancelResponse, TaskListResponse, TaskStatusResponse
from ..services.task_manager import TaskManager

router = APIRouter()


@router.get('/api/tasks/{task_id}', response_model=TaskStatusResponse)
def get_task(task_id: str,
             task_manager: TaskManager = Depends(get_task_manager)) -> dict:
    return task_manager.get(task_id)               # 未知 → 404 task_not_found


@router.post('/api/tasks/{task_id}/cancel', response_model=CancelResponse)
def cancel_task(task_id: str,
                task_manager: TaskManager = Depends(get_task_manager)) -> dict:
    status = task_manager.cancel(task_id)          # 404 / 409 由全局映射
    return {'task_id': task_id, 'status': status}


@router.get('/api/tasks', response_model=TaskListResponse)
def list_tasks(task_manager: TaskManager = Depends(get_task_manager)) -> dict:
    tasks, queue_length = task_manager.list_tasks()
    return {'tasks': tasks, 'queue_length': queue_length}
