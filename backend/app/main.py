"""KineForm 本地分析服务（FastAPI）装配入口。

启动（cwd = d:\\KineForm\\backend）：

    D:\\KineForm\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

形态：单进程 + 内存任务表 + 单 worker 线程串行消费 + 202/轮询/协作取消
（契约 client/API_CONTRACT.md §4；先例 ComfyUI/Gradio/A1111）。lifespan
启动 worker + watchdog（daemon）线程，shutdown 优雅停（最多等 5s）。
"""
from __future__ import annotations

import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from .core.config import SERVICE_VERSION
from .routers import analysis, health, projects, tasks
from .routers.projects import ProjectError
from .services.runner_protocol import ValidationError
from .services.task_manager import (
    DuplicateVideoError,
    QueueFullError,
    TaskFinishedError,
    TaskManager,
    TaskNotFoundError,
)

# 未知路由等非业务 HTTP 错误的机器码（契约 §4.6 之外的框架扩展）
_HTTP_CODE_NAMES = {
    400: 'bad_request',
    401: 'unauthorized',
    403: 'forbidden',
    404: 'not_found',
    405: 'method_not_allowed',
    413: 'payload_too_large',
    422: 'validation_error',
    429: 'too_many_requests',
    500: 'internal_error',
    503: 'service_unavailable',
}


def _start_analysis_preload() -> None:
    """后台线程预载分析管线（重依赖导入+模型加载，见 analysis_runner.preload）。

    环境变量 KINEFORM_PRELOAD_ANALYSIS=0 可关闭（测试用：避免 pytest
    进程加载 torch/权重）。
    """
    if os.environ.get('KINEFORM_PRELOAD_ANALYSIS', '1') == '0':
        return

    def _run() -> None:
        # 延迟 import：保持服务装配轻量（preload 内部才触发重依赖）
        from .services.analysis_runner import preload
        state = preload()
        if state['error']:
            print(f'[preload] 分析模型预载失败: {state["error"]}', flush=True)
        else:
            print('[preload] 分析模型预载完成', flush=True)

    threading.Thread(target=_run, daemon=True,
                     name='analysis-preload').start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task_manager = TaskManager()
    task_manager.start()
    app.state.task_manager = task_manager
    _start_analysis_preload()
    yield
    task_manager.shutdown()


def _error_body(code: str, message: str) -> dict:
    return {'error': {'code': code, 'message': message}}


def _register_exception_handlers(app: FastAPI) -> None:
    """统一错误体 {"error":{"code","message"}}（契约 §4.6）。

    路由层只抛领域异常，HTTP 状态码/错误体的映射全部集中在此。
    """

    async def validation_error_handler(request: Request,
                                       exc: ValidationError):
        return JSONResponse(status_code=400,
                            content=_error_body(exc.code, exc.message))

    async def duplicate_video_handler(request: Request,
                                      exc: DuplicateVideoError):
        # 契约 §4.1：duplicate_video 附带既有任务 id（与 error 同级）
        return JSONResponse(status_code=409, content={
            'error': {'code': 'duplicate_video', 'message': exc.message},
            'task_id': exc.task_id,
        })

    async def queue_full_handler(request: Request, exc: QueueFullError):
        return JSONResponse(status_code=409,
                            content=_error_body('queue_full', exc.message))

    async def task_not_found_handler(request: Request,
                                     exc: TaskNotFoundError):
        return JSONResponse(status_code=404,
                            content=_error_body('task_not_found', exc.message))

    async def task_finished_handler(request: Request,
                                    exc: TaskFinishedError):
        return JSONResponse(status_code=409,
                            content=_error_body('task_finished', exc.message))

    async def project_error_handler(request: Request, exc: ProjectError):
        # 项目资源端点领域异常：状态码/错误码由异常自带（projects 路由抛出）
        return JSONResponse(status_code=exc.status_code,
                            content=_error_body(exc.code, exc.message))

    async def http_exception_handler(request: Request,
                                     exc: StarletteHTTPException):
        # 覆盖 FastAPI 默认 {"detail":...}（含 404 路由不存在、405 等）
        if isinstance(exc.detail, dict) and 'code' in exc.detail:
            error = {'code': str(exc.detail['code']),
                     'message': str(exc.detail.get('message', ''))}
        else:
            code = _HTTP_CODE_NAMES.get(exc.status_code,
                                        f'http_{exc.status_code}')
            message = ('接口不存在' if exc.status_code == 404
                       and exc.detail == 'Not Found' else str(exc.detail))
            error = {'code': code, 'message': message}
        return JSONResponse(status_code=exc.status_code,
                            content={'error': error})

    async def request_validation_handler(request: Request,
                                         exc: RequestValidationError):
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = '.'.join(str(x) for x in first.get('loc', [])
                           if x != 'body')
            message = f'请求体校验失败：{loc} {first.get("msg", "")}'.strip()
        else:
            message = '请求体校验失败'
        return JSONResponse(status_code=422,
                            content=_error_body('validation_error', message))

    async def unhandled_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500,
                            content=_error_body('internal_error', '服务器内部错误'))

    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(DuplicateVideoError, duplicate_video_handler)
    app.add_exception_handler(QueueFullError, queue_full_handler)
    app.add_exception_handler(TaskNotFoundError, task_not_found_handler)
    app.add_exception_handler(TaskFinishedError, task_finished_handler)
    app.add_exception_handler(ProjectError, project_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError,
                              request_validation_handler)
    app.add_exception_handler(Exception, unhandled_handler)


def create_app() -> FastAPI:
    app = FastAPI(title='KineForm Analysis API', version=SERVICE_VERSION,
                  lifespan=lifespan)
    # 本地回环服务、无 cookie 凭证（契约 §8.3）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=False,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.include_router(analysis.router)
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(health.router)
    _register_exception_handlers(app)
    return app


app = create_app()
