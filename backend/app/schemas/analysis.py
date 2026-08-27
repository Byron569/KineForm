"""POST /api/analysis/submit 请求/响应模型（契约 §4.1）。

请求模型 extra='allow'：客户端额外字段（如 annotations.json 的
createdAt/updatedAt）原样透传给执行体，满足 §6.1「markers 原样留档」。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MotionInfo(BaseModel):
    """motion 来源信息（原样留档到 submitted_markers.json，§6.1）。"""

    model_config = ConfigDict(extra='allow')

    source: str
    sha256: str | None = None


class Marker(BaseModel):
    """教练打点（契约 §4.1 markers[]）。"""

    model_config = ConfigDict(extra='allow')

    id: str
    frameIndex: int
    timestampMs: float
    label: str
    comment: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class SubmitRequest(BaseModel):
    model_config = ConfigDict(extra='allow')

    video_id: str
    fps: float
    frame_count: int
    # 缺失视同空数组 → 执行体校验 → 400 markers_empty（与真实执行体一致）
    markers: list[Marker] = Field(default_factory=list)
    motion: MotionInfo


class SubmitAcceptedResponse(BaseModel):
    status: Literal['accepted']
    task_id: str
    result_path: str


class StartAnalysisRequest(BaseModel):
    """POST /api/analysis/start 请求体（视频姿态分析）。

    video_path 刻意为宽松类型 Any：非字符串不在 pydantic 层以 422 拒绝，
    而是下沉到执行体校验 → 400 video_invalid（契约「路径非字符串」分支）；
    字段缺失仍走全局 422 validation_error。

    project_name 为可选用户命名（str | None）：仅供透传给执行体写入
    meta.json，不做其他校验——非字符串由 pydantic 以 422 兜底（全局
    validation_error）。
    """

    video_path: Any
    project_name: str | None = None


class StartAnalysisAcceptedResponse(BaseModel):
    """202 受理响应：分析项目目录名带时间戳、受理时未知 → 'projects/pending'，
    succeeded 时任务快照的 result_path 由执行体返回值覆写为真实目录名。"""

    status: Literal['accepted']
    task_id: str
    result_path: str
