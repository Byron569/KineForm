"""GET /api/health（契约 §4.5：Electron 探活 + 版本比对）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.config import SERVICE_VERSION
from ..dependencies import get_task_manager
from ..schemas.health import HealthResponse
from ..services.task_manager import TaskManager

router = APIRouter()


@router.get('/api/health', response_model=HealthResponse)
def health(task_manager: TaskManager = Depends(get_task_manager)) -> dict:
    """极轻量：busy 走无锁 Event，不读任务表锁也能即时应答。"""
    return {'status': 'ok',
            'service_version': SERVICE_VERSION,
            'busy': task_manager.is_busy()}
