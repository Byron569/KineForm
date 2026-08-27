// 后端联调冒烟：listProjects → fetchMotion → fetchEvents → fetchAnnotations(404)
// → saveAnnotations(PUT) → 回读断言一致。用法：node smoke-backend.mjs [baseUrl]
// 依赖正在运行的 FastAPI 服务（KINEFORM_OUTPUTS_DIR 指向含假项目的临时目录）。
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { createApiClient, buildAnnotationsDocument } = require('./contract-adapter.js');

const BASE = process.argv[2] || 'http://127.0.0.1:8000';
const VIDEO_ID = 'smoke-20260826_test_project';

function fail(step, message) {
  console.error(`FAIL [${step}] ${message}`);
  process.exit(1);
}

function assert(condition, step, message) {
  if (!condition) fail(step, message);
  console.log(`ok   [${step}] ${message}`);
}

const client = createApiClient({ baseUrl: BASE, fetchImpl: globalThis.fetch });

// 1. listProjects 应包含假项目
const listed = await client.listProjects();
const entry = (listed.projects || []).find((project) => project.video_id === VIDEO_ID);
assert(Boolean(entry), 'listProjects', `projects 包含 ${VIDEO_ID}（共 ${listed.projects.length} 个）`);
assert(entry.frame_count === 2 && entry.has_events === true && entry.has_annotations === false,
  'listProjects', `元数据正确 frame_count=${entry.frame_count} has_events=${entry.has_events}`);

// 2. fetchMotion 原样返回
const motion = await client.fetchMotion(VIDEO_ID);
assert(motion.video_id === VIDEO_ID && motion.frame_count === 2 && motion.frames[1].timestampMs === 83.4,
  'fetchMotion', `motion.json 原样（fps=${motion.fps}, frames[1].timestampMs=${motion.frames[1].timestampMs}）`);

// 3. fetchEvents 原样返回
const events = await client.fetchEvents(VIDEO_ID);
assert(events.events.length === 1 && events.events[0].type === 'left_touchdown',
  'fetchEvents', `events.json 原样（${events.events.length} 个事件）`);

// 4. fetchAnnotations 空白起步 → 404 annotations_not_found
try {
  await client.fetchAnnotations(VIDEO_ID);
  fail('fetchAnnotations', '期望 404 annotations_not_found，实际 200');
} catch (error) {
  assert(error.api?.code === 'annotations_not_found' && error.api?.status === 404,
    'fetchAnnotations', '404 annotations_not_found（空白起步）');
}

// 5. saveAnnotations PUT 全量覆盖
const document = buildAnnotationsDocument({
  videoId: VIDEO_ID,
  fps: motion.fps,
  markers: [{
    id: 'm_smoke1', frameIndex: 1, timestampMs: 83.4, label: '冒烟标记',
    comment: 'smoke', createdAt: '2026-08-26T12:00:00Z', updatedAt: '2026-08-26T12:00:00Z',
  }],
});
const saved = await client.saveAnnotations(VIDEO_ID, document);
assert(saved.status === 'saved', 'saveAnnotations', `PUT 返回 ${JSON.stringify(saved)}`);

// 6. 回读断言一致
const reloaded = await client.fetchAnnotations(VIDEO_ID);
assert(reloaded.video_id === document.video_id && reloaded.fps === document.fps
  && reloaded.markers.length === 1 && reloaded.markers[0].id === 'm_smoke1'
  && reloaded.markers[0].frameIndex === 1 && reloaded.markers[0].timestampMs === 83.4,
  'roundtrip', '回读 annotations 与保存内容一致');

// 7. videoUrl / analysisUrl 字符串
assert(client.videoUrl(VIDEO_ID) === `${BASE}/api/projects/${VIDEO_ID}/video`
  && client.analysisUrl(VIDEO_ID) === `${BASE}/api/projects/${VIDEO_ID}/analysis`,
  'videoUrls', 'videoUrl/analysisUrl 拼接正确');

console.log('\nSMOKE PASS: 7/7 步骤全部通过');
