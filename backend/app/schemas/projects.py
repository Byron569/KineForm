"""项目资源端点模型（项目列表 / annotations 读写）。

列表项元数据取自 motion.json 顶层字段（契约 client/API_CONTRACT.md §2），
字段缺失时输出 null，由前端按可选处理；annotations 文档宽松校验
（允许额外字段如 fps/createdAt/updatedAt，原样落盘）。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProjectSummary(BaseModel):
    """GET /api/projects 列表项。"""

    video_id: str
    fps: float | None = None
    frame_count: int | None = None
    width: int | None = None
    height: int | None = None
    created_at: str | None = None
    has_events: bool
    has_annotations: bool


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]


class AnnotationMarker(BaseModel):
    """annotations.json markers[] 条目（宽松校验，允许额外字段）。"""

    model_config = ConfigDict(extra='allow')

    id: str
    frameIndex: int
    label: str


class AnnotationsDocument(BaseModel):
    """PUT /api/projects/{video_id}/annotations 请求体 = 全量文档。"""

    model_config = ConfigDict(extra='allow')

    schema_version: str
    video_id: str
    markers: list[AnnotationMarker]


class AnnotationsSaveResponse(BaseModel):
    status: Literal['saved']
    path: str
