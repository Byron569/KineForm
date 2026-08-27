"""项目资源端点契约用例（GET /api/projects 系列 + /api/tasks/{id}/result）。

假项目布局：outputs/<video_id>/{motion.json（头部+2帧）, events.json,
annotations.json, source_cfr.mp4/analysis.mp4（几字节假文件）}。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_json(path: Path, doc: dict) -> None:
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                    encoding='utf-8')


def _motion_doc(video_id: str) -> dict:
    """motion.json：契约 §2 顶层字段 + 2 帧（列表端点只消费头部字段）。"""
    return {
        'schema_version': '1.0',
        'video_id': video_id,
        'source_video': 'source_cfr.mp4',
        'fps': 29.97,
        'frame_count': 2,
        'width': 1920,
        'height': 1080,
        'created_at': '2026-08-26T10:00:00',
        'frames': [
            {'frameIndex': 0, 'timestampMs': 0.0, 'metrics': {}},
            {'frameIndex': 1, 'timestampMs': 33.4, 'metrics': {}},
        ],
    }


def _annotations_doc(video_id: str) -> dict:
    """annotations.json：契约 §3 形状（含 fps/createdAt 等额外字段）。"""
    return {
        'schema_version': '1.0',
        'video_id': video_id,
        'fps': 29.97,
        'markers': [
            {'id': 'm_1',
             'frameIndex': 0,
             'timestampMs': 0.0,
             'label': '起跳瞬间',
             'comment': '',
             'createdAt': '2026-08-26T11:00:00',
             'updatedAt': '2026-08-26T11:05:00'},
        ],
    }


@pytest.fixture
def stage_project(outputs_dir):
    """假项目工厂：motion.json 必写，其余产物按 kwargs 落盘。"""
    def _stage(video_id: str, *, events: bool = False, annotations: bool = False,
               source_video: bool = False, analysis_video: bool = False) -> Path:
        d = outputs_dir / video_id
        d.mkdir(parents=True, exist_ok=True)
        _write_json(d / 'motion.json', _motion_doc(video_id))
        if events:
            _write_json(d / 'events.json', {
                'schema_version': '1.0',
                'events': [{'type': 'left_touchdown', 'frame_index': 1,
                            'timestamp_ms': 33.4, 'value': 12.5}],
            })
        if annotations:
            _write_json(d / 'annotations.json', _annotations_doc(video_id))
        if source_video:
            (d / 'source_cfr.mp4').write_bytes(b'FAKE_MP4_BYTES_0123456789')
        if analysis_video:
            (d / 'analysis.mp4').write_bytes(b'FAKE_ANALYSIS_BYTES_9876543210')
        return d
    return _stage


# ---------- GET /api/projects（列表） ----------

def test_list_projects_empty(make_client):
    with make_client() as client:
        resp = client.get('/api/projects')
        assert resp.status_code == 200
        assert resp.json() == {'projects': []}


def test_list_projects_filters_and_sorts(make_client, outputs_dir,
                                         stage_project):
    """仅收录含 motion.json 的一级子目录；元数据取自 motion.json 头部；
    按 video_id 倒序（新在前）。"""
    stage_project('vid_b', events=True, annotations=True)
    stage_project('vid_a')
    stage_project('vid_c', events=True)
    (outputs_dir / 'no_motion').mkdir()                      # 无 motion.json
    (outputs_dir / 'broken').mkdir()
    (outputs_dir / 'broken' / 'motion.json').write_text('{oops',        # 损坏
                                                        encoding='utf-8')
    (outputs_dir / 'stray.json').write_text('{}', encoding='utf-8')     # 散落文件

    with make_client() as client:
        resp = client.get('/api/projects')
        assert resp.status_code == 200
        projects = resp.json()['projects']
        assert [p['video_id'] for p in projects] == ['vid_c', 'vid_b', 'vid_a']
        by_id = {p['video_id']: p for p in projects}
        assert by_id['vid_b'] == {
            'video_id': 'vid_b',
            'fps': 29.97,
            'frame_count': 2,
            'width': 1920,
            'height': 1080,
            'created_at': '2026-08-26T10:00:00',
            'has_events': True,
            'has_annotations': True,
        }
        assert by_id['vid_a']['has_events'] is False
        assert by_id['vid_a']['has_annotations'] is False
        assert by_id['vid_c']['has_events'] is True
        assert by_id['vid_c']['has_annotations'] is False


# ---------- GET motion ----------

def test_get_motion_raw_bytes(make_client, stage_project):
    d = stage_project('vid_ok')
    with make_client() as client:
        resp = client.get('/api/projects/vid_ok/motion')
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('application/json')
        assert resp.json() == _motion_doc('vid_ok')
        assert resp.content == (d / 'motion.json').read_bytes()   # 原样字节


def test_get_motion_project_not_found(make_client, outputs_dir, stage_project):
    stage_project('vid_ok')
    (outputs_dir / 'no_motion').mkdir()                  # 目录存在但无 motion.json
    with make_client() as client:
        for vid in ('no_such_project', 'no_motion'):
            resp = client.get(f'/api/projects/{vid}/motion')
            assert resp.status_code == 404
            body = resp.json()
            assert body['error']['code'] == 'project_not_found'
            assert vid in body['error']['message']


# ---------- GET events ----------

def test_get_events_ok(make_client, stage_project):
    d = stage_project('vid_ev', events=True)
    with make_client() as client:
        resp = client.get('/api/projects/vid_ev/events')
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('application/json')
        assert resp.content == (d / 'events.json').read_bytes()


def test_get_events_not_found(make_client, stage_project):
    stage_project('vid_no_ev')
    with make_client() as client:
        resp = client.get('/api/projects/vid_no_ev/events')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'events_not_found'


# ---------- annotations GET / PUT ----------

def test_get_annotations_not_found(make_client, stage_project):
    stage_project('vid_blank')
    with make_client() as client:
        resp = client.get('/api/projects/vid_blank/annotations')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'annotations_not_found'


def test_put_annotations_roundtrip(make_client, stage_project):
    d = stage_project('vid_ann')
    doc = _annotations_doc('vid_ann')
    with make_client() as client:
        resp = client.put('/api/projects/vid_ann/annotations', json=doc)
        assert resp.status_code == 200
        assert resp.json() == {'status': 'saved',
                               'path': 'outputs/vid_ann/annotations.json'}

        # 落盘回读：JSON 语义一致 + UTF-8（ensure_ascii=False）+ indent=2
        raw = (d / 'annotations.json').read_text(encoding='utf-8')
        assert json.loads(raw) == doc
        assert '起跳瞬间' in raw
        assert '\n  "' in raw
        # GET 回读一致（覆盖写后即可读）
        resp = client.get('/api/projects/vid_ann/annotations')
        assert resp.status_code == 200
        assert resp.json() == doc

        # 再 PUT 覆盖（前端防抖后的重复保存 = 全量覆盖）
        doc['markers'] = []
        resp = client.put('/api/projects/vid_ann/annotations', json=doc)
        assert resp.status_code == 200
        assert json.loads((d / 'annotations.json').read_text(
            encoding='utf-8'))['markers'] == []


def test_put_annotations_video_id_mismatch(make_client, stage_project):
    d = stage_project('vid_ann')
    with make_client() as client:
        resp = client.put('/api/projects/vid_ann/annotations',
                          json=_annotations_doc('vid_other'))
        assert resp.status_code == 400
        assert resp.json()['error']['code'] == 'video_id_mismatch'
        assert not (d / 'annotations.json').exists()      # 校验失败不落盘


def test_put_annotations_project_not_found(make_client):
    with make_client() as client:
        resp = client.put('/api/projects/no_such_project/annotations',
                          json=_annotations_doc('no_such_project'))
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'project_not_found'


def test_put_annotations_invalid_body_422(make_client, stage_project):
    stage_project('vid_ann')
    with make_client() as client:
        resp = client.put('/api/projects/vid_ann/annotations',
                          json={'schema_version': 1.0,      # 非字符串
                                'video_id': 'vid_ann',
                                'markers': 'not-a-list'})   # 非列表
        assert resp.status_code == 422
        body = resp.json()
        assert body['error']['code'] == 'validation_error'
        assert 'detail' not in body


# ---------- 视频（video / analysis） ----------

def test_get_video_full_and_range(make_client, stage_project):
    d = stage_project('vid_play', source_video=True)
    payload = (d / 'source_cfr.mp4').read_bytes()
    assert len(payload) == 25                       # 足够覆盖 bytes=5-9
    with make_client() as client:
        resp = client.get('/api/projects/vid_play/video')
        assert resp.status_code == 200
        assert resp.headers['content-type'] == 'video/mp4'
        assert resp.headers['accept-ranges'] == 'bytes'
        assert resp.content == payload

        rng = client.get('/api/projects/vid_play/video',
                         headers={'Range': 'bytes=0-3'})
        assert rng.status_code == 206
        assert rng.headers['content-range'] == f'bytes 0-3/{len(payload)}'
        assert rng.content == payload[:4]

        rng_mid = client.get('/api/projects/vid_play/video',
                             headers={'Range': 'bytes=5-9'})
        assert rng_mid.status_code == 206
        assert rng_mid.headers['content-range'] == f'bytes 5-9/{len(payload)}'
        assert rng_mid.content == payload[5:10]


def test_get_video_not_found(make_client, stage_project):
    stage_project('vid_novideo')                          # 无 source_cfr.mp4
    with make_client() as client:
        resp = client.get('/api/projects/vid_novideo/video')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'video_not_found'


def test_get_analysis_video_ok(make_client, stage_project):
    d = stage_project('vid_ana', analysis_video=True)
    with make_client() as client:
        resp = client.get('/api/projects/vid_ana/analysis')
        assert resp.status_code == 200
        assert resp.headers['content-type'] == 'video/mp4'
        assert resp.content == (d / 'analysis.mp4').read_bytes()
        # 同样支持 Range
        rng = client.get('/api/projects/vid_ana/analysis',
                         headers={'Range': 'bytes=0-3'})
        assert rng.status_code == 206


def test_get_analysis_video_not_found(make_client, stage_project):
    stage_project('vid_noana')                            # 无 analysis.mp4
    with make_client() as client:
        resp = client.get('/api/projects/vid_noana/analysis')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'video_not_found'


# ---------- 路径穿越 ----------

def test_path_traversal_blocked(make_client, outputs_dir, stage_project):
    """穿越/非法 video_id 一律 404，绝不读取 outputs_dir 之外的文件。"""
    stage_project('vid_ok')
    # outputs 根之外的诱饵项目：任何穿越请求都不得读到它
    outside = outputs_dir.parent / 'outside_decoy'
    outside.mkdir()
    _write_json(outside / 'motion.json', _motion_doc('decoy'))
    try:
        with make_client() as client:
            # 命中路由但 video_id 含穿越片段（解码后为单段）→ project_not_found
            for bad in ('%2E%2E',            # 解码为 '..'
                        'a..b',              # 含 '..' 子串
                        '..%5Cetc',          # 解码为 '..\etc'
                        'x:y'):              # Windows 盘符冒号
                resp = client.get(f'/api/projects/{bad}/motion')
                assert resp.status_code == 404, bad
                assert resp.json()['error']['code'] == 'project_not_found', bad

            # 解码后破坏路径结构（多出段/客户端归一化）→ 框架级 404，
            # 同样不触达文件系统
            for bad in ('..', '..%2Fetc', 'sub%2F..%2Fetc'):
                resp = client.get(f'/api/projects/{bad}/motion')
                assert resp.status_code == 404, bad
                assert 'error' in resp.json()
    finally:
        assert (outside / 'motion.json').exists()         # 诱饵未被破坏


# ---------- GET /api/tasks/{task_id}/result ----------

def test_task_result_not_found(make_client):
    with make_client() as client:
        resp = client.get('/api/tasks/t_nope/result')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'task_not_found'


def test_task_result_running_409(make_client, stage_video, make_payload,
                                 wait_for):
    """非终态（queued/running/cancelling）→ 409，message 含当前状态。"""
    stage_video('vid_running')
    with make_client('slow') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_running')).json()['task_id']
        wait_for(client, task_id, 'running')
        resp = client.get(f'/api/tasks/{task_id}/result')
        assert resp.status_code == 409
        body = resp.json()
        assert body['error']['code'] == 'task_not_finished'
        assert 'running' in body['error']['message']


def test_task_result_failed_409(make_client, stage_video, make_payload,
                                wait_for):
    stage_video('vid_fail')
    with make_client('fail') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_fail')).json()['task_id']
        wait_for(client, task_id, 'failed')
        resp = client.get(f'/api/tasks/{task_id}/result')
        assert resp.status_code == 409
        body = resp.json()
        assert body['error']['code'] == 'task_not_finished'
        assert 'failed' in body['error']['message']


def test_task_result_succeeded_and_report_missing(make_client, outputs_dir,
                                                  stage_video, make_payload,
                                                  wait_for):
    """succeeded → 200 报告原样；succeeded 但文件被清 → 404 report_not_found。"""
    stage_video('vid_done')
    with make_client('fast') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_done')).json()['task_id']
        wait_for(client, task_id, 'succeeded')

        resp = client.get(f'/api/tasks/{task_id}/result')
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('application/json')
        assert resp.json() == {'task_id': task_id, 'video_id': 'vid_done'}

        (outputs_dir / 'vid_done' / 'score_report.json').unlink()
        resp = client.get(f'/api/tasks/{task_id}/result')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'report_not_found'
