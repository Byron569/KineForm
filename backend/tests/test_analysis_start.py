"""POST /api/analysis/start 契约用例（视频姿态分析任务类型）。

FakeAnalysisPipeline 仿真真实 AnalysisPipeline 的行为契约（不加载
torch/cv2）：run(video_path, progress_cb, cancel_event) 分段推进 +
检查点协作取消 + 返回带 project_dir 的结果对象；经
build_analysis_runner(pipeline_factory=...) 注入。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_analysis_runner, get_outputs_dir, get_runner
from app.main import app
from app.services.analysis_runner import build_analysis_runner

from conftest import FakeRunner

SEGMENT_DELAY = 0.05
SLOW_SEGMENTS = 20                            # slow 模式约 1s，轮询可观察进度


class PipelineCancelled(RuntimeError):
    """与 spa_app.pipeline.errors.PipelineCancelled 同名同语义
    （analysis_runner 按类名映射为框架 TaskCancelled）。"""


@dataclass
class FakeAnalysisResult:
    """仿真 AnalysisResult（runner 只读 project_dir 字段）。"""

    project_dir: Path


class FakeAnalysisPipeline:
    """仿真管线：mode 控制行为——

        fast  3 段 × 0.05s 正常完成；
        slow  20 段 × 0.05s，段间检查 cancel_event → PipelineCancelled；
        fail  抛 RuntimeError → failed。
    """

    def __init__(self, mode: str, projects_root: Path):
        self.mode = mode
        self.projects_root = projects_root
        self.run_count = 0

    def run(self, video_path, progress_cb=None, cancel_event=None):
        self.run_count += 1
        if self.mode == 'fail':
            progress_cb('加载模型', 6, '模拟')
            raise RuntimeError('模拟推理失败')

        segments = 3 if self.mode == 'fast' else SLOW_SEGMENTS
        for i in range(segments):
            if cancel_event is not None and cancel_event.is_set():
                raise PipelineCancelled('推理阶段取消')   # 检查点：协作取消
            time.sleep(SEGMENT_DELAY)
            progress_cb('逐帧推理', 8 + int(54 * (i + 1) / segments),
                        f'{i + 1}/{segments} 帧')

        project_dir = self.projects_root / (
            '2026-01-01_120000_' + Path(video_path).stem)
        project_dir.mkdir(parents=True, exist_ok=True)
        progress_cb('完成', 100, project_dir.name)
        return FakeAnalysisResult(project_dir=project_dir)


@pytest.fixture
def spa_projects_root(tmp_path) -> Path:
    d = tmp_path / 'spa_projects'
    d.mkdir()
    return d


@pytest.fixture
def make_start_client(outputs_dir, spa_projects_root):
    """TestClient 工厂：注入 FakeAnalysisPipeline(mode) 与 tmp outputs_dir。

    用法：with make_start_client('slow') as client: ...
    """
    def _make(mode: str = 'fast') -> TestClient:
        fake = FakeAnalysisPipeline(mode, spa_projects_root)
        app.dependency_overrides[get_analysis_runner] = lambda: (
            build_analysis_runner(pipeline_factory=lambda: fake))
        app.dependency_overrides[get_outputs_dir] = lambda: outputs_dir
        return TestClient(app)
    return _make


@pytest.fixture
def make_video(tmp_path):
    """生成假视频文件（start 校验只看存在性 + 扩展名，不看内容）。"""
    def _make(name: str = 'run.mp4') -> Path:
        p = tmp_path / name
        p.write_bytes(b'fake-video-bytes')
        return p
    return _make


# ---------- 受理与成功 ----------

def test_start_accepted_then_succeeded(make_start_client, make_video,
                                       wait_for):
    video = make_video('run.mp4')
    with make_start_client('fast') as client:
        resp = client.post('/api/analysis/start',
                           json={'video_path': str(video)})
        assert resp.status_code == 202
        body = resp.json()
        assert body == {'status': 'accepted',
                        'task_id': body['task_id'],
                        'result_path': 'projects/pending'}
        assert body['task_id'].startswith('t_')

        final = wait_for(client, body['task_id'], 'succeeded')
        assert final['type'] == 'analyze'
        assert final['status'] == 'succeeded'
        assert final['percent'] == 100
        assert final['stage'] == '完成'
        assert final['error'] is None
        assert final['finished_at'] is not None
        # result_path 由 'projects/pending' 覆写为真实项目目录名
        assert final['result_path'] == 'projects/2026-01-01_120000_run'

        # 列表接口同样携带 type（契约：GET /api/tasks）
        listed = [t for t in client.get('/api/tasks').json()['tasks']
                  if t['task_id'] == body['task_id']][0]
        assert listed['type'] == 'analyze'


def test_start_progress_advances(make_start_client, make_video, wait_for):
    """running 期间 percent 单调递增（管线 progress_cb 贯通到任务快照）。"""
    video = make_video('prog.mp4')
    with make_start_client('slow') as client:
        task_id = client.post('/api/analysis/start',
                              json={'video_path': str(video)}).json()['task_id']
        wait_for(client, task_id, 'running')
        percents = []
        while True:
            task = client.get(f'/api/tasks/{task_id}').json()
            if task['status'] != 'running':
                break
            percents.append(task['percent'])
            time.sleep(0.02)
        assert percents == sorted(percents)          # 单调不减
        assert len(set(percents)) >= 2               # 观察到递增
        wait_for(client, task_id, 'succeeded')


# ---------- 同步校验 400 ----------

def test_start_video_not_found_400(make_start_client):
    with make_start_client('fast') as client:
        resp = client.post('/api/analysis/start',
                           json={'video_path': r'D:\no_such_dir\nope.mp4'})
        assert resp.status_code == 400
        body = resp.json()
        assert body['error']['code'] == 'video_not_found'
        assert body['error']['message']


def test_start_video_invalid_extension_400(make_start_client, make_video):
    txt = make_video('notes.txt')
    with make_start_client('fast') as client:
        resp = client.post('/api/analysis/start',
                           json={'video_path': str(txt)})
        assert resp.status_code == 400
        assert resp.json()['error']['code'] == 'video_invalid'


@pytest.mark.parametrize('bad_path', [123, None, ['x'], ''])
def test_start_video_invalid_non_string_400(make_start_client, bad_path):
    """路径非字符串/为空 → 400 video_invalid（冻结契约 start 分支）。"""
    with make_start_client('fast') as client:
        resp = client.post('/api/analysis/start',
                           json={'video_path': bad_path})
        assert resp.status_code == 400
        assert resp.json()['error']['code'] == 'video_invalid'


def test_start_missing_field_422(make_start_client):
    """字段缺失仍走全局 422 validation_error（统一错误体）。"""
    with make_start_client('fast') as client:
        resp = client.post('/api/analysis/start', json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body['error']['code'] == 'validation_error'
        assert 'detail' not in body


# ---------- 去重 409 ----------

def test_start_duplicate_active_video_409(make_start_client, make_video,
                                          wait_for):
    video = make_video('dup.mp4')
    with make_start_client('slow') as client:
        first = client.post('/api/analysis/start',
                            json={'video_path': str(video)})
        assert first.status_code == 202
        task_id = first.json()['task_id']

        # 同视频大小写变体：绝对路径小写规范化后同键 → 409 duplicate_video
        second = client.post('/api/analysis/start',
                             json={'video_path': str(video).upper()})
        assert second.status_code == 409
        body = second.json()
        assert body['error']['code'] == 'duplicate_video'
        assert body['task_id'] == task_id          # 附带既有任务 id（error 同级）

        # 收尾：取消后释放并发位；终态不再参与 dedupe
        assert client.post(f'/api/tasks/{task_id}/cancel').status_code == 200
        wait_for(client, task_id, 'cancelled')
        again = client.post('/api/analysis/start',
                            json={'video_path': str(video)})
        assert again.status_code == 202


# ---------- 取消 / 失败 ----------

def test_start_cancel_running_to_cancelled(make_start_client, make_video,
                                           wait_for):
    """cancel_event 传播到 fake 检查点 → PipelineCancelled 映射为 cancelled。"""
    video = make_video('cancel.mp4')
    with make_start_client('slow') as client:
        task_id = client.post('/api/analysis/start',
                              json={'video_path': str(video)}).json()['task_id']
        wait_for(client, task_id, 'running')

        resp = client.post(f'/api/tasks/{task_id}/cancel')
        assert resp.status_code == 200
        assert resp.json()['status'] in ('cancelling', 'cancelled')

        final = wait_for(client, task_id, 'cancelled')
        assert final['error'] is None
        assert final['finished_at'] is not None


def test_start_pipeline_failure_failed(make_start_client, make_video,
                                       wait_for):
    """管线异常原样上抛 → failed + 中文 error；result_path 保持受理占位。"""
    video = make_video('boom.mp4')
    with make_start_client('fail') as client:
        task_id = client.post('/api/analysis/start',
                              json={'video_path': str(video)}).json()['task_id']
        final = wait_for(client, task_id, 'failed')
        assert final['error'] == '模拟推理失败'
        assert final['result_path'] == 'projects/pending'   # 失败不覆写
        assert final['percent'] < 100                       # 失败不置 100
        assert final['type'] == 'analyze'


# ---------- 与既有 report 任务共存 ----------

def test_report_and_analyze_task_types(make_start_client, make_video,
                                       stage_video, make_payload, wait_for):
    """既有 report 任务不受影响（type='report'）；analyze 为 'analyze'。"""
    stage_video('vid_report')                    # report 任务所需项目目录
    video = make_video('mix.mp4')
    with make_start_client('fast') as client:
        app.dependency_overrides[get_runner] = lambda: FakeRunner('fast')
        report_id = client.post('/api/analysis/submit',
                                json=make_payload('vid_report')).json()['task_id']
        analyze_id = client.post('/api/analysis/start',
                                 json={'video_path': str(video)}).json()['task_id']

        assert wait_for(client, report_id, 'succeeded')['type'] == 'report'
        final = wait_for(client, analyze_id, 'succeeded')
        assert final['type'] == 'analyze'
        assert final['result_path'].startswith('projects/2026-')
