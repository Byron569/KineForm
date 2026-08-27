"""meta.json 契约用例：run 成功写 meta + GET /api/projects/{id}/meta 端点。

复用 test_analysis_start 的 FakeAnalysisPipeline 注入模式（不加载
torch/cv2）：start 受理 → succeeded 后在项目目录落 meta.json；GET meta
端点按 project_not_found / meta_not_found / 原样返回 三种状态覆盖。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_analysis_runner, get_outputs_dir
from app.main import app
from app.services.analysis_runner import build_analysis_runner


@dataclass
class FakeAnalysisResult:
    """仿真 AnalysisResult（runner 只读 project_dir 字段）。"""

    project_dir: Path


class FakeAnalysisPipeline:
    """仿真管线：run 分段推进后产出带时间戳前缀的项目目录（同 start 用例）。"""

    def __init__(self, projects_root: Path):
        self.mode = 'fast'
        self.projects_root = projects_root

    def run(self, video_path, progress_cb=None, cancel_event=None):
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
    """TestClient 工厂：注入 FakeAnalysisPipeline 与 tmp outputs_dir。

    把分析项目根目录挂在 client._spa_projects_root 供断言回读项目产物。
    """
    def _make(mode: str = 'fast') -> TestClient:
        fake = FakeAnalysisPipeline(spa_projects_root)
        app.dependency_overrides[get_analysis_runner] = lambda: (
            build_analysis_runner(pipeline_factory=lambda: fake))
        app.dependency_overrides[get_outputs_dir] = lambda: outputs_dir
        client = TestClient(app)
        client._spa_projects_root = spa_projects_root
        return client
    return _make


@pytest.fixture
def make_video(tmp_path):
    """"""  # 生成假视频文件（start 校验只看存在性 + 扩展名）。
    def _make(name: str) -> Path:
        p = tmp_path / name
        p.write_bytes(b'fake-video-bytes')
        return p
    return _make


def _stage_project(outputs_dir: Path, video_id: str,
                   meta: dict | None = None) -> Path:
    """假项目：motion.json 必写（服务端有效项目判据），meta.json 按需。"""
    d = outputs_dir / video_id
    d.mkdir(parents=True, exist_ok=True)
    (d / 'motion.json').write_text(json.dumps(
        {'schema_version': '1.0', 'video_id': video_id, 'frames': []},
        ensure_ascii=False), encoding='utf-8')
    if meta is not None:
        (d / 'meta.json').write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return d


# ---------- analyze succeed 后写 meta.json ----------

def test_meta_written_on_success_with_project_name(make_start_client,
                                                   make_video, wait_for):
    """传了 project_name → meta.json 含之；source_video_name=原始文件名；
    analyzed_at 为存在的时间串。"""
    video = make_video('run_back.mp4')
    with make_start_client('fast') as client:
        task_id = client.post('/api/analysis/start', json={
            'video_path': str(video),
            'project_name': '晨跑训练'}).json()['task_id']
        final = wait_for(client, task_id, 'succeeded')
        project_dir = Path(client._spa_projects_root) / '2026-01-01_120000_run_back'
        assert project_dir.name == final['result_path'].split('/')[-1]

        meta = json.loads((project_dir / 'meta.json').read_text(
            encoding='utf-8'))
        assert meta['source_video_name'] == 'run_back.mp4'
        assert meta['project_name'] == '晨跑训练'
        # analyzed_at 为合法本地 ISO-8601（可被 datetime.fromisoformat 解析）
        analyzed_at = meta.get('analyzed_at')
        assert analyzed_at
        datetime.fromisoformat(analyzed_at)


def test_meta_written_without_project_name(make_start_client, make_video,
                                           wait_for):
    """未传 project_name → meta.json 省略该键（保留 source_video_name）。"""
    video = make_video('plain.mp4')
    with make_start_client('fast') as client:
        task_id = client.post('/api/analysis/start',
                              json={'video_path': str(video)}).json()['task_id']
        wait_for(client, task_id, 'succeeded')
        root = Path(client._spa_projects_root)
        meta = json.loads((root / '2026-01-01_120000_plain' /
                           'meta.json').read_text(encoding='utf-8'))
        assert meta['source_video_name'] == 'plain.mp4'
        assert 'project_name' not in meta
        assert meta['analyzed_at']


def test_meta_written_overwrites_existing(make_start_client, make_video,
                                          wait_for):
    """已有 meta.json 时覆盖更新（保留 source_video_name 为本轮文件名）。"""
    video = make_video('again.mp4')
    with make_start_client('fast') as client:
        root = Path(client._spa_projects_root)
        target = root / '2026-01-01_120000_again'
        target.mkdir(parents=True, exist_ok=True)
        (target / 'meta.json').write_text(
            json.dumps({'source_video_name': 'stale.mp4',
                        'project_name': '旧名'}),
            encoding='utf-8')
        task_id = client.post('/api/analysis/start',
                              json={'video_path': str(video),
                                    'project_name': '新名'}).json()['task_id']
        wait_for(client, task_id, 'succeeded')
        meta = json.loads((target / 'meta.json').read_text(encoding='utf-8'))
        assert meta['source_video_name'] == 'again.mp4'
        assert meta['project_name'] == '新名'


# ---------- StartAnalysisRequest.project_name 可空/省略 ----------

def test_start_project_name_nullable(make_start_client, make_video):
    """省略 / null / 空串 均可受理（202；各用独立视频避免去重冲突）。"""
    cases = [
        ('omitted.mp4', {}),                                  # 省略
        ('null.mp4', {'project_name': None}),                 # null
        ('empty.mp4', {'project_name': ''}),                  # 空串
    ]
    with make_start_client('fast') as client:
        for name, extra in cases:
            body = {'video_path': str(make_video(name)), **extra}
            resp = client.post('/api/analysis/start', json=body)
            assert resp.status_code == 202, body
            assert resp.json()['status'] == 'accepted'


def test_start_project_name_non_string_422(make_start_client, make_video):
    """project_name 非字符串 → 全局 422 validation_error 兜底。"""
    video = make_video('badname.mp4')
    with make_start_client('fast') as client:
        resp = client.post('/api/analysis/start',
                           json={'video_path': str(video),
                                 'project_name': 123})
        assert resp.status_code == 422
        body = resp.json()
        assert body['error']['code'] == 'validation_error'
        assert 'detail' not in body


# ---------- GET /api/projects/{video_id}/meta ----------

def test_get_meta_200_raw(make_client, outputs_dir):
    """meta.json 原样返回（内容语义一致 + 字节一致）。"""
    doc = {'source_video_name': 'run_back.mp4',
           'project_name': '晨跑训练',
           'analyzed_at': '2026-08-27T10:00:00'}
    d = _stage_project(outputs_dir, 'vid_meta', doc)
    with make_client() as client:
        resp = client.get('/api/projects/vid_meta/meta')
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('application/json')
        assert resp.json() == doc
        assert resp.content == (d / 'meta.json').read_bytes()  # 原样字节


def test_get_meta_not_found(make_client, outputs_dir):
    """项目存在但无 meta.json（旧项目）→ 404 meta_not_found。"""
    _stage_project(outputs_dir, 'vid_nometa')
    with make_client() as client:
        resp = client.get('/api/projects/vid_nometa/meta')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'meta_not_found'


def test_get_meta_project_not_found(make_client, outputs_dir):
    """项目不存在 → 404 project_not_found（与其它资源组一致）。"""
    _stage_project(outputs_dir, 'vid_ok')
    (outputs_dir / 'no_motion').mkdir()          # 目录存在但无 motion.json
    with make_client() as client:
        for vid in ('no_such_project', 'no_motion'):
            resp = client.get(f'/api/projects/{vid}/meta')
            assert resp.status_code == 404
            assert resp.json()['error']['code'] == 'project_not_found'


def test_get_meta_traversal_blocked(make_client, outputs_dir):
    """路径穿越 → 404 project_not_found，绝不读取外层文件。"""
    d = _stage_project(outputs_dir, 'vid_meta',
                       {'source_video_name': 'a.mp4', 'analyzed_at': 'x'})
    outside = outputs_dir.parent / 'outside_meta_decoy'
    outside.mkdir()
    (outside / 'meta.json').write_text(
        json.dumps({'source_video_name': 'decoy.mp4'}), encoding='utf-8')
    try:
        with make_client() as client:
            # 命中路由但 video_id 含穿越片段 → project_not_found
            for bad in ('%2E%2E', 'a..b', '..%5Cetc', 'x:y'):
                resp = client.get(f'/api/projects/{bad}/meta')
                assert resp.status_code == 404, bad
                assert resp.json()['error']['code'] == 'project_not_found', bad
            # 解码后破坏路径结构 → 框架级 404，同样不触达文件系统
            for bad in ('..', '..%2Fetc'):
                resp = client.get(f'/api/projects/{bad}/meta')
                assert resp.status_code == 404, bad
                assert 'error' in resp.json()
    finally:
        assert (d / 'meta.json').exists()
        assert (outside / 'meta.json').exists()   # 诱饵未被读取/破坏