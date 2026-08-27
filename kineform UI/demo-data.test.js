const test = require('node:test');
const assert = require('node:assert/strict');
const { createDemoEvents, createDemoMotion, createDemoReport } = require('./demo-data.js');

test('demo motion has contract metadata, exact frame timestamps, and the full metric key set', () => {
  const motion = createDemoMotion();

  assert.equal(motion.schema_version, '1.0');
  assert.equal(motion.video_id, '2026-08-26_103000_test_running');
  assert.equal(motion.frame_count, motion.frames.length);
  assert.equal(motion.frames[80].frameIndex, 80);
  assert.equal(motion.frames[80].timestampMs, 2669.3);
  assert.equal(motion.frames[47].metrics.torso_lean_angle, null);
  assert.equal(Object.keys(motion.frames[0].metrics).length, 34);
  assert.ok(Object.hasOwn(motion.frames[0].metrics, 'left_knee_angvel'));
  assert.ok(Object.hasOwn(motion.frames[0].metrics, 'valid_ratio'));
});

test('demo events include suggested markers and optional gait summary', () => {
  const events = createDemoEvents();

  assert.equal(events.schema_version, '1.0');
  assert.ok(events.events.some((event) => event.type === 'right_touchdown'));
  assert.ok(events.events.every((event) => Number.isFinite(event.frame_index)));
  assert.ok(events.gait_summary.steps.length >= 6);
  assert.ok(events.gait_summary.fatigue_trend.delta);
});

test('demo report has the score_report summary shape', () => {
  const report = createDemoReport();

  assert.equal(report.schema_version, '1.0');
  assert.equal(report.summary.n_markers, 6);
  assert.equal(report.summary.gait.n_steps, 12);
  assert.ok(Array.isArray(report.summary.gait.reference_comparison));
  assert.ok(Array.isArray(report.summary.takeoff_steps));
});
