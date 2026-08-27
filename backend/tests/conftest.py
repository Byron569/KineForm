"""框架层 API 测试公共设施（FakeRunner + 依赖注入 fixtures）。

FakeRunner 仿真真实执行体 app/services/report_runner.py 的契约行为：
  - validate：markers 空 / 项目目录缺 motion.json / 帧号越界 → ValidationError；
  - run：mode 控制行为——
      fast  正常完成（3 段进度，无延迟）；
      fail  抛 RuntimeError → failed；
      slow  20 段 × 50ms 分段推进（约 1s），段间检查 cancel_event，
            检测到取消后延迟 0.2s 再抛 TaskCancelled（保证 cancelling
            状态可被轮询观察到）；
      stuck 永不推进（watchdog 用例）。
"""
from __future__ import annotations

import os

# 必须在 import app.* 之前：关闭 lifespan 的分析模型预载线程
# （否则 pytest 进程会加载 torch/权重，拖慢且与 FakeAnalysisRunner 无关）
os.environ.setdefault('KINEFORM_PRELOAD_ANALYSIS', '0')

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_outputs_dir, get_runner
from app.main import app
from app.services.runner_protocol import TaskCancelled, ValidationError

SLOW_SEGMENTS = 20
SLOW_SEGMENT_DELAY = 0.05
CANCEL_LATENCY = 0.2


class FakeRunner:
    """仿真执行体：校验规则对齐 report_runner，运行行为由 mode 决定。"""

    def __init__(self, mode: str = 'fast') -> None:
        self.mode = mode

    # ---- 同步校验（与真实执行体同规则） ----
    def validate(self, payload: dict, outputs_dir: Path) -> None:
        payload = payload or {}
        markers = payload.get('markers')
        if not isinstance(markers, list) or not markers:
            raise ValidationError('markers_empty', '未包含任何打点标记')

        video_id = payload.get('video_id')
        if (not isinstance(video_id, str) or not video_id
                or video_id in ('.', '..')
                or '/' in video_id or '\\' in video_id):
            raise ValidationError('unknown_video', f'未找到视频项目: {video_id}')

        motion_path = Path(outputs_dir) / video_id / 'motion.json'
        try:
            motion = json.loads(motion_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            motion = None
        if not isinstance(motion, dict):
            raise ValidationError('unknown_video', f'未找到视频项目: {video_id}')

        frame_count = motion.get('frame_count') or len(motion.get('frames') or [])
        for marker in markers:
            fi = marker.get('frameIndex') if isinstance(marker, dict) else None
            if not isinstance(fi, int) or isinstance(fi, bool) \
                    or fi < 0 or fi >= frame_count:
                raise ValidationError(
                    'frame_index_out_of_range',
                    f'打点帧号越界: {fi!r}（有效范围 0..{frame_count - 1}）')

    # ---- 异步执行 ----
    def run(self, payload: dict, outputs_dir: Path, progress_cb,
            cancel_event, task_id: str) -> dict:
        video_id = payload['video_id']

        if self.mode == 'fail':
            progress_cb('validate', 10, '校验提交数据')
            raise RuntimeError('模拟推理失败')

        if self.mode == 'stuck':            # 永不推进，等待取消/超时
            cancel_event.wait(30)
            raise TaskCancelled('长时间无进度')

        segments = 3 if self.mode == 'fast' else SLOW_SEGMENTS
        delay = 0.0 if self.mode == 'fast' else SLOW_SEGMENT_DELAY
        for i in range(segments):
            if cancel_event.wait(delay):    # 检查点：协作取消
                time.sleep(CANCEL_LATENCY)  # 模拟收尾耗时，使 cancelling 可观察
                raise TaskCancelled('任务已取消')
            percent = (i + 1) * 100 // segments
            progress_cb('analysis', percent, f'进度 {percent}%')

        project_dir = Path(outputs_dir) / video_id
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / 'score_report.json').write_text(
            json.dumps({'task_id': task_id, 'video_id': video_id},
                       ensure_ascii=False),
            encoding='utf-8')
        return {'result_path': f'outputs/{video_id}/score_report.json'}


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """每个用例结束后清理 dependency_overrides（对不用 app 的用例无副作用）。"""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def outputs_dir(tmp_path) -> Path:
    d = tmp_path / 'outputs'
    d.mkdir()
    return d


@pytest.fixture
def make_client(outputs_dir):
    """TestClient 工厂：注入 FakeRunner(mode) 与 tmp outputs_dir。

    用法：with make_client('slow') as client: ...
    """
    def _make(mode: str = 'fast') -> TestClient:
        app.dependency_overrides[get_runner] = lambda: FakeRunner(mode)
        app.dependency_overrides[get_outputs_dir] = lambda: outputs_dir
        return TestClient(app)
    return _make


@pytest.fixture
def stage_video(outputs_dir):
    """登记视频：outputs_dir/<video_id>/motion.json（服务端事实来源）。"""
    def _stage(video_id: str, frame_count: int = 100) -> Path:
        project_dir = outputs_dir / video_id
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / 'motion.json').write_text(json.dumps({
            'schema_version': '1.0',
            'video_id': video_id,
            'fps': 30.0,
            'frame_count': frame_count,
            'frames': [{'frameIndex': i,
                        'timestampMs': round(i * 33.33, 1),
                        'metrics': {}}
                       for i in range(frame_count)],
        }, ensure_ascii=False), encoding='utf-8')
        return project_dir
    return _stage


@pytest.fixture
def make_payload():
    """构造契约 §4.1 形状的提交请求体。"""
    def _make(video_id: str, frame_count: int = 100,
              marker_frames: list | None = None) -> dict:
        frames = [10] if marker_frames is None else marker_frames
        return {
            'video_id': video_id,
            'fps': 30.0,
            'frame_count': frame_count,
            'markers': [
                {'id': f'm_{i}',
                 'frameIndex': f,
                 'timestampMs': round(f * 33.33, 1),
                 'label': f'标记{i}',
                 'comment': '',
                 'metrics': {'left_knee_angle': 142.13}}
                for i, f in enumerate(frames)
            ],
            'motion': {'source': f'outputs/{video_id}/motion.json',
                       'sha256': '0' * 64},
        }
    return _make


@pytest.fixture
def wait_for():
    """轮询 GET /api/tasks/{task_id} 直至目标状态（默认 15s 超时）。"""
    def _wait(client: TestClient, task_id: str, target: str,
              timeout: float = 15.0) -> dict:
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            resp = client.get(f'/api/tasks/{task_id}')
            assert resp.status_code == 200
            last = resp.json()
            if last['status'] == target:
                return last
            if last['status'] in ('failed', 'cancelled') \
                    and target not in ('failed', 'cancelled'):
                pytest.fail(f'任务意外进入 {last["status"]}: {last.get("error")}')
            time.sleep(0.02)
        pytest.fail(f'等待任务 {task_id} 达到 {target} 超时；'
                    f'最后状态: {last and last.get("status")}')
    return _wait
