"""GET /api/health 响应模型（契约 §4.5）。"""
from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service_version: str
    busy: bool
