"""并发行为：容量核算 / 多线程提交 / 运行中并发轮询 / busy 标志。"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor


def test_threaded_submits_respect_capacity(make_client, stage_video,
                                           make_payload):
    """6 线程同时提交不同视频：恰好 2 个 202（1 运行 + 1 排队），其余 409。"""
    vids = [f'vid_c{i}' for i in range(6)]
    for vid in vids:
        stage_video(vid)
    with make_client('slow') as client:

        def submit(vid):
            return client.post('/api/analysis/submit', json=make_payload(vid))

        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(submit, vids))

        codes = sorted(r.status_code for r in responses)
        assert codes == [202, 202, 409, 409, 409, 409]
        for resp in responses:
            if resp.status_code == 409:
                assert resp.json()['error']['code'] == 'queue_full'

        # 收尾：取消两个活跃任务
        for task in client.get('/api/tasks').json()['tasks']:
            if task['status'] in ('queued', 'running', 'cancelling'):
                client.post(f"/api/tasks/{task['task_id']}/cancel")


def test_concurrent_polling_during_run(make_client, stage_video, make_payload,
                                       wait_for):
    """运行期间 3 线程并发轮询 health/tasks/详情：全部 200、percent 不回退。"""
    stage_video('vid_poll')
    with make_client('slow') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_poll')).json()['task_id']
        errors = []

        def poll(extra_urls):
            deadline = time.monotonic() + 0.5
            last_percent = -1
            while time.monotonic() < deadline:
                for url in extra_urls:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        errors.append((url, resp.status_code))
                        return
                task = client.get(f'/api/tasks/{task_id}').json()
                if task['percent'] < last_percent:
                    errors.append(('percent_regressed', task['percent']))
                    return
                last_percent = task['percent']

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(poll, ['/api/health']),
                pool.submit(poll, ['/api/tasks']),
                pool.submit(poll, []),
            ]
            for fut in futures:
                fut.result()

        assert errors == []
        wait_for(client, task_id, 'succeeded')


def test_health_busy_toggles(make_client, stage_video, make_payload,
                             wait_for):
    """运行期间 busy=true；完成后 busy=false（health 全程 200）。"""
    stage_video('vid_busy')
    with make_client('slow') as client:
        task_id = client.post('/api/analysis/submit',
                              json=make_payload('vid_busy')).json()['task_id']

        deadline = time.monotonic() + 2.0
        saw_busy = False
        while time.monotonic() < deadline:
            health = client.get('/api/health')
            assert health.status_code == 200
            if health.json()['busy']:
                saw_busy = True
                break
            time.sleep(0.02)
        assert saw_busy, '运行期间 health.busy 应为 true'

        wait_for(client, task_id, 'succeeded')
        assert client.get('/api/health').json()['busy'] is False
