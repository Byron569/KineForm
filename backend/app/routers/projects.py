r"""项目资源端点：项目枚举 / motion / events / annotations / 视频 / 报告。

数据根与 submit 的服务端事实来源一致（OUTPUTS_DIR，见 core/config.py）：
一级子目录名即 video_id，目录内含 motion.json 才视为有效项目。

约定（与既有路由一致：路由层只抛领域异常，HTTP 映射集中在 app/main.py）：
  - video_id 防穿越（含 / \ .. : 或空）与「目录不存在或无 motion.json」
    统一 404 project_not_found，不区分，避免向客户端泄露目录结构；
  - 否则资源缺失按文件分别返回 events_not_found / annotations_not_found /
    keypoints_not_found / video_not_found / report_not_found / meta_not_found；
  - JSON 文件与视频均走 starlette FileResponse 原样字节返回（不重序列化；
    视频原生支持 Range/206 供 <video> 拖动播放，starlette 1.6.0 已验证）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from starlette.responses import FileResponse

from ..dependencies import get_outputs_dir, get_task_manager
from ..schemas.projects import (
    AnnotationsDocument,
    AnnotationsSaveResponse,
    ProjectListResponse,
)
from ..services.task_manager import TaskManager

router = APIRouter()

SOURCE_VIDEO = 'source_cfr.mp4'     # CFR 标准化源视频（契约 §2 source_video）
ANALYSIS_VIDEO = 'analysis.mp4'     # 叠加骨架的分析视频（契约 §1 数据流）


class ProjectError(Exception):
    """项目资源访问错误（HTTP 映射见 app/main.py 全局 exception_handler）。"""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# ---------- 公共校验 / IO ----------

def _require_project_dir(outputs_dir: Path, video_id: str) -> Path:
    r"""video_id 防穿越 + 项目存在性校验，通过则返回项目目录。

    - 穿越片段（/ \ .. 或 Windows 盘符冒号——'C:evil' 会拼出盘符相对
      路径逃逸 outputs_dir）与不存在的项目统一 404 project_not_found；
    - 返回的目录保证含 motion.json（项目有效的唯一判据），其余文件
      由各端点按需检查。
    """
    if (not video_id or video_id in ('.', '..') or ':' in video_id
            or '/' in video_id or '\\' in video_id or '..' in video_id):
        raise ProjectError(404, 'project_not_found',
                           f'未找到视频项目: {video_id}')
    project_dir = Path(outputs_dir) / video_id
    if not (project_dir / 'motion.json').is_file():
        raise ProjectError(404, 'project_not_found',
                           f'未找到视频项目: {video_id}')
    return project_dir


def _json_file_response(path: Path, code: str, message: str) -> FileResponse:
    """JSON 资源原样字节返回；文件缺失 → 404 指定错误码。"""
    if not path.is_file():
        raise ProjectError(404, code, message)
    return FileResponse(path, media_type='application/json')


def _video_response(project_dir: Path, filename: str,
                    video_id: str) -> FileResponse:
    """项目视频（video/mp4，FileResponse 原生 Range/206）；缺失 → 404。"""
    path = project_dir / filename
    if not path.is_file():
        raise ProjectError(404, 'video_not_found',
                           f'未找到视频文件: outputs/{video_id}/{filename}')
    return FileResponse(path, media_type='video/mp4')


def _read_json(path: Path) -> Any:
    """读取 JSON 文件；缺失或解析失败返回 None（调用方按可选文件处理）。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data: Any) -> None:
    """覆盖写盘（UTF-8、ensure_ascii=False、indent=2，同 report_runner）。"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- 端点 ----------

@router.get('/api/projects', response_model=ProjectListResponse)
def list_projects(outputs_dir: Path = Depends(get_outputs_dir)) -> dict:
    """枚举项目：OUTPUTS_DIR 一级子目录中含 motion.json 者，按 video_id 倒序。

    性能假设（桌面单用户）：项目数 < 100、单 motion.json < 20MB——对每个
    项目 json.load 全量解析（含 frames 数组）可接受，不引 ijson 等新依赖；
    损坏（非 JSON 对象）的 motion.json 直接跳过该项目。
    """
    outputs_dir = Path(outputs_dir)
    projects = []
    if outputs_dir.is_dir():
        for child in outputs_dir.iterdir():
            motion_path = child / 'motion.json'
            if not child.is_dir() or not motion_path.is_file():
                continue
            motion = _read_json(motion_path)
            if not isinstance(motion, dict):
                continue
            projects.append({
                'video_id': child.name,
                'fps': motion.get('fps'),
                'frame_count': motion.get('frame_count'),
                'width': motion.get('width'),
                'height': motion.get('height'),
                'created_at': motion.get('created_at'),
                'has_events': (child / 'events.json').is_file(),
                'has_annotations': (child / 'annotations.json').is_file(),
            })
    projects.sort(key=lambda p: p['video_id'], reverse=True)
    return {'projects': projects}


@router.get('/api/projects/{video_id}/motion')
def get_motion(video_id: str,
               outputs_dir: Path = Depends(get_outputs_dir)) -> FileResponse:
    """motion.json 原样内容（字节级返回，不重序列化；可达数 MB 走流式）。"""
    project_dir = _require_project_dir(outputs_dir, video_id)
    return FileResponse(project_dir / 'motion.json',
                        media_type='application/json')


@router.get('/api/projects/{video_id}/events')
def get_events(video_id: str,
               outputs_dir: Path = Depends(get_outputs_dir)) -> FileResponse:
    """events.json 原样内容；无 → 404 events_not_found（前端按无步态处理）。"""
    project_dir = _require_project_dir(outputs_dir, video_id)
    return _json_file_response(project_dir / 'events.json',
                               'events_not_found',
                               f'该项目无步态事件数据: {video_id}')


@router.get('/api/projects/{video_id}/annotations')
def get_annotations(video_id: str,
                    outputs_dir: Path = Depends(get_outputs_dir)
                    ) -> FileResponse:
    """annotations.json 原样内容；无 → 404 annotations_not_found（空白起步）。"""
    project_dir = _require_project_dir(outputs_dir, video_id)
    return _json_file_response(project_dir / 'annotations.json',
                               'annotations_not_found',
                               f'该项目暂无标注数据: {video_id}')


@router.get('/api/projects/{video_id}/meta')
def get_meta(video_id: str,
             outputs_dir: Path = Depends(get_outputs_dir)) -> FileResponse:
    """meta.json 原样内容（source_video_name / project_name / analyzed_at）。

    旧项目（本次改动前分析、无 meta.json）→ 404 meta_not_found，前端
    据此回退显示默认值（预期）。
    """
    project_dir = _require_project_dir(outputs_dir, video_id)
    return _json_file_response(project_dir / 'meta.json',
                               'meta_not_found',
                               f'该项目无 meta.json（旧项目）: {video_id}')


@router.put('/api/projects/{video_id}/annotations',
            response_model=AnnotationsSaveResponse)
def put_annotations(video_id: str,
                    body: AnnotationsDocument,
                    outputs_dir: Path = Depends(get_outputs_dir)) -> dict:
    """全量覆盖写 annotations.json（前端防抖后调用，服务端不做合并）。"""
    project_dir = _require_project_dir(outputs_dir, video_id)
    if body.video_id != video_id:
        raise ProjectError(
            400, 'video_id_mismatch',
            f'请求体 video_id 与路径参数不一致: {body.video_id} != {video_id}')
    _write_json(project_dir / 'annotations.json', body.model_dump())
    return {'status': 'saved',
            'path': f'outputs/{video_id}/annotations.json'}


@router.get('/api/projects/{video_id}/video')
def get_video(video_id: str,
              outputs_dir: Path = Depends(get_outputs_dir)) -> FileResponse:
    """source_cfr.mp4（CFR 标准化源视频）。"""
    project_dir = _require_project_dir(outputs_dir, video_id)
    return _video_response(project_dir, SOURCE_VIDEO, video_id)


@router.get('/api/projects/{video_id}/analysis')
def get_analysis_video(video_id: str,
                       outputs_dir: Path = Depends(get_outputs_dir)
                       ) -> FileResponse:
    """analysis.mp4（叠加骨架的分析视频），处理方式同 /video。"""
    project_dir = _require_project_dir(outputs_dir, video_id)
    return _video_response(project_dir, ANALYSIS_VIDEO, video_id)


@router.get('/api/tasks/{task_id}/result')
def get_task_result(
        task_id: str,
        task_manager: TaskManager = Depends(get_task_manager),
        outputs_dir: Path = Depends(get_outputs_dir)) -> FileResponse:
    """score_report.json 原样内容；仅任务 succeeded 且报告在盘时可读。"""
    task = task_manager.get(task_id)          # 未知 → 404 task_not_found（既有映射）
    if task['status'] != 'succeeded':
        raise ProjectError(409, 'task_not_finished',
                           f'任务尚未成功结束，当前状态: {task["status"]}')
    video_id = task['video_id']
    return _json_file_response(
        Path(outputs_dir) / video_id / 'score_report.json',
        'report_not_found',
        f'未找到分析报告: outputs/{video_id}/score_report.json')
