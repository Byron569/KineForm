"""POST /api/analysis/start 的执行体（视频姿态分析管线适配层）。

把 sports_pose_analyzer 的 AnalysisPipeline 适配为 RunnerProtocol
（接口与 report_runner 同构）：

  runner = build_analysis_runner()
  runner.validate(payload, outputs_dir)   # video_path 存在+扩展名 → 400
  runner.run(payload, outputs_dir, progress_cb, cancel_event, task_id)
                                          # worker 线程内调用管线并包装结果

导入隔离（两件事，都为必须）：
  1) 延迟导入——管线链路依赖 cv2/numpy，模型加载再进 torch/mmpose
     （首导+首载可达数十秒），validate 与服务装配期一律不触发；
  2) 别名装载——sports_pose_analyzer 的顶层包也叫 app，与 backend 自身
     的 app 同名；backend 启动后 ``app`` 已驻留 sys.modules，常规
     sys.path 注入 + ``from app...`` 会解析到 backend/app（无 pipeline
     子包）直接 ImportError。故用 importlib 按 file location 把
     <repo>/sports_pose_analyzer/app 装载为别名 spa_app（其内部全部为
     相对导入，别名下照常工作）。

模型复用：AnalysisPipeline 把检测/姿态模型缓存在实例字段上
（_ensure_models 惰性加载、仅首次加载），故 runner 持单例 pipeline——
重复分析不重载模型。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from .runner_protocol import TaskCancelled, ValidationError

# sports_pose_analyzer 仓库根：backend/app/services/analysis_runner.py
# 上溯三级到仓库根 d:\KineForm，再进 sports_pose_analyzer
SPA_ROOT = Path(__file__).resolve().parents[3] / 'sports_pose_analyzer'
# 顶层包装载别名（避开与 backend 顶层包 app 的 sys.modules 同名冲突）
_SPA_ALIAS = 'spa_app'
# 契约（start）：允许的视频扩展名白名单
VIDEO_EXTENSIONS = frozenset({'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'})

_alias_lock = threading.Lock()
_alias_loaded = False
_runner: Optional['AnalysisRunner'] = None    # 默认路径单例（pipeline 复用）


# ---------- sports_pose_analyzer 装载 ----------

def _ensure_spa_package() -> None:
    """把 SPA_ROOT/app 以别名 _SPA_ALIAS 装入 sys.modules（幂等、线程安全）。"""
    global _alias_loaded
    if _alias_loaded:
        return
    with _alias_lock:
        if _alias_loaded:
            return
        if _SPA_ALIAS not in sys.modules:
            init_py = SPA_ROOT / 'app' / '__init__.py'
            if not init_py.is_file():
                raise RuntimeError(f'未找到分析管线包: {init_py.parent}')
            spec = importlib.util.spec_from_file_location(
                _SPA_ALIAS, str(init_py),
                submodule_search_locations=[str(init_py.parent)])
            module = importlib.util.module_from_spec(spec)
            sys.modules[_SPA_ALIAS] = module
            spec.loader.exec_module(module)
        _alias_loaded = True


def _build_real_pipeline() -> Any:
    """构造真实 AnalysisPipeline（首次调用才触发管线依赖导入与设置加载）。"""
    _ensure_spa_package()
    from spa_app.config.settings import load_settings
    from spa_app.pipeline.orchestrator import AnalysisPipeline

    settings = load_settings()            # user_settings.json（device/身高等）
    _apply_device_fallback(settings)
    return AnalysisPipeline(settings)


def _apply_device_fallback(settings: Any) -> None:
    """settings.device 指向 cuda 但无可用 GPU 时回退 cpu。

    load_settings() 无此回退（默认值与磁盘 user_settings.json 均为
    cuda:0），在此统一兜底，避免无 GPU 机器首次推理即失败。
    """
    if str(getattr(settings, 'device', '')).lower().startswith('cuda'):
        import torch
        if not torch.cuda.is_available():
            settings.device = 'cpu'


# ---------- 执行体 ----------

def build_analysis_runner(
        pipeline_factory: Optional[Callable[[], Any]] = None) -> 'AnalysisRunner':
    """工厂入口，供框架层获取执行体；默认路径模块级缓存单例。

    pipeline_factory 供测试注入假管线（不触发 cv2/torch 导入）；
    默认 None 时走真实管线，且每次返回同一 runner 实例（其内 pipeline
    单例 → 模型跨任务复用）。
    """
    global _runner
    if pipeline_factory is not None:
        return AnalysisRunner(pipeline_factory)
    if _runner is None:
        _runner = AnalysisRunner()
    return _runner


class AnalysisRunner:
    """start 执行体：validate 同步快速校验；run 内调用分析管线。"""

    def __init__(self, pipeline_factory: Optional[Callable[[], Any]] = None):
        self._pipeline_factory = pipeline_factory
        self._pipeline: Any = None   # 单例；TaskManager 单 worker 串行调用
        self._pipeline_lock = threading.Lock()  # preload 线程与 worker 线程竞争构建

    def validate(self, payload: dict, outputs_dir: Path) -> None:
        """同步快速校验；失败抛 ValidationError。

        video_not_found — 文件不存在；video_invalid — 路径非字符串/为空，
        或扩展名不在白名单（mp4/mov/avi/mkv/webm/m4v）。
        """
        video_path = (payload or {}).get('video_path')
        if not isinstance(video_path, str) or not video_path:
            raise ValidationError('video_invalid',
                                  'video_path 必须为非空字符串')
        path = Path(video_path)
        if not path.is_file():
            raise ValidationError('video_not_found',
                                  f'视频文件不存在: {video_path}')
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValidationError(
                'video_invalid',
                f'不支持的视频格式: {path.suffix or "(无扩展名)"}')

    def run(self, payload: dict, outputs_dir: Path,
            progress_cb: Optional[Callable[[str, int, str], None]] = None,
            cancel_event: Any = None, task_id: str = '') -> dict:
        """在 worker 线程内执行：校验(0) → 管线分析 → 包装返回值。

        返回 {"result_path": "projects/<目录名>", "project_dir": 绝对路径,
        "video_id": 目录名}——result_path 由 TaskManager 在 succeeded 时
        覆写任务快照（受理时的 'projects/pending' 占位）。
        """
        payload = payload or {}
        # 阶段 1：防御性重新校验（与 report_runner 同模式）
        _raise_if_cancelled(cancel_event)
        _notify(progress_cb, 'validate', 0, '校验视频路径')
        self.validate(payload, outputs_dir)
        video_path = payload['video_path']

        # 阶段 2：分析管线（progress_cb / cancel_event 原样透传）。
        # 持锁执行：与启动预载线程（ensure_models）完全串行，避免二者
        # 并发触发 _ensure_models 双重加载模型（TaskManager 单 worker，
        # run 之间本就无并发，锁的唯一竞争者是一次性的 preload）。
        try:
            with self._pipeline_lock:
                pipeline = self._pipeline_locked()
                result = pipeline.run(
                    video_path, progress_cb=progress_cb,
                    cancel_event=cancel_event)
        except TaskCancelled:
            raise
        except Exception as exc:
            # 管线的 PipelineCancelled 与框架 TaskCancelled 分属两个包、
            # 前者导入耦合重依赖 → 按类名识别映射（真实管线与测试 fake 通用）
            if exc.__class__.__name__ == 'PipelineCancelled':
                raise TaskCancelled(str(exc) or '分析已取消') from exc
            raise

        # 阶段 3：写 meta.json（记录原始文件名/用户命名/分析时间），
        # 再包装返回值（AnalysisResult.project_dir 由管线保证为绝对路径）
        project_dir = Path(result.project_dir)
        _write_project_meta(project_dir, payload, video_path)
        return {
            'result_path': f'projects/{project_dir.name}',
            'project_dir': str(project_dir.resolve()),
            'video_id': project_dir.name,
        }

    def _pipeline_locked(self) -> Any:
        """取管线单例（调用方须已持有 _pipeline_lock）。"""
        if self._pipeline is None:
            self._pipeline = (self._pipeline_factory()
                              if self._pipeline_factory is not None
                              else _build_real_pipeline())
        return self._pipeline

    def ensure_models(self) -> None:
        """提前触发模型加载（供服务启动预载；_ensure_models 为管线惰性加载入口）。"""
        with self._pipeline_lock:
            self._pipeline_locked()._ensure_models()


# ---------- 启动预载 ----------

_preload_state = {'done': False, 'error': None}


def preload() -> dict:
    """服务启动后台线程调用：提前完成重依赖导入 + 模型加载。

    背景：torch/mmpose 首次导入（可达 30-90s）发生在 worker 线程时会
    长时间挤压 GIL/磁盘 I/O，实测期间 uvicorn 事件循环响应迟滞
    （/api/tasks 轮询 >10s 无响应）。把成本移到服务启动期，用户首次
    提交分析时模型已就绪。失败不抛出（记录后由真实任务再暴露错误）。
    """
    try:
        build_analysis_runner().ensure_models()
        _preload_state.update(done=True, error=None)
    except Exception as exc:  # noqa: BLE001 — 预载失败不阻断服务启动
        _preload_state.update(done=False, error=str(exc))
    return dict(_preload_state)


def preload_state() -> dict:
    """预载状态查询（调试用）。"""
    return dict(_preload_state)


# ---------- 工具（与 report_runner 同约定的私有副本） ----------

def _write_project_meta(project_dir: Path, payload: dict,
                        video_path: str) -> None:
    """分析成功后写/覆写 <project_dir>/meta.json（UTF-8、indent=2、ensure_ascii=False）。

    记录：source_video_name（用户导入的原始文件名，必得）、
    project_name（用户命名，可选——未提供或为空串时省略该键）、
    analyzed_at（本地 ISO-8601）。已有 meta.json 与否均覆盖更新
    （source_video_name 始终以本次分析为准）。
    """
    meta = {
        'source_video_name': Path(video_path).name,
        'analyzed_at': datetime.now().isoformat(timespec='seconds'),
    }
    project_name = payload.get('project_name')
    if project_name:               # 仅非空字符串才写该项目名键
        meta['project_name'] = project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    with open(project_dir / 'meta.json', 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _raise_if_cancelled(cancel_event: Any) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TaskCancelled('任务已取消')


def _notify(progress_cb: Optional[Callable[[str, int, str], None]],
            stage: str, percent: int, detail: str) -> None:
    if progress_cb is not None:
        progress_cb(stage, percent, detail)
