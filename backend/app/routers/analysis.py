"""POST /api/analysis/submit 与 POST /api/analysis/start（契约 §4.1）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from ..dependencies import (
    get_analysis_runner,
    get_outputs_dir,
    get_runner,
    get_task_manager,
)
from ..schemas.analysis import (
    StartAnalysisAcceptedResponse,
    StartAnalysisRequest,
    SubmitAcceptedResponse,
    SubmitRequest,
)
from ..services.runner_protocol import RunnerProtocol
from ..services.task_manager import TaskManager

router = APIRouter()

# 受理时分析项目目录名（带时间戳）未知 → result_path 占位（契约 start），
# succeeded 时由 TaskManager 用执行体返回值覆写为真实目录名
PENDING_RESULT_PATH = 'projects/pending'


@router.post('/api/analysis/submit', status_code=202,
             response_model=SubmitAcceptedResponse)
def submit_analysis(
    body: SubmitRequest,
    runner: RunnerProtocol = Depends(get_runner),
    outputs_dir: Path = Depends(get_outputs_dir),
    task_manager: TaskManager = Depends(get_task_manager),
) -> SubmitAcceptedResponse:
    """受理分析请求：同步校验（400）→ dedupe/容量（409）→ 入队（202）。

    异常不做 try/except：ValidationError / DuplicateVideoError /
    QueueFullError 由 app/main.py 的全局 exception_handler 统一映射为
    契约 §4.6 错误体。
    """
    payload = body.model_dump()
    runner.validate(payload, outputs_dir)          # 失败 → 400
    task_id = task_manager.submit(                 # 冲突 → 409
        body.video_id, payload, runner, outputs_dir)
    return SubmitAcceptedResponse(
        status='accepted',
        task_id=task_id,
        result_path=f'outputs/{body.video_id}/score_report.json')


@router.post('/api/analysis/start', status_code=202,
             response_model=StartAnalysisAcceptedResponse)
def start_analysis(
    body: StartAnalysisRequest,
    runner: RunnerProtocol = Depends(get_analysis_runner),
    outputs_dir: Path = Depends(get_outputs_dir),
    task_manager: TaskManager = Depends(get_task_manager),
) -> StartAnalysisAcceptedResponse:
    """受理视频姿态分析：同步校验（400）→ dedupe/容量（409）→ 入队（202）。

    与 submit 同模式：异常不做 try/except，ValidationError /
    DuplicateVideoError / QueueFullError 由全局 handler 统一映射。
    dedupe 键 = 源视频绝对路径小写规范化（Windows 路径大小写不敏感）；
    快照 video_id 同为该规范化路径（项目目录名 succeeded 后才存在，
    见 result_path 覆写）。
    """
    payload = body.model_dump()
    runner.validate(payload, outputs_dir)          # 失败 → 400
    video_key = str(Path(payload['video_path']).resolve()).lower()
    task_id = task_manager.submit(                 # 冲突 → 409
        video_key, payload, runner, outputs_dir,
        task_type='analyze', result_path=PENDING_RESULT_PATH)
    return StartAnalysisAcceptedResponse(
        status='accepted',
        task_id=task_id,
        result_path=PENDING_RESULT_PATH)
