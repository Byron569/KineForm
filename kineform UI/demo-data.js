(function attachKineFormDemoData(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.KineFormDemoData = api;
})(typeof window !== 'undefined' ? window : globalThis, () => {
  const FPS = 29.97;
  const VIDEO_ID = '2026-08-26_103000_test_running';
  const METRIC_KEYS = [
    'left_knee_angle', 'right_knee_angle', 'left_hip_angle', 'right_hip_angle',
    'left_ankle_angle', 'right_ankle_angle', 'left_elbow_angle', 'right_elbow_angle',
    'left_knee_angvel', 'right_knee_angvel', 'left_hip_angvel', 'right_hip_angvel',
    'left_ankle_angvel', 'right_ankle_angvel', 'left_elbow_angvel', 'right_elbow_angvel',
    'torso_lean_angle', 'left_thigh_angle', 'right_thigh_angle', 'left_shank_angle',
    'right_shank_angle', 'left_shoulder_angle', 'right_shoulder_angle', 'pelvis_x',
    'pelvis_y', 'pelvis_speed_px_s', 'head_x', 'head_y', 'left_heel_x', 'left_heel_y',
    'right_heel_x', 'right_heel_y', 'pose_quality', 'valid_ratio',
  ];

  const round = (value, decimals = 2) => Number(value.toFixed(decimals));
  const timeAt = (frameIndex) => round((frameIndex * 1000) / FPS, 1);

  function buildMetrics(frameIndex) {
    const phase = frameIndex / 450;
    const swing = Math.sin(phase * Math.PI * 5.4);
    const fastSwing = Math.sin(phase * Math.PI * 11.2 + 0.45);
    const quality = Math.max(0.82, Math.min(0.985, 0.935 + Math.sin(phase * Math.PI * 4.1) * 0.018 + fastSwing * 0.006));
    const metrics = {
      left_knee_angle: round(137.5 + swing * 17.2 + fastSwing * 2.8),
      right_knee_angle: round(141.1 - swing * 15.8 + fastSwing * 2.2),
      left_hip_angle: round(168.5 + swing * 7.4),
      right_hip_angle: round(165.2 - swing * 6.8),
      left_ankle_angle: round(91.5 + swing * 9.8),
      right_ankle_angle: round(88.8 - swing * 8.5),
      left_elbow_angle: round(51 + fastSwing * 8.2),
      right_elbow_angle: round(47 - fastSwing * 7.6),
      left_knee_angvel: round(210 * Math.cos(phase * Math.PI * 5.4), 1),
      right_knee_angvel: round(-192 * Math.cos(phase * Math.PI * 5.4), 1),
      left_hip_angvel: round(86 * Math.cos(phase * Math.PI * 5.4), 1),
      right_hip_angvel: round(-82 * Math.cos(phase * Math.PI * 5.4), 1),
      left_ankle_angvel: round(124 * Math.cos(phase * Math.PI * 5.4), 1),
      right_ankle_angvel: round(-118 * Math.cos(phase * Math.PI * 5.4), 1),
      left_elbow_angvel: round(72 * Math.cos(phase * Math.PI * 11.2), 1),
      right_elbow_angvel: round(-68 * Math.cos(phase * Math.PI * 11.2), 1),
      torso_lean_angle: round(10.9 + swing * 5.4 + fastSwing * 0.8),
      left_thigh_angle: round(34.5 + swing * 10.5),
      right_thigh_angle: round(37.2 - swing * 9.4),
      left_shank_angle: round(7.8 + swing * 13.2),
      right_shank_angle: round(9.4 - swing * 12.7),
      left_shoulder_angle: round(18.2 + fastSwing * 7.4),
      right_shoulder_angle: round(20.5 - fastSwing * 6.9),
      pelvis_x: round(320 + frameIndex * 1.28),
      pelvis_y: round(372.4 - swing * 20.8 + fastSwing * 1.9),
      pelvis_speed_px_s: round(38.1 + fastSwing * 1.2, 1),
      head_x: round(388 + frameIndex * 1.28),
      head_y: round(116 - swing * 8.1),
      left_heel_x: round(302 + frameIndex * 1.28 - swing * 18),
      left_heel_y: round(386 - swing * 17),
      right_heel_x: round(518 + frameIndex * 1.28 + swing * 17),
      right_heel_y: round(385 + swing * 16),
      pose_quality: round(quality, 4),
      valid_ratio: round(Math.max(0.8, quality + 0.041), 4),
    };

    if (frameIndex % 47 === 0) metrics.torso_lean_angle = null;
    if (frameIndex === 80) {
      metrics.left_knee_angle = 142.13;
      metrics.right_knee_angle = 138.70;
      metrics.pelvis_y = 372.40;
      metrics.torso_lean_angle = 12.80;
      metrics.pose_quality = 0.9412;
      metrics.valid_ratio = 0.9821;
    }
    return metrics;
  }

  function createDemoMotion() {
    const frames = Array.from({ length: 450 }, (_, frameIndex) => ({
      frameIndex,
      timestampMs: timeAt(frameIndex),
      metrics: buildMetrics(frameIndex),
    }));
    return {
      schema_version: '1.0',
      video_id: VIDEO_ID,
      source_video: 'source_cfr.mp4',
      fps: FPS,
      frame_count: frames.length,
      width: 1920,
      height: 1080,
      created_at: '2026-08-26T10:30:00Z',
      frames,
    };
  }

  function makeEvent(type, frameIndex, label, value = null) {
    return {
      type,
      frame_index: frameIndex,
      timestamp_ms: timeAt(frameIndex),
      value,
      label,
    };
  }

  function stat(mean, std, min, max, count) {
    return { mean, std, min, max, count };
  }

  function createDemoEvents() {
    const events = [
      makeEvent('pelvis_highest', 105, '骨盆最高点', -1.2),
      makeEvent('right_touchdown', 118, '右脚触地', 42.8),
      makeEvent('left_toe_off', 132, '左脚离地', -36.5),
      makeEvent('left_touchdown', 160, '左脚触地', 39.1),
      makeEvent('right_toe_off', 174, '右脚离地', -34.2),
      makeEvent('right_touchdown', 198, '右脚触地', 41.5),
      makeEvent('left_toe_off', 212, '左脚离地', -35.6),
      makeEvent('torso_lean_peak', 248, '躯干倾角峰值', 17.4),
      makeEvent('left_touchdown', 276, '左脚触地', 38.3),
      makeEvent('right_toe_off', 290, '右脚离地', -33.9),
      makeEvent('right_touchdown', 314, '右脚触地', 40.2),
      makeEvent('left_toe_off', 330, '左脚离地', -36.1),
    ];

    const steps = Array.from({ length: 12 }, (_, index) => {
      const side = index % 2 === 0 ? 'right' : 'left';
      const tdFrame = 70 + index * 30;
      const toFrame = tdFrame + 14;
      return {
        side,
        td_frame: tdFrame,
        to_frame: toFrame,
        next_td_frame: index === 11 ? null : tdFrame + 30,
        contact_time_ms: round(118 + (index % 4) * 4.2, 1),
        flight_time_ms: index === 11 ? null : 214.1,
        stride_time_ms: index === 11 ? null : 1001.0,
        stance_ratio: index === 11 ? null : 0.2857,
        flight_support_ratio: index === 11 ? null : 1.81,
        stride_length_px: round(385 + index * 1.7, 1),
        stride_length_norm: round(2.18 + index * 0.006, 4),
        touchdown: {
          knee_angle: round(142 - index * 0.4, 1),
          hip_angle: round(164 + index * 0.3, 1),
          ankle_angle: round(89 + index * 0.2, 1),
          torso_lean_angle: round(11.8 + index * 0.22, 1),
          thigh_angle: round(35.2 + index * 0.4, 1),
          shank_angle: round(8.1 + index * 0.2, 1),
          shoulder_angle: round(18.4 + index * 0.15, 1),
          elbow_angle: round(49.2 + index * 0.2, 1),
          foot_pelvis_dist_px: round(41.3 + index * 0.7, 1),
          foot_pelvis_dist_norm: round(0.235 + index * 0.002, 4),
          foot_rel_vx_px_s: round(-14.1 + index * 0.6, 1),
        },
        midstance: { frame: tdFrame + 7, knee_angle: round(132.5 - index * 0.5, 1), hip_angle: 158.2, ankle_angle: 96.4, shoulder_angle: 21.2, elbow_angle: 53.8 },
        toe_off: { knee_angle: round(154 + index * 0.2, 1), hip_angle: 171.5, ankle_angle: 103.1, shoulder_angle: 24.5, elbow_angle: 45.3 },
        stance: { min_knee_angle: round(131.2 - index * 0.35, 1), knee_collapse_deg: round(10.8 + index * 0.25, 1), knee_rom_deg: 22.7, ankle_rom_deg: 14.6, hip_rom_deg: 18.3 },
        swing: { min_knee_angle: round(73.4 - index * 0.2, 1), max_thigh_angle: round(48.2 + index * 0.6, 1) },
      };
    });

    return {
      schema_version: '1.0',
      events,
      gait_summary: {
        left: {
          n_touchdowns: 6,
          n_toe_offs: 6,
          contact_time_ms: stat(121.4, 4.8, 114.2, 128.6, 6),
          flight_time_ms: stat(212.9, 7.1, 202.6, 222.8, 5),
          stride_time_ms: stat(1003.3, 11.7, 987.2, 1018.9, 5),
          stance_ratio: { ...stat(28.6, 0.9, 27.2, 29.7, 5), mean_frac: 0.286 },
        },
        right: {
          n_touchdowns: 6,
          n_toe_offs: 6,
          contact_time_ms: stat(119.8, 4.2, 113.9, 126.5, 6),
          flight_time_ms: stat(214.1, 6.5, 205.4, 222.1, 5),
          stride_time_ms: stat(1001.0, 10.4, 986.8, 1014.6, 5),
          stance_ratio: { ...stat(28.4, 0.8, 27.1, 29.4, 5), mean_frac: 0.284 },
        },
        step_time_ms: stat(350.9, 10.2, 333.4, 367.2, 11),
        cadence_spm: 171.4,
        body_scale: { body_height_px: 178.4, leg_length_px: 91.7, m_per_px: 0.0102, speed_px_s: 38.1, speed_mps: 0.39 },
        steps,
        reference_comparison: [{
          reference: 'sprint_max_v',
          source: 'Mattes 2021 短跑参考',
          sample: '精英短跑运动员',
          angle_definition: '项目角度定义与参考库对齐',
          disclaimer: '统计分层与 2D 投影误差仅供工程分析参考。',
          skipped_metrics: {},
          side_summary: {
            left: { 'touchdown.knee_angle': { mean_z: -0.42, band: 'common', n: 6 }, 'contact_time_ms': { mean_z: 0.86, band: 'common', n: 6 } },
            right: { 'touchdown.knee_angle': { mean_z: -0.18, band: 'common', n: 6 }, 'contact_time_ms': { mean_z: 1.32, band: 'deviated', n: 6 } },
          },
          global: { cadence_hz: { value: 2.857, ref_mean: 2.94, ref_sd: 0.12, z: -0.69, band: 'common' } },
        }],
        fatigue_trend: {
          n_steps: 12,
          split_at: 6,
          halves: { first: { contact_time_ms: 117.8, 'swing.min_knee_angle': 71.2 }, second: { contact_time_ms: 123.2, 'swing.min_knee_angle': 76.1 } },
          delta: { contact_time_ms: 5.4, 'swing.min_knee_angle': 4.9 },
          delta_pct: { contact_time_ms: 4.6, 'swing.min_knee_angle': 6.9 },
        },
        takeoff_steps: [{
          td_frame: 370,
          side: 'right',
          contact_time_ms: 188.4,
          contact_median_ms: 119.9,
          ratio: 1.571,
          confidence: 0.561,
          reason: '末步触地时间超过全部有效步中位数的 1.4 倍，识别为疑似起跳步。',
        }],
      },
    };
  }

  function createDemoReport() {
    return {
      schema_version: '1.0',
      task_id: 't_demo_20260826_103001',
      video_id: VIDEO_ID,
      created_at: '2026-08-26T10:30:03Z',
      markers: [
        { id: 'm-aB3xK9', frameIndex: 80, timestampMs: 2669.3, label: '起跳瞬间', comment: '右脚蹬离地面', metrics: { left_knee_angle: 142.13, right_knee_angle: 138.70, pose_quality: 0.9412 }, step: { side: 'right', td_frame: 70 }, event_context: [{ type: 'right_toe_off', frame_index: 81, timestamp_ms: 2702.7, delta_frames: 1 }] },
      ],
      summary: {
        n_markers: 6,
        gait: {
          n_steps: 12,
          cadence_spm: 171.4,
          contact_time_ms_mean: 120.6,
          reference_comparison: [{ reference: 'sprint_max_v', left: { 'touchdown.knee_angle': -0.42 }, right: { 'contact_time_ms': 1.32 } }],
        },
        fatigue_trend: { n_steps: 12, delta: { contact_time_ms: 5.4, 'swing.min_knee_angle': 4.9 } },
        takeoff_steps: [{ td_frame: 370, side: 'right', ratio: 1.571, confidence: 0.561, reason: '疑似起跳步' }],
      },
    };
  }

  return { createDemoEvents, createDemoMotion, createDemoReport, METRIC_KEYS };
});
