const test = require('node:test');
const assert = require('node:assert/strict');
const {
  buildAnnotationsDocument,
  buildSubmitPayload,
  createApiClient,
  getFrameTimestamp,
  isVersionCompatible,
  mapApiError,
  normalizeMotion,
} = require('./contract-adapter.js');

const motionFixture = {
  schema_version: '1.0',
  video_id: 'runner-01',
  source_video: 'source_cfr.mp4',
  fps: 29.97,
  frame_count: 2,
  width: 1920,
  height: 1080,
  created_at: '2026-08-26T10:30:00Z',
  frames: [
    { frameIndex: 0, timestampMs: 0.1, metrics: { left_knee_angle: 100.12, pose_quality: 0.9 } },
    { frameIndex: 1, timestampMs: 33.4, metrics: { left_knee_angle: null, pose_quality: 0.91 } },
  ],
};

test('normalizes motion frames while preserving exact timestampMs and null metrics', () => {
  const motion = normalizeMotion(motionFixture);

  assert.equal(motion.frame_count, 2);
  assert.equal(motion.frames[0].timestampMs, 0.1);
  assert.equal(motion.frames[1].timestampMs, 33.4);
  assert.equal(motion.frames[1].metrics.left_knee_angle, null);
  assert.equal(getFrameTimestamp(motion, 1), 33.4);
});

test('builds the annotations.json envelope with project identity and marker timestamps', () => {
  const document = buildAnnotationsDocument({
    videoId: 'runner-01',
    fps: 29.97,
    markers: [{
      id: 'm_abc',
      frameIndex: 1,
      timestampMs: 33.4,
      label: '触地',
      comment: '右脚先着地',
      createdAt: '2026-08-26T10:31:00Z',
      updatedAt: '2026-08-26T10:31:01Z',
    }],
  });

  assert.deepEqual(document, {
    schema_version: '1.0',
    video_id: 'runner-01',
    fps: 29.97,
    markers: [{
      id: 'm_abc',
      frameIndex: 1,
      timestampMs: 33.4,
      label: '触地',
      comment: '右脚先着地',
      createdAt: '2026-08-26T10:31:00Z',
      updatedAt: '2026-08-26T10:31:01Z',
    }],
  });
});

test('builds submit payload from the source frame metrics instead of recalculating time', () => {
  const payload = buildSubmitPayload({
    motion: motionFixture,
    markers: [{ id: 'm_abc', frameIndex: 1, label: '触地', comment: '右脚先着地' }],
    motionSource: 'projects/runner-01/motion.json',
  });

  assert.equal(payload.video_id, 'runner-01');
  assert.equal(payload.fps, 29.97);
  assert.equal(payload.frame_count, 2);
  assert.equal(payload.markers[0].timestampMs, 33.4);
  assert.deepEqual(payload.markers[0].metrics, motionFixture.frames[1].metrics);
  assert.deepEqual(payload.motion, { source: 'projects/runner-01/motion.json' });
});

test('blocks major or minor service version mismatch but allows patch mismatch', () => {
  assert.deepEqual(isVersionCompatible('0.1.3', '0.1.8'), { compatible: true, patchMismatch: true });
  assert.deepEqual(isVersionCompatible('0.1.3', '0.2.0'), { compatible: false, patchMismatch: false });
  assert.deepEqual(isVersionCompatible('0.1.3', '1.1.3'), { compatible: false, patchMismatch: false });
});

test('maps stable API error codes to UI actions', () => {
  assert.equal(mapApiError(409, { error: { code: 'duplicate_video', message: '已有任务' }, task_id: 't_existing' }).code, 'duplicate_video');
  assert.equal(mapApiError(409, { error: { code: 'queue_full', message: '队列已满' } }).action, 'retry');
  assert.equal(mapApiError(404, { error: { code: 'task_not_found', message: '任务不存在' } }).action, 'restart');
  assert.equal(mapApiError(400, { error: { code: 'markers_empty', message: '不能为空' } }).action, 'add-marker');
});

test('buildAnnotationsDocument includes top-level project_name when provided', () => {
  const document = buildAnnotationsDocument({
    videoId: 'runner-01',
    fps: 29.97,
    projectName: '晨间冲刺训练',
    markers: [{ id: 'm_abc', frameIndex: 1, timestampMs: 33.4, label: '触地', comment: '', createdAt: '2026-08-26T10:31:00Z', updatedAt: '2026-08-26T10:31:01Z' }],
  });

  assert.equal(document.project_name, '晨间冲刺训练');
  const without = buildAnnotationsDocument({ videoId: 'runner-01', fps: 29.97, markers: [] });
  assert.ok(!('project_name' in without));
});

test('startAnalysis POSTs project_name when provided and omits it otherwise', async () => {
  const withNameFetch = createMockFetch([
    { url: `${BASE}/api/analysis/start`, status: 202, body: { status: 'accepted', task_id: 't_named', result_path: 'projects/pending' } },
  ]);
  const withNameClient = createApiClient({ baseUrl: BASE, fetchImpl: withNameFetch });
  await withNameClient.startAnalysis('D:\\videos\\run.mp4', '晨跑项目');

  const call = withNameFetch.calls[0];
  assert.deepEqual(JSON.parse(call.options.body), { video_path: 'D:\\videos\\run.mp4', project_name: '晨跑项目' });

  const bareFetch = createMockFetch([
    { url: `${BASE}/api/analysis/start`, status: 202, body: { status: 'accepted', task_id: 't_bare', result_path: 'projects/pending' } },
  ]);
  const bareClient = createApiClient({ baseUrl: BASE, fetchImpl: bareFetch });
  await bareClient.startAnalysis('D:\\videos\\run.mp4');

  assert.deepEqual(JSON.parse(bareFetch.calls[0].options.body), { video_path: 'D:\\videos\\run.mp4' });
});

test('fetchMeta returns project meta and surfaces 404 meta_not_found as stable error', async () => {
  const fetchImpl = createMockFetch([
    { url: `${BASE}/api/projects/p1/meta`, body: { source_video_name: '原始视频.MP4', project_name: '训练项目' } },
  ]);
  const client = createApiClient({ baseUrl: BASE, fetchImpl });

  const meta = await client.fetchMeta('p1');
  assert.equal(meta.source_video_name, '原始视频.MP4');
  assert.equal(meta.project_name, '训练项目');

  const missingFetch = createMockFetch([
    { url: `${BASE}/api/projects/p1/meta`, ok: false, status: 404, body: { error: { code: 'meta_not_found', message: '无 meta' } } },
  ]);
  const missingClient = createApiClient({ baseUrl: BASE, fetchImpl: missingFetch });
  await assert.rejects(missingClient.fetchMeta('p1'), (error) => error.api.code === 'meta_not_found');
});

function createMockFetch(routes) {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, options });
    const route = routes.find((entry) => (typeof entry.match === 'function' ? entry.match(url, options) : url === entry.url));
    if (!route) return { ok: false, status: 404, json: async () => ({}) };
    return {
      ok: route.ok ?? true,
      status: route.status ?? 200,
      json: async () => route.body,
    };
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

const BASE = 'http://127.0.0.1:8000';

test('client lists projects and fetches motion through /api/projects', async () => {
  const fetchImpl = createMockFetch([
    { url: `${BASE}/api/projects`, body: { projects: [{ video_id: 'p1', frame_count: 2, has_events: true, has_annotations: false }] } },
    { url: `${BASE}/api/projects/p1/motion`, body: motionFixture },
  ]);
  const client = createApiClient({ baseUrl: `${BASE}/`, fetchImpl });

  const listed = await client.listProjects();
  const motion = await client.fetchMotion('p1');

  assert.equal(listed.projects[0].video_id, 'p1');
  assert.equal(motion.video_id, 'runner-01');
  assert.equal(fetchImpl.calls[0].options.method, undefined);
});

test('fetchEvents and fetchAnnotations surface 404 resource codes as stable api errors', async () => {
  const fetchImpl = createMockFetch([
    { url: `${BASE}/api/projects/p1/events`, ok: false, status: 404, body: { error: { code: 'events_not_found', message: '无步态' } } },
    { url: `${BASE}/api/projects/p1/annotations`, ok: false, status: 404, body: { error: { code: 'annotations_not_found', message: '暂无标注' } } },
  ]);
  const client = createApiClient({ baseUrl: BASE, fetchImpl });

  await assert.rejects(client.fetchEvents('p1'), (error) => error.api.code === 'events_not_found' && error.api.status === 404);
  await assert.rejects(client.fetchAnnotations('p1'), (error) => error.api.code === 'annotations_not_found');
});

test('saveAnnotations PUTs the full document and reports video_id_mismatch', async () => {
  const fetchImpl = createMockFetch([
    { url: `${BASE}/api/projects/p1/annotations`, body: { status: 'saved', path: 'outputs/p1/annotations.json' } },
  ]);
  const client = createApiClient({ baseUrl: BASE, fetchImpl });
  const document = buildAnnotationsDocument({ videoId: 'p1', fps: 29.97, markers: [] });

  const saved = await client.saveAnnotations('p1', document);
  const call = fetchImpl.calls.at(-1);

  assert.equal(saved.status, 'saved');
  assert.equal(call.options.method, 'PUT');
  assert.equal(call.options.headers['Content-Type'], 'application/json');
  assert.equal(JSON.parse(call.options.body).video_id, 'p1');

  const mismatchFetch = createMockFetch([
    { url: `${BASE}/api/projects/p2/annotations`, ok: false, status: 400, body: { error: { code: 'video_id_mismatch', message: 'video_id 不一致' } } },
  ]);
  const mismatchClient = createApiClient({ baseUrl: BASE, fetchImpl: mismatchFetch });
  await assert.rejects(mismatchClient.saveAnnotations('p2', document), (error) => error.api.code === 'video_id_mismatch');
});

test('fetchTaskResult maps 409 task_not_finished and 404 report_not_found', async () => {
  const runningFetch = createMockFetch([
    { url: `${BASE}/api/tasks/t1/result`, ok: false, status: 409, body: { error: { code: 'task_not_finished', message: '任务未完成' } } },
  ]);
  const runningClient = createApiClient({ baseUrl: BASE, fetchImpl: runningFetch });
  await assert.rejects(runningClient.fetchTaskResult('t1'), (error) => error.api.code === 'task_not_finished');

  const missingFetch = createMockFetch([
    { url: `${BASE}/api/tasks/t2/result`, ok: false, status: 404, body: { error: { code: 'report_not_found', message: '报告不存在' } } },
  ]);
  const missingClient = createApiClient({ baseUrl: BASE, fetchImpl: missingFetch });
  await assert.rejects(missingClient.fetchTaskResult('t2'), (error) => error.api.code === 'report_not_found');
});

test('videoUrl and analysisUrl return ready-to-use URL strings', () => {
  const client = createApiClient({ baseUrl: `${BASE}/`, fetchImpl: async () => ({ ok: true, json: async () => ({}) }) });

  assert.equal(client.videoUrl('p1'), `${BASE}/api/projects/p1/video`);
  assert.equal(client.analysisUrl('p1'), `${BASE}/api/projects/p1/analysis`);
  assert.equal(client.videoUrl('a b'), `${BASE}/api/projects/a%20b/video`);
});

test('startAnalysis POSTs { video_path } and returns the 202 accepted envelope', async () => {
  const fetchImpl = createMockFetch([
    { url: `${BASE}/api/analysis/start`, status: 202, body: { status: 'accepted', task_id: 't_analyze_1', result_path: 'projects/pending' } },
  ]);
  const client = createApiClient({ baseUrl: BASE, fetchImpl });

  const response = await client.startAnalysis('D:\\videos\\run.mp4');

  assert.equal(response.status, 'accepted');
  assert.equal(response.task_id, 't_analyze_1');
  assert.equal(response.result_path, 'projects/pending');
  const call = fetchImpl.calls[0];
  assert.equal(call.options.method, 'POST');
  assert.equal(call.options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(call.options.body), { video_path: 'D:\\videos\\run.mp4' });
});

test('startAnalysis surfaces 409 duplicate_video with task_id for poll-existing', async () => {
  const fetchImpl = createMockFetch([
    { url: `${BASE}/api/analysis/start`, ok: false, status: 409, body: { error: { code: 'duplicate_video', message: '已有分析任务' }, task_id: 't_existing' } },
  ]);
  const client = createApiClient({ baseUrl: BASE, fetchImpl });

  await assert.rejects(client.startAnalysis('/videos/run.mp4'), (error) => {
    assert.equal(error.api.code, 'duplicate_video');
    assert.equal(error.api.status, 409);
    assert.equal(error.api.taskId, 't_existing');
    assert.equal(error.api.action, 'poll-existing');
    return true;
  });
});

test('startAnalysis maps 400 video_invalid / video_not_found to stable pick-video errors', async () => {
  const fetchImpl = createMockFetch([
    { url: `${BASE}/api/analysis/start`, ok: false, status: 400, body: { error: { code: 'video_invalid', message: '格式不支持' } } },
  ]);
  const client = createApiClient({ baseUrl: BASE, fetchImpl });

  await assert.rejects(client.startAnalysis('/videos/run.avi'), (error) => {
    assert.equal(error.api.code, 'video_invalid');
    assert.equal(error.api.status, 400);
    assert.equal(error.api.action, 'pick-video');
    return true;
  });
  assert.equal(mapApiError(400, { error: { code: 'video_not_found', message: '文件不存在' } }).action, 'pick-video');
});
