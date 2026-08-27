"""任务全生命周期 / 状态机 / 列表 / health / watchdog 用例（§4.2/§4.4/§4.5）。"""
from __future__ import annotations

import time
from datetime import datetime

from app.services.runner_protocol import TaskCancelled
from app.services.task_manager import TaskManager


def test_lifecycle_queued_running_succeeded(make_client, stage_video,
                                             make_payload, wait_for):
    """提交 → queued → running（percent 递增）→ succeeded → result_path。"""
    stage_video('vid_main')
    stage_video('vid_second')
    with make_client('slow') as client:
        first = client.post('/api/analysis/submit',
                            json=make_payload('vid_main'))
        task_id = first.json()['task_id']

        # 首任务 running 后再提交第二个 → 第二个确定性停在 queued
        wait_for(client, task_id, 'running')
        task_id_2 = client.post('/api/analysis/submit',
                                json=make_payload('vid_second')).json()['task_id']
        assert client.get(f'/api/tasks/{task_id_2}').json()['status'] == 'queued'

        running_percents = []
        while True:
            task = client.get(f'/api/tasks/{task_id}').json()
            if task['status'] != 'running':
                break
            running_percents.append(task['percent'])
            time.sleep(0.02)

        final = wait_for(client, task_id, 'succeeded')
        assert final['result_path'] == 'outputs/vid_main/score_report.json'
        assert final['percent'] == 100
        assert final['error'] is None
        assert final['finished_at'] is not None
        assert running_percents == sorted(running_percents)      # 单调不减
        assert len(set(running_percents)) >= 2                   # 观察到递增

        final2 = wait_for(client, task_id_2, 'succeeded')
        assert final2['result_path'] == 'outputs/vid_second/score_report.json'


def test_task_not_found_404(make_client):
    with make_client('fast') as client:
        resp = client.get('/api/tasks/t_not_exist')
        assert resp.status_code == 404
        assert resp.json()['error']['code'] == 'task_not_found'


def test_unknown_route_unified_404(make_client):
    """不存在的路由也必须是统一错误体（覆盖 FastAPI 默认 {"detail":...}）。"""
    with make_client('fast') as client:
        resp = client.get('/api/no_such_route')
        assert resp.status_code == 404
        body = resp.json()
        assert body['error']['code'] == 'not_found'
        assert body['error']['message']
        assert 'detail' not in body


def test_failed_task_carries_error(make_client, stage_video, make_payload,
                                    wait_for):
    stage_video('vid_fail')
    with make_client('fail') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_fail')).json()['task_id']
        final = wait_for(client, task_id, 'failed')
        assert final['error'] == '模拟推理失败'
        assert final['finished_at'] is not None
        assert final['result_path'] == 'outputs/vid_fail/score_report.json'
        assert final['percent'] < 100                    # 失败不置 100


def test_tasks_list_and_queue_length(make_client, stage_video, make_payload,
                                      wait_for):
    stage_video('vid_a')
    stage_video('vid_b')
    with make_client('slow') as client:
        task_a = client.post('/api/analysis/submit',
                             json=make_payload('vid_a')).json()['task_id']
        wait_for(client, task_a, 'running')
        client.post('/api/analysis/submit', json=make_payload('vid_b'))

        body = client.get('/api/tasks').json()
        assert body['queue_length'] == 1                 # queued 数（§4.4）
        assert len(body['tasks']) == 2
        by_id = {t['task_id']: t for t in body['tasks']}
        assert by_id[task_a]['status'] == 'running'
        assert set(by_id[task_a]) == {
            'task_id', 'video_id', 'type', 'status', 'stage', 'percent',
            'detail', 'error', 'result_path', 'created_at', 'started_at',
            'finished_at'}
        other = [t for t in body['tasks'] if t['task_id'] != task_a][0]
        assert other['status'] == 'queued'


def test_health_ok_idle(make_client):
    with make_client('fast') as client:
        resp = client.get('/api/health')
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok', 'service_version': '0.1.0',
                               'busy': False}


def test_result_file_written(make_client, stage_video, make_payload,
                             wait_for, outputs_dir):
    stage_video('vid_out')
    with make_client('fast') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_out')).json()['task_id']
        wait_for(client, task_id, 'succeeded')
        assert (outputs_dir / 'vid_out' / 'score_report.json').is_file()


def test_iso_timestamps_parseable(make_client, stage_video, make_payload,
                                  wait_for):
    stage_video('vid_ts')
    stage_video('vid_ts2')
    with make_client('slow') as client:
        t1 = client.post('/api/analysis/submit',
                         json=make_payload('vid_ts')).json()['task_id']
        wait_for(client, t1, 'running')
        t2 = client.post('/api/analysis/submit',
                         json=make_payload('vid_ts2')).json()['task_id']
        queued = client.get(f'/api/tasks/{t2}').json()
        assert queued['started_at'] is None
        assert queued['finished_at'] is None

        final = wait_for(client, t1, 'succeeded')
        created = datetime.fromisoformat(final['created_at'])
        started = datetime.fromisoformat(final['started_at'])
        finished = datetime.fromisoformat(final['finished_at'])
        assert all(dt.tzinfo is not None for dt in (created, started, finished))
        assert created <= started <= finished
        wait_for(client, t2, 'succeeded')                # 收尾


def test_finished_tasks_fifo_retention(make_client, stage_video, make_payload,
                                       wait_for):
    """终态任务保留最近 50 条，FIFO 淘汰最旧（重启清空语义另见 §8.3）。"""
    total = 51
    for i in range(total):
        stage_video(f'vid_fifo_{i}')
    with make_client('fast') as client:
        first_task_id = None
        for i in range(total):
            resp = client.post('/api/analysis/submit',
                               json=make_payload(f'vid_fifo_{i}'))
            assert resp.status_code == 202
            task_id = resp.json()['task_id']
            if first_task_id is None:
                first_task_id = task_id
            wait_for(client, task_id, 'succeeded')

        body = client.get('/api/tasks').json()
        assert len(body['tasks']) == 50
        assert client.get(f'/api/tasks/{first_task_id}').status_code == 404


def test_watchdog_marks_stuck_task_failed(outputs_dir, make_payload):
    """running 且无进度超过 watchdog 超时 → failed（error=watchdog: 无进度超时）。"""

    class StuckRunner:
        def validate(self, payload, outputs_dir):
            pass

        def run(self, payload, outputs_dir, progress_cb, cancel_event, task_id):
            cancel_event.wait(30)         # 模拟卡死：不回调任何进度
            raise TaskCancelled('stuck')

    tm = TaskManager(watchdog_timeout=0.3)
    tm.start()
    try:
        task_id = tm.submit('vid_stuck', make_payload('vid_stuck'),
                            StuckRunner(), outputs_dir)
        deadline = time.monotonic() + 3.0
        snapshot = None
        while time.monotonic() < deadline:
            snapshot = tm.get(task_id)
            if snapshot['status'] == 'failed':
                break
            time.sleep(0.05)
        assert snapshot is not None and snapshot['status'] == 'failed'
        assert snapshot['error'] == 'watchdog: 无进度超时'
        assert snapshot['finished_at'] is not None
    finally:
        tm.shutdown()
