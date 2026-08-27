"""POST /api/analysis/submit 契约用例（API_CONTRACT.md §4.1）。"""
from __future__ import annotations


def test_submit_accepted_202(make_client, stage_video, make_payload):
    stage_video('vid_ok')
    with make_client('fast') as client:
        resp = client.post('/api/analysis/submit', json=make_payload('vid_ok'))
        assert resp.status_code == 202
        body = resp.json()
        assert body['status'] == 'accepted'
        assert body['task_id'].startswith('t_')
        assert body['result_path'] == 'outputs/vid_ok/score_report.json'


def test_submit_markers_empty_400(make_client, stage_video, make_payload):
    stage_video('vid_ok')
    with make_client('fast') as client:
        payload = make_payload('vid_ok')
        payload['markers'] = []
        resp = client.post('/api/analysis/submit', json=payload)
        assert resp.status_code == 400
        body = resp.json()
        assert body['error']['code'] == 'markers_empty'
        assert body['error']['message']


def test_submit_unknown_video_400(make_client, make_payload):
    with make_client('fast') as client:
        resp = client.post('/api/analysis/submit',
                           json=make_payload('no_such_project'))
        assert resp.status_code == 400
        assert resp.json()['error']['code'] == 'unknown_video'


def test_submit_frame_index_out_of_range_400(make_client, stage_video,
                                             make_payload):
    stage_video('vid_range', frame_count=50)
    with make_client('fast') as client:
        # 帧号上限以服务端 motion.json 的 frame_count=50 为准
        resp = client.post('/api/analysis/submit',
                           json=make_payload('vid_range', marker_frames=[50]))
        assert resp.status_code == 400
        assert resp.json()['error']['code'] == 'frame_index_out_of_range'


def test_submit_duplicate_active_video_409(make_client, stage_video,
                                           make_payload, wait_for):
    stage_video('vid_dup')
    with make_client('slow') as client:
        first = client.post('/api/analysis/submit', json=make_payload('vid_dup'))
        assert first.status_code == 202
        task_id = first.json()['task_id']

        second = client.post('/api/analysis/submit', json=make_payload('vid_dup'))
        assert second.status_code == 409
        body = second.json()
        assert body['error']['code'] == 'duplicate_video'
        assert body['task_id'] == task_id       # 附带既有任务 id（error 同级）

        # 收尾：取消后释放并发位
        assert client.post(f'/api/tasks/{task_id}/cancel').status_code == 200
        wait_for(client, task_id, 'cancelled')


def test_submit_again_after_terminal_202(make_client, stage_video,
                                         make_payload, wait_for):
    """终态任务不参与 dedupe：完成后同 video_id 可再次提交。"""
    stage_video('vid_again')
    with make_client('fast') as client:
        first = client.post('/api/analysis/submit',
                            json=make_payload('vid_again'))
        task_id_1 = first.json()['task_id']
        wait_for(client, task_id_1, 'succeeded')

        second = client.post('/api/analysis/submit',
                             json=make_payload('vid_again'))
        assert second.status_code == 202
        assert second.json()['task_id'] != task_id_1


def test_submit_queue_full_409(make_client, stage_video, make_payload):
    """契约 §4.1：并发上限 = 1 运行 + 1 排队；占满后提交 → 409 queue_full。"""
    for vid in ('v1', 'v2', 'v3', 'v4'):
        stage_video(vid)
    with make_client('slow') as client:
        assert client.post('/api/analysis/submit',
                           json=make_payload('v1')).status_code == 202
        assert client.post('/api/analysis/submit',
                           json=make_payload('v2')).status_code == 202
        for vid in ('v3', 'v4'):
            resp = client.post('/api/analysis/submit', json=make_payload(vid))
            assert resp.status_code == 409
            assert resp.json()['error']['code'] == 'queue_full'
        # 收尾：取消两个活跃任务，快速释放 worker
        for task in client.get('/api/tasks').json()['tasks']:
            if task['status'] in ('queued', 'running', 'cancelling'):
                client.post(f"/api/tasks/{task['task_id']}/cancel")


def test_submit_malformed_body_422(make_client, stage_video):
    """请求体缺字段 → 422 且为统一错误体（契约 §4.6，非默认 detail）。"""
    stage_video('vid_bad')
    with make_client('fast') as client:
        resp = client.post('/api/analysis/submit', json={'video_id': 'vid_bad'})
        assert resp.status_code == 422
        body = resp.json()
        assert body['error']['code'] == 'validation_error'
        assert body['error']['message']
        assert 'detail' not in body
