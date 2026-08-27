"""POST /api/tasks/{task_id}/cancel 契约用例（§4.3）。"""
from __future__ import annotations


def test_cancel_running_to_cancelled(make_client, stage_video, make_payload,
                                     wait_for):
    stage_video('vid_run')
    with make_client('slow') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_run')).json()['task_id']
        wait_for(client, task_id, 'running')

        resp = client.post(f'/api/tasks/{task_id}/cancel')
        assert resp.status_code == 200
        assert resp.json() == {'task_id': task_id, 'status': 'cancelling'}

        final = wait_for(client, task_id, 'cancelled')
        assert final['error'] is None
        assert final['finished_at'] is not None


def test_cancel_queued_directly_cancelled(make_client, stage_video,
                                          make_payload, wait_for):
    """queued 态取消 = 直接连出队置 cancelled；运行中任务不受影响。"""
    stage_video('vid_q1')
    stage_video('vid_q2')
    with make_client('slow') as client:
        running_id = client.post('/api/analysis/submit',
                                 json=make_payload('vid_q1')).json()['task_id']
        wait_for(client, running_id, 'running')
        queued_id = client.post('/api/analysis/submit',
                                json=make_payload('vid_q2')).json()['task_id']

        resp = client.post(f'/api/tasks/{queued_id}/cancel')
        assert resp.status_code == 200
        assert resp.json()['status'] == 'cancelled'
        assert client.get(
            f'/api/tasks/{queued_id}').json()['status'] == 'cancelled'

        wait_for(client, running_id, 'succeeded')        # 运行中任务正常完成


def test_cancel_terminal_409(make_client, stage_video, make_payload, wait_for):
    """终态（succeeded/failed）任务取消 → 409 task_finished。"""
    stage_video('vid_done')
    stage_video('vid_bad')
    with make_client('fast') as client:
        ok_id = client.post('/api/analysis/submit',
                            json=make_payload('vid_done')).json()['task_id']
        wait_for(client, ok_id, 'succeeded')
        resp = client.post(f'/api/tasks/{ok_id}/cancel')
        assert resp.status_code == 409
        assert resp.json()['error']['code'] == 'task_finished'

    with make_client('fail') as client:
        bad_id = client.post('/api/analysis/submit',
                             json=make_payload('vid_bad')).json()['task_id']
        wait_for(client, bad_id, 'failed')
        assert client.post(f'/api/tasks/{bad_id}/cancel').status_code == 409


def test_cancel_unknown_task_404(make_client):
    with make_client('fast') as client:
        resp = client.post('/api/tasks/t_nope/cancel')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'task_not_found'


def test_cancel_idempotent_while_cancelling(make_client, stage_video,
                                            make_payload, wait_for):
    """对 cancelling 态重复 cancel → 200 且状态不变（契约 §4.3 幂等）。"""
    stage_video('vid_idem')
    with make_client('slow') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_idem')).json()['task_id']
        wait_for(client, task_id, 'running')

        first = client.post(f'/api/tasks/{task_id}/cancel')
        assert first.status_code == 200
        assert first.json()['status'] == 'cancelling'

        # FakeRunner 取消收尾窗口 ~0.2s：第二次 cancel 应幂等返回 cancelling
        second = client.post(f'/api/tasks/{task_id}/cancel')
        assert second.status_code == 200
        assert second.json()['status'] == 'cancelling'

        wait_for(client, task_id, 'cancelled')


def test_resubmit_after_cancel_accepted(make_client, stage_video,
                                        make_payload, wait_for):
    """取消终态后同 video_id 重新提交 → 202（dedupe 只针对活跃任务）。"""
    stage_video('vid_rc')
    with make_client('slow') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_rc')).json()['task_id']
        wait_for(client, task_id, 'running')
        client.post(f'/api/tasks/{task_id}/cancel')
        wait_for(client, task_id, 'cancelled')

        resp = client.post('/api/analysis/submit', json=make_payload('vid_rc'))
        assert resp.status_code == 202
