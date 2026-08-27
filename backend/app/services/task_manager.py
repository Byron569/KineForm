"""内存任务表 + 单 worker 串行消费 + 协作取消 + watchdog。

形态先例：ComfyUI / Gradio / A1111 的本地任务服务——单进程、内存任务表、
后台线程串行执行、202 + 轮询 + 协作取消（桌面单用户，不引入 celery/redis）。

线程模型：
  - 1 个 worker 线程：queue.Queue 串行取任务 → runner.run(...)；
  - 1 个 watchdog 线程：running 超过 WATCHDOG_TIMEOUT_SEC 无进度 → failed；
  - 全部公共方法线程安全（threading.Lock 保护任务表；health 的 busy 走
    独立 Event，不碰任务表锁）。

状态机（终态：succeeded / failed / cancelled）：
    queued ──→ running ──→ succeeded
       │           └──→ failed
       │           ──→ cancelling ──→ cancelled
       └────────────────────────→ cancelled
"""
from __future__ import annotations

import queue
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..core.config import MAX_FINISHED_TASKS, QUEUE_CAPACITY, WATCHDOG_TIMEOUT_SEC
from .runner_protocol import RunnerProtocol, TaskCancelled

ACTIVE_STATUSES = ('queued', 'running', 'cancelling')


# ---------- 领域异常（HTTP 映射见 app/main.py 全局 exception_handler） ----------

class TaskManagerError(Exception):
    """任务表错误基类。"""


class DuplicateVideoError(TaskManagerError):
    def __init__(self, task_id: str, message: str = '该视频已有进行中的任务'):
        super().__init__(message)
        self.task_id = task_id
        self.message = message


class QueueFullError(TaskManagerError):
    def __init__(self, message: str = '任务队列已满，请稍后再试'):
        super().__init__(message)
        self.message = message


class TaskNotFoundError(TaskManagerError):
    def __init__(self, message: str = '任务不存在'):
        super().__init__(message)
        self.message = message


class TaskFinishedError(TaskManagerError):
    def __init__(self, message: str = '任务已结束，无法取消'):
        super().__init__(message)
        self.message = message


def _now_iso() -> str:
    """本地时区 ISO-8601（含 UTC 偏移；与 report_runner 的落盘时间戳同约定）。"""
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


def _new_task_id() -> str:
    """'t_' + 毫秒时间戳 + 短随机后缀，如 t_1759180000000_a1b2c3d4。"""
    return f't_{int(time.time() * 1000)}_{secrets.token_hex(4)}'


@dataclass
class TaskRecord:
    """任务全量记录（含不外发的 runner/payload/cancel_event 等内部字段）。"""

    task_id: str
    video_id: str
    payload: dict
    runner: RunnerProtocol
    outputs_dir: Path
    result_path: str                      # 契约 §4.2：预定报告路径，受理即存在
    task_type: str = 'report'             # 快照输出为 "type"（report | analyze）
    dedupe_key: str = ''                  # 活跃任务去重键（默认回退 video_id）
    status: str = 'queued'
    stage: str | None = None
    percent: int = 0
    detail: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=_now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    last_progress_at: float = field(default_factory=time.monotonic)
    cancel_event: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        if not self.dedupe_key:
            self.dedupe_key = self.video_id

    def snapshot(self) -> dict:
        """对外快照：契约 §4.2 单任务响应字段（剥离内部字段）。"""
        return {
            'task_id': self.task_id,
            'video_id': self.video_id,
            'type': self.task_type,
            'status': self.status,
            'stage': self.stage,
            'percent': self.percent,
            'detail': self.detail,
            'error': self.error,
            'result_path': self.result_path,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
        }


class TaskManager:
    """内存任务表 + 单 worker + watchdog；生命周期由 app lifespan 管理。"""

    def __init__(self,
                 queue_capacity: int = QUEUE_CAPACITY,
                 watchdog_timeout: float = WATCHDOG_TIMEOUT_SEC,
                 max_finished_tasks: int = MAX_FINISHED_TASKS,
                 watchdog_interval: float | None = None) -> None:
        self._queue_capacity = queue_capacity
        self._watchdog_timeout = watchdog_timeout
        self._max_finished_tasks = max_finished_tasks
        # 轮询间隔 = 超时/10，夹在 [0.05, 5] 秒（900s → 5s；小超时便于测试）
        self._watchdog_interval = (
            watchdog_interval if watchdog_interval is not None
            else max(0.05, min(5.0, watchdog_timeout / 10.0)))
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskRecord] = {}
        self._finished_ids: deque[str] = deque()
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._busy_event = threading.Event()   # health.busy（无锁读取）
        self._worker: threading.Thread | None = None
        self._watchdog: threading.Thread | None = None

    # ---------- 生命周期 ----------

    def start(self) -> None:
        if self._worker is not None:
            return
        self._worker = threading.Thread(
            target=self._worker_loop, name='kineform-worker', daemon=True)
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, name='kineform-watchdog', daemon=True)
        self._worker.start()
        self._watchdog.start()

    def shutdown(self) -> None:
        """优雅停：置停止位、唤醒阻塞在取消检查点的执行体、join 最多 5s。"""
        self._stop_event.set()
        with self._lock:
            for rec in self._tasks.values():
                if rec.status in ACTIVE_STATUSES:
                    rec.cancel_event.set()
        self._queue.put(None)                 # sentinel：让 worker 立即退出 get()
        if self._worker is not None:
            self._worker.join(timeout=5.0)
        if self._watchdog is not None:
            self._watchdog.join(timeout=self._watchdog_interval + 1.0)

    # ---------- 公共 API（线程安全） ----------

    def submit(self, video_id: str, payload: dict, runner: RunnerProtocol,
               outputs_dir: Path, *, task_type: str = 'report',
               dedupe_key: str | None = None,
               result_path: str | None = None) -> str:
        """受理任务：dedupe → 容量检查 → 入队；返回 task_id。

        校验（runner.validate）由路由层在调用前完成，本方法只管排队。
        keyword-only 扩展（既有 report 调用点零改动）：
          task_type   — 'report'（默认）| 'analyze'，随快照输出为 "type"；
          dedupe_key  — 活跃任务去重键（默认 video_id；analyze 为规范化后的
                        源视频绝对路径，见 routers/analysis.py）；
          result_path — 受理时预定结果路径（默认
                        outputs/<video_id>/score_report.json；analyze 为
                        'projects/pending'，succeeded 时由执行体返回值覆写）。
        """
        key = dedupe_key or video_id
        with self._lock:
            active = [r for r in self._tasks.values()
                      if r.status in ACTIVE_STATUSES]
            for rec in active:
                if rec.dedupe_key == key:
                    raise DuplicateVideoError(rec.task_id)
            # 契约 §4.1：并发上限 = 1 运行 + QUEUE_CAPACITY 排队
            if len(active) >= self._queue_capacity + 1:
                raise QueueFullError()
            task_id = _new_task_id()
            self._tasks[task_id] = TaskRecord(
                task_id=task_id,
                video_id=video_id,
                payload=payload,
                runner=runner,
                outputs_dir=Path(outputs_dir),
                result_path=result_path
                or f'outputs/{video_id}/score_report.json',
                task_type=task_type,
                dedupe_key=key)
            self._queue.put(task_id)
        return task_id

    def cancel(self, task_id: str) -> str:
        """取消任务，返回受理后状态（cancelling / cancelled）。"""
        with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                raise TaskNotFoundError()
            if rec.status == 'queued':         # 排队中：直接出队置 cancelled
                rec.status = 'cancelled'
                self._mark_terminal(rec)
                return 'cancelled'
            if rec.status == 'running':        # 运行中：协作取消
                rec.status = 'cancelling'
                rec.cancel_event.set()
                return 'cancelling'
            if rec.status == 'cancelling':     # 幂等（契约 §4.3）
                return 'cancelling'
            raise TaskFinishedError()          # succeeded/failed/cancelled

    def get(self, task_id: str) -> dict:
        with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                raise TaskNotFoundError()
            return rec.snapshot()

    def list_tasks(self) -> tuple[list[dict], int]:
        """全部任务快照（受理顺序）+ 当前排队数（status == queued）。"""
        with self._lock:
            tasks = [r.snapshot() for r in self._tasks.values()]
            queue_length = sum(1 for r in self._tasks.values()
                               if r.status == 'queued')
        return tasks, queue_length

    def is_busy(self) -> bool:
        """health 用：worker 是否正在执行任务（Event 读取，不碰任务表锁）。"""
        return self._busy_event.is_set()

    # ---------- 内部：worker / watchdog ----------

    def _worker_loop(self) -> None:
        while True:
            task_id = self._queue.get()
            if task_id is None:                # shutdown sentinel
                break
            with self._lock:
                rec = self._tasks.get(task_id)
                if rec is None or rec.status != 'queued':
                    continue                   # 排队期间已被取消（或已被淘汰）
                rec.status = 'running'
                rec.started_at = _now_iso()
                rec.last_progress_at = time.monotonic()
            self._busy_event.set()
            try:
                result = rec.runner.run(
                    rec.payload, rec.outputs_dir,
                    self._make_progress_cb(rec), rec.cancel_event, rec.task_id)
            except TaskCancelled:
                outcome, error, result_path = 'cancelled', None, None
            except Exception as exc:           # 执行体任意异常 → failed
                outcome = 'failed'
                error = str(exc) or exc.__class__.__name__
                result_path = None
            else:
                outcome, error = 'succeeded', None
                result_path = (result or {}).get('result_path') or rec.result_path
            self._busy_event.clear()
            with self._lock:
                if rec.status in ('running', 'cancelling'):
                    rec.status = outcome
                    if outcome == 'succeeded':
                        rec.result_path = result_path
                        rec.percent = 100
                    elif outcome == 'failed':
                        rec.error = error
                    self._mark_terminal(rec)
                # 否则已被 watchdog 置 failed（终态），结果作废，不改写

    def _make_progress_cb(
            self, rec: TaskRecord) -> Callable[[str, int, str], None]:
        def progress_cb(stage: str, percent: int, detail: str) -> None:
            with self._lock:
                if rec.status in ('running', 'cancelling'):
                    rec.stage = str(stage)
                    rec.percent = max(0, min(100, int(percent)))
                    rec.detail = str(detail)
                    rec.last_progress_at = time.monotonic()
        return progress_cb

    def _watchdog_loop(self) -> None:
        while not self._stop_event.wait(self._watchdog_interval):
            now = time.monotonic()
            with self._lock:
                for rec in list(self._tasks.values()):
                    if rec.status == 'running' \
                            and now - rec.last_progress_at > self._watchdog_timeout:
                        rec.status = 'failed'
                        rec.error = 'watchdog: 无进度超时'
                        rec.cancel_event.set()   # 通知执行体尽快退出
                        self._mark_terminal(rec)

    def _mark_terminal(self, rec: TaskRecord) -> None:
        """置终态时间戳并 FIFO 淘汰旧终态任务（保留最近 max_finished 条）。"""
        rec.finished_at = _now_iso()
        self._finished_ids.append(rec.task_id)
        while len(self._finished_ids) > self._max_finished_tasks:
            self._tasks.pop(self._finished_ids.popleft(), None)
