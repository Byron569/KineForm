(() => {
  'use strict';

  const CLIENT_VERSION = '0.1.0';
  const STORAGE_KEY = 'kineform-demo-annotations-v1';
  const DEMO_SOURCE = 'motion.json';
  const EVENT_LABELS = {
    pelvis_highest: '骨盆最高点',
    pelvis_lowest: '骨盆最低点',
    max_pelvis_height: '骨盆最高点',
    min_pelvis_height: '骨盆最低点',
    torso_lean_peak: '躯干倾角峰值',
    max_torso_lean: '躯干倾角峰值',
    min_left_knee_angle: '左膝最小角',
    min_right_knee_angle: '右膝最小角',
    max_joint_angular_velocity: '关节峰值角速度',
    left_touchdown: '左脚触地',
    right_touchdown: '右脚触地',
    left_toe_off: '左脚离地',
    right_toe_off: '右脚离地',
  };
  const METRIC_LABELS = {
    left_knee_angle: '左膝角度',
    right_knee_angle: '右膝角度',
    left_hip_angle: '左髋角度',
    right_hip_angle: '右髋角度',
    left_ankle_angle: '左踝角度',
    right_ankle_angle: '右踝角度',
    left_elbow_angle: '左肘角度',
    right_elbow_angle: '右肘角度',
    left_knee_angvel: '左膝角速度',
    right_knee_angvel: '右膝角速度',
    left_hip_angvel: '左髋角速度',
    right_hip_angvel: '右髋角速度',
    left_ankle_angvel: '左踝角速度',
    right_ankle_angvel: '右踝角速度',
    left_elbow_angvel: '左肘角速度',
    right_elbow_angvel: '右肘角速度',
    torso_lean_angle: '躯干倾角',
    left_thigh_angle: '左大腿角',
    right_thigh_angle: '右大腿角',
    left_shank_angle: '左小腿角',
    right_shank_angle: '右小腿角',
    left_shoulder_angle: '左肩角',
    right_shoulder_angle: '右肩角',
    pelvis_x: '骨盆 X',
    pelvis_y: '骨盆 Y',
    pelvis_speed_px_s: '骨盆速度',
    head_x: '头部 X',
    head_y: '头部 Y',
    left_heel_x: '左脚跟 X',
    left_heel_y: '左脚跟 Y',
    right_heel_x: '右脚跟 X',
    right_heel_y: '右脚跟 Y',
    pose_quality: '姿态质量',
    valid_ratio: '有效比例',
  };
  const PRIMARY_METRICS = new Set(['left_knee_angle', 'right_knee_angle', 'pelvis_y', 'torso_lean_angle', 'pose_quality']);
  const GAIT_LABELS = {
    cadence_spm: '步频(步/分)',
    cadence_hz: '步频(Hz)',
    step_time_ms: '步时',
    contact_time_ms: '触地时间',
    contact_time_ms_mean: '平均触地时间',
    flight_time_ms: '腾空时间',
    stride_time_ms: '步幅周期',
    stance_ratio: '支撑期占比',
    knee_collapse_deg: '膝塌陷角',
    knee_rom_deg: '膝关节活动度',
    ankle_rom_deg: '踝关节活动度',
    hip_rom_deg: '髋关节活动度',
    min_knee_angle: '最小膝角',
    max_thigh_angle: '大腿最大摆角',
    knee_angle: '膝角',
    hip_angle: '髋角',
    ankle_angle: '踝角',
    thigh_angle: '大腿角',
    shank_angle: '小腿角',
    shoulder_angle: '肩角',
    elbow_angle: '肘角',
    foot_pelvis_dist_px: '足-骨盆距离',
    foot_pelvis_dist_norm: '足-骨盆距离(标准化)',
    foot_rel_vx_px_s: '足相对水平速度',
    flight_support_ratio: '腾空支撑比',
    stride_length_px: '步幅长(像素)',
    stride_length_norm: '步幅长(标准化)',
    stride_length_m: '步幅长(米)',
    pelvis_vertical_range_px: '骨盆垂直起伏(像素)',
    pelvis_vertical_range_norm: '骨盆垂直起伏(标准化)',
    mean_z: '标准分均值',
    delta: '变化量',
    reference: '参考人群',
    n_steps: '步数',
    n_markers: '标记数',
    n_touchdowns: '触地次数',
    n_toe_offs: '离地次数',
    takeoff_steps: '起跳步',
    fatigue_trend: '疲劳趋势',
    touchdown: '触地',
    midstance: '支撑中期',
    toe_off: '离地',
    stance: '支撑期',
    swing: '摆动期',
    left: '左侧',
    right: '右侧',
    side: '侧别',
    side_summary: '分侧汇总',
    global: '整体指标',
    gait: '步态',
    value: '数值',
    frame: '帧',
    confidence: '置信度',
    ratio: '比值',
    count: '样本数',
    n: '样本数',
    std: '标准差',
    min: '最小值',
    max: '最大值',
    mean_frac: '占比(小数)',
    body_scale: '身体尺度',
    body_height_px: '身高(像素)',
    leg_length_px: '腿长(像素)',
    speed_px_s: '速度(像素/秒)',
    speed_mps: '水平速度',
    td_frame: '触地帧',
    to_frame: '离地帧',
    next_td_frame: '下次触地帧',
    z: '标准分',
    band: '分层',
    ref_mean: '参考均值',
    ref_sd: '参考标准差',
    ref_range: '参考范围',
    sprint_max_v: '短跑最大速度期',
    marathon_m: '男子马拉松参考',
    marathon_f: '女子马拉松参考',
  };
  const TASK_LABELS = {
    idle: '等待',
    queued: '排队中',
    running: '执行中',
    cancelling: '取消中',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消',
  };
  const ANALYSIS_ERROR_HINTS = {
    video_not_found: '所选视频文件不存在，请重新选择',
    video_invalid: '视频格式不支持，请选择 MP4 等常见格式',
  };

  // 历史标记英文标签 → 中文（旧版本采纳 events 建议时把 type 直接当 label 写入，
  // 如 'max torso lean'；这里按 EVENT_LABELS 反查渲染时翻译，不改动存储原文）
  const EN_LABEL_TO_ZH = (() => {
    const map = {};
    Object.entries(EVENT_LABELS).forEach(([type, zh]) => {
      map[type.replaceAll('_', ' ')] = zh;
    });
    return map;
  })();

  function displayMarkerLabel(label) {
    const text = String(label || '');
    if (EN_LABEL_TO_ZH[text]) return EN_LABEL_TO_ZH[text];
    return text;
  }

  const state = {
    clientVersion: CLIENT_VERSION,
    motion: null,
    eventsDocument: { events: [] },
    report: null,
    motionSource: DEMO_SOURCE,
    motionSha256: null,
    fps: 29.97,
    frameCount: 450,
    currentFrame: 80,
    playing: false,
    speed: 1,
    zoom: 100,
    stageZoom: 1,
    stagePan: { x: 0, y: 0 },
    timelineCenterTimer: null,
    audio: true,
    overlay: true,
    grid: false,
    activeTool: 'select',
    activeInspectorTab: 'metrics',
    selectedMarkerId: 'm-aB3xK9',
    multiSelect: {},
    projectName: null,
    sourceVideoName: null,
    series: { kneeL: true, kneeR: true, pelvis: true, quality: true },
    frames: [],
    markers: [],
    suggestions: [],
    history: [],
    future: [],
    playbackTimer: null,
    toastTimer: null,
    persistTimer: null,
    projects: [],
    currentVideoId: null,
    api: null,
    service: {
      mode: 'demo',
      state: 'demo',
      ready: true,
      blocked: false,
      version: null,
      message: '演示模式 · API 待连接',
    },
    task: {
      id: null,
      status: 'idle',
      stage: null,
      percent: null,
      detail: null,
      error: null,
      result_path: null,
      pollTimer: null,
      demoTimer: null,
    },
    analysis: {
      id: null,
      status: 'idle',
      stage: null,
      percent: null,
      detail: null,
      error: null,
      result_path: null,
      pollTimer: null,
    },
  };

  const videoLayer = {
    available: false,
    overlayAvailable: false,
    seeking: false,
    rafId: null,
    seekToken: 0,
  };

  const STAGE_ZOOM_STEPS = [1, 1.25, 1.5, 2, 2.5, 3, 4];

  let detachAnalyzeVideoMenu = null;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function pad(value, length = 2) {
    return String(value).padStart(length, '0');
  }

  function formatTimecode(timestampMs) {
    if (timestampMs === null || timestampMs === undefined || !Number.isFinite(Number(timestampMs))) return '—';
    const safeMs = Math.max(0, Math.round(Number(timestampMs)));
    const minutes = Math.floor(safeMs / 60000);
    const seconds = Math.floor((safeMs % 60000) / 1000);
    const milliseconds = safeMs % 1000;
    return `${pad(minutes)}:${pad(seconds)}.${pad(milliseconds, 3)}`;
  }

  function frameTime(frameIndex) {
    return KineFormContract.getFrameTimestamp(state.motion, clamp(frameIndex, 0, state.frameCount - 1));
  }

  function frameLabel(frameIndex) {
    return `F:${pad(frameIndex, 3)}`;
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function newMarkerId() {
    const random = window.crypto?.randomUUID?.().replaceAll('-', '').slice(0, 12)
      || `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
    return `m_${random}`;
  }

  function normalizeMarker(raw) {
    const frameIndex = clamp(Math.round(Number(raw?.frameIndex) || 0), 0, state.frameCount - 1);
    const now = new Date().toISOString();
    return {
      id: String(raw?.id || newMarkerId()),
      frameIndex,
      timestampMs: frameTime(frameIndex),
      label: String(raw?.label || '教练标注'),
      comment: String(raw?.comment || ''),
      createdAt: String(raw?.createdAt || now),
      updatedAt: String(raw?.updatedAt || raw?.createdAt || now),
      suggested: Boolean(raw?.suggested),
    };
  }

  function createSeedMarkers() {
    return [
      { id: 'm-aB3xK9', frameIndex: 80, label: '起跳瞬间', comment: '右脚蹬离地面', createdAt: '2026-08-26T10:30:00.000Z' },
      { id: 'm-cD7pL2', frameIndex: 92, label: '支撑期开始', comment: '身体重心进入前移阶段', createdAt: '2026-08-26T10:30:04.000Z' },
      { id: 'm-eF4qR8', frameIndex: 144, label: '躯干稳定', comment: '躯干倾角回到可控范围', createdAt: '2026-08-26T10:30:08.000Z' },
      { id: 'm-gH6sT1', frameIndex: 208, label: '左侧落点', comment: '左腿开始吸收冲击', createdAt: '2026-08-26T10:30:12.000Z' },
      { id: 'm-jK9uV5', frameIndex: 288, label: '最大伸展', comment: '双膝角度达到峰值', createdAt: '2026-08-26T10:30:16.000Z' },
      { id: 'm-xY2zN6', frameIndex: 366, label: '动作结束', comment: '回到稳定站姿', createdAt: '2026-08-26T10:30:20.000Z' },
    ].map(normalizeMarker);
  }

  function annotationStorageKey() {
    return `${STORAGE_KEY}:${state.motion?.video_id || 'demo'}`;
  }

  let demoProjectName = null;

  async function loadDemoMarkers() {
    const bridge = window.kineformBridge;
    if (bridge?.readProjectFile) {
      try {
        const raw = await bridge.readProjectFile('annotations.json');
        const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
        const markers = Array.isArray(parsed) ? parsed : parsed?.markers;
        if (!Array.isArray(parsed) && parsed?.project_name) demoProjectName = String(parsed.project_name);
        if (Array.isArray(markers)) return markers.map(normalizeMarker);
      } catch (error) {
        console.info('No project annotations.json found; using demo markers.', error);
      }
    }
    try {
      const stored = localStorage.getItem(annotationStorageKey()) || localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        const markers = Array.isArray(parsed) ? parsed : parsed?.markers;
        if (!Array.isArray(parsed) && parsed?.project_name) demoProjectName = String(parsed.project_name);
        if (Array.isArray(markers) && markers.length) return markers.map(normalizeMarker);
      }
    } catch (error) {
      console.warn('Unable to load local annotations.', error);
    }
    return createSeedMarkers();
  }

  async function persistMarkers() {
    const document = KineFormContract.buildAnnotationsDocument({
      videoId: state.motion.video_id,
      fps: state.fps,
      markers: state.markers,
      projectName: state.projectName,
    });
    if (state.service.mode === 'live' && state.api) {
      try {
        await state.api.saveAnnotations(state.motion.video_id, document);
        markSaved();
        return true;
      } catch (error) {
        const apiError = handleApiError(error);
        markDirty();
        showToast(`标注保存失败：${apiError.message}`, true);
        return false;
      }
    }
    try {
      localStorage.setItem(annotationStorageKey(), JSON.stringify(document));
      markSaved();
      return true;
    } catch (error) {
      console.warn('Unable to persist browser annotations.', error);
      return false;
    }
  }

  function schedulePersistMarkers() {
    if (state.service.mode === 'live' && state.api) {
      window.clearTimeout(state.persistTimer);
      state.persistTimer = window.setTimeout(() => { void persistMarkers(); }, 500);
      return;
    }
    void persistMarkers();
  }

  function persistMarkersNow() {
    window.clearTimeout(state.persistTimer);
    state.persistTimer = null;
    return persistMarkers();
  }

  function selectedMarker() {
    return state.markers.find((marker) => marker.id === state.selectedMarkerId) || null;
  }

  function markDirty() {
    const saveState = $('#saveState');
    const statusDot = $('.topbar .status-dot');
    if (saveState) saveState.textContent = '有未保存更改';
    if (statusDot) statusDot.style.background = 'var(--yellow)';
  }

  function markSaved() {
    const saveState = $('#saveState');
    const statusDot = $('.topbar .status-dot');
    if (saveState) saveState.textContent = '已保存 · 刚刚';
    if (statusDot) statusDot.style.background = 'var(--green)';
  }

  function snapshotMarkers() {
    return clone(state.markers);
  }

  function commitMarkerMutation(mutator) {
    state.history.push(snapshotMarkers());
    state.future = [];
    mutator();
    state.markers = state.markers.map(normalizeMarker);
    schedulePersistMarkers();
    markDirty();
    render();
  }

  function undoMarkers() {
    if (!state.history.length) {
      showToast('没有可撤销的标注操作');
      return;
    }
    state.future.push(snapshotMarkers());
    state.markers = state.history.pop().map(normalizeMarker);
    if (!selectedMarker()) state.selectedMarkerId = state.markers.at(-1)?.id || null;
    schedulePersistMarkers();
    markDirty();
    render();
    showToast('已撤销上一笔标注');
  }

  function redoMarkers() {
    if (!state.future.length) {
      showToast('没有可重做的标注操作');
      return;
    }
    state.history.push(snapshotMarkers());
    state.markers = state.future.pop().map(normalizeMarker);
    if (!selectedMarker()) state.selectedMarkerId = state.markers.at(-1)?.id || null;
    schedulePersistMarkers();
    markDirty();
    render();
    showToast('已重做标注操作');
  }

  function stageVideo() {
    return $('#stageVideo');
  }

  function overlayVideo() {
    return $('#analysisVideo');
  }

  // live 双层视频：base=source_cfr.mp4 永远显示，overlay=analysis.mp4 由骨架叠加开关控制
  function applyVideoSource() {
    const video = stageVideo();
    const overlay = overlayVideo();
    if (!video) return;
    if (state.service.mode === 'live' && state.api && state.motion) {
      videoLayer.available = true;
      video.classList.remove('hidden');
      const baseSrc = state.api.videoUrl(state.motion.video_id);
      if (baseSrc && video.getAttribute('src') !== baseSrc) video.src = baseSrc;
      if (overlay) {
        const overlaySrc = state.api.analysisUrl(state.motion.video_id);
        if (overlaySrc) {
          videoLayer.overlayAvailable = true;
          overlay.muted = true;
          if (overlay.getAttribute('src') !== overlaySrc) overlay.src = overlaySrc;
        } else {
          videoLayer.overlayAvailable = false;
        }
      }
    } else {
      // demo 分支：video 隐藏，假骨架 poseCanvas 由 renderOverlayVisual 打理
      videoLayer.available = false;
      videoLayer.overlayAvailable = false;
      video.classList.add('hidden');
      if (overlay) overlay.classList.add('hidden');
      video.removeAttribute('src');
      overlay?.removeAttribute('src');
    }
  }

  // 骨架叠加语义：demo → 假骨架 poseCanvas；live → analysis.mp4 叠加层显隐
  function renderOverlayVisual() {
    const demoMode = state.service.mode === 'demo';
    const poseCanvas = $('#poseCanvas');
    if (poseCanvas) poseCanvas.classList.toggle('hidden', !(demoMode && state.overlay));
    const overlay = overlayVideo();
    if (!overlay) return;
    const showOverlay = state.overlay && videoLayer.overlayAvailable;
    overlay.classList.toggle('is-overlay-off', !showOverlay);
  }

  function seekVideoToFrame(frameIndex) {
    const timestampMs = state.frames[frameIndex]?.timestampMs;
    if (!videoLayer.available || !Number.isFinite(Number(timestampMs))) return;
    const seconds = Number(timestampMs) / 1000;
    void seekBothSynchronized(seconds);
  }

  function waitForVideoEvent(video, eventName, timeout = 1500) {
    return Promise.race([
      new Promise((resolve) => video.addEventListener(eventName, resolve, { once: true })),
      new Promise((resolve) => window.setTimeout(resolve, timeout)),
    ]);
  }

  // 双层同步定位：token 防止连续 seek 交错；overlay 比 base 短 1 帧（如 125 vs 124）→
  // 钳到 overlay 时长 - 0.04s，避免 seek 超界
  async function seekBothSynchronized(seconds) {
    const video = stageVideo();
    const overlay = overlayVideo();
    if (!video) return;
    const token = ++videoLayer.seekToken;
    videoLayer.seeking = true;
    if (video.readyState >= 1) video.currentTime = Number(seconds);
    if (overlay && videoLayer.overlayAvailable && overlay.readyState >= 1) {
      const duration = Number.isFinite(overlay.duration) ? overlay.duration : 0;
      overlay.currentTime = Math.min(Number(seconds), Math.max(0, duration - 0.04));
    }
    await waitForVideoEvent(video, 'seeked', 1500);
    if (token !== videoLayer.seekToken) return;
    videoLayer.seeking = false;
    renderFrameState();
  }

  function setCurrentFrame(nextFrame) {
    state.currentFrame = clamp(Math.round(nextFrame), 0, state.frameCount - 1);
    seekVideoToFrame(state.currentFrame);
    renderFrameState();
  }

  function stepFrame(delta) {
    setCurrentFrame(state.currentFrame + delta);
  }

  function findFrameIndexByTime(timeMs) {
    const frames = state.frames;
    if (!frames.length) return 0;
    let low = 0;
    let high = frames.length - 1;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (Number(frames[mid].timestampMs) < timeMs) low = mid + 1;
      else high = mid;
    }
    if (low > 0) {
      const previous = Number(frames[low - 1].timestampMs);
      const current = Number(frames[low].timestampMs);
      if (Math.abs(previous - timeMs) <= Math.abs(current - timeMs)) return low - 1;
    }
    return low;
  }

  function stopVideoFrameSync() {
    if (videoLayer.rafId) window.cancelAnimationFrame(videoLayer.rafId);
    videoLayer.rafId = null;
  }

  function startVideoFrameSync() {
    stopVideoFrameSync();
    const tick = () => {
      const video = stageVideo();
      if (!state.playing || !video) return;
      if (!videoLayer.seeking) {
        const index = findFrameIndexByTime(video.currentTime * 1000);
        if (index !== state.currentFrame) {
          state.currentFrame = clamp(index, 0, state.frameCount - 1);
          renderFrameState();
        }
        if (state.currentFrame >= state.frameCount - 1) {
          stopPlayback();
          return;
        }
      }
      videoLayer.rafId = window.requestAnimationFrame(tick);
    };
    videoLayer.rafId = window.requestAnimationFrame(tick);
  }

  function stopPlayback() {
    if (state.playbackTimer) window.clearInterval(state.playbackTimer);
    state.playbackTimer = null;
    stopVideoFrameSync();
    if (videoLayer.available) {
      const video = stageVideo();
      if (video && !video.paused) video.pause();
      const overlay = overlayVideo();
      if (videoLayer.overlayAvailable && overlay && !overlay.paused) overlay.pause();
    }
    state.playing = false;
    renderTransportState();
  }

  function startIntervalPlayback() {
    state.playbackTimer = window.setInterval(() => {
      if (state.currentFrame >= state.frameCount - 1) {
        stopPlayback();
        return;
      }
      setCurrentFrame(state.currentFrame + 1);
    }, Math.max(16, 1000 / (state.fps * state.speed)));
  }

  function togglePlayback() {
    if (state.playing) {
      stopPlayback();
      return;
    }
    if (!state.frames.length) {
      showToast('当前没有可播放的项目数据', true);
      return;
    }
    if (state.currentFrame >= state.frameCount - 1) state.currentFrame = 0;
    state.playing = true;
    renderTransportState();
    if (videoLayer.available) {
      const video = stageVideo();
      const overlay = overlayVideo();
      seekVideoToFrame(state.currentFrame);
      if (video) {
        video.playbackRate = state.speed;
        video.muted = !state.audio;
        video.play().then(() => {
          if (videoLayer.overlayAvailable && overlay) {
            overlay.playbackRate = state.speed;
            overlay.muted = true; // 叠加层永远静音
            overlay.play().catch(() => {});
          }
          startVideoFrameSync();
        }).catch(() => {
          showToast('视频播放失败，已切换为示意播放', true);
          videoLayer.available = false;
          videoLayer.overlayAvailable = false;
          video.classList.add('hidden');
          overlay?.classList.add('hidden');
          stopPlayback();
          state.playing = true;
          renderTransportState();
          startIntervalPlayback();
        });
      }
      return;
    }
    startIntervalPlayback();
  }

  function addMarker(frameIndex = state.currentFrame, options = {}) {
    const safeFrame = clamp(Math.round(frameIndex), 0, state.frameCount - 1);
    const existing = state.markers.find((marker) => marker.frameIndex === safeFrame);
    if (existing && !options.force) {
      state.selectedMarkerId = existing.id;
      state.activeInspectorTab = 'markers';
      render();
      showToast(`${frameLabel(safeFrame)} 已有标记，已选中`);
      return existing;
    }

    let created;
    commitMarkerMutation(() => {
      const now = new Date().toISOString();
      created = {
        id: newMarkerId(),
        frameIndex: safeFrame,
        timestampMs: frameTime(safeFrame),
        label: options.label || '教练标注',
        comment: options.comment || '',
        createdAt: now,
        updatedAt: now,
        suggested: Boolean(options.suggested),
      };
      state.markers.push(created);
      state.selectedMarkerId = created.id;
      state.activeInspectorTab = 'markers';
    });
    showToast(`${frameLabel(safeFrame)} 已添加标记`);
    return created;
  }

  function deleteSelectedMarker() {
    const marker = selectedMarker();
    if (!marker) {
      showToast('请先选择一个标记', true);
      return;
    }
    commitMarkerMutation(() => {
      state.markers = state.markers.filter((item) => item.id !== marker.id);
      state.selectedMarkerId = state.markers.at(-1)?.id || null;
    });
    showToast('标记已删除，可使用撤销恢复');
  }

  function normalizeSuggestion(event) {
    const frameIndex = Number(event?.frame_index ?? event?.frameIndex);
    if (!Number.isFinite(frameIndex)) return null;
    const type = String(event?.type || 'event');
    const label = String(event?.label || EVENT_LABELS[type] || type.replaceAll('_', ' '));
    return {
      frameIndex: clamp(Math.round(frameIndex), 0, state.frameCount - 1),
      type,
      label,
      comment: `来自 events.json：${label}`,
      value: event?.value ?? null,
    };
  }

  function buildSuggestedEvents(eventsDocument) {
    return (eventsDocument?.events || []).map(normalizeSuggestion).filter(Boolean);
  }

  function adoptSuggestion(frameIndex) {
    const suggestion = state.suggestions.find((item) => item.frameIndex === Number(frameIndex));
    if (!suggestion) return;
    const existing = state.markers.find((marker) => marker.frameIndex === suggestion.frameIndex);
    if (existing) {
      state.selectedMarkerId = existing.id;
      state.activeInspectorTab = 'markers';
      render();
      showToast(`${frameLabel(suggestion.frameIndex)} 已经被标记`);
      return;
    }
    addMarker(suggestion.frameIndex, { label: suggestion.label, comment: suggestion.comment, suggested: true });
    showToast(`已采纳建议：${suggestion.label}`);
  }

  function updateSelectedMarker(field, value) {
    const marker = selectedMarker();
    if (!marker) return;
    marker[field] = value;
    marker.updatedAt = new Date().toISOString();
    schedulePersistMarkers();
    markDirty();
    renderMarkerList();
  }

  function selectMarker(markerId) {
    const marker = state.markers.find((item) => item.id === markerId);
    if (!marker) return;
    state.selectedMarkerId = marker.id;
    state.activeInspectorTab = 'markers';
    setCurrentFrame(marker.frameIndex);
    render();
  }

  function toggleSeries(series) {
    state.series[series] = !state.series[series];
    renderChart();
  }

  function setSpeed(speed) {
    state.speed = Number(speed);
    $('#speedMenu')?.classList.remove('is-open');
    renderTransportState();
    if (videoLayer.available) {
      const video = stageVideo();
      if (video) video.playbackRate = state.speed;
      const overlay = overlayVideo();
      if (videoLayer.overlayAvailable && overlay) overlay.playbackRate = state.speed;
    } else if (state.playing) {
      stopPlayback();
      togglePlayback();
    }
    showToast(`播放速度 ${state.speed.toFixed(2).replace(/0$/, '')}×`);
  }

  function scheduleTimelineCenter() {
    window.clearTimeout(state.timelineCenterTimer);
    state.timelineCenterTimer = window.setTimeout(() => {
      window.requestAnimationFrame(() => {
        const container = $('#timelineScroll');
        const playhead = $('#trackPlayhead');
        if (!container || !playhead) return;
        const playheadLeft = playhead.getBoundingClientRect().left - container.getBoundingClientRect().left + container.scrollLeft;
        const maxScroll = Math.max(0, container.scrollWidth - container.clientWidth);
        container.scrollTo({ left: clamp(playheadLeft - container.clientWidth / 2, 0, maxScroll) });
      });
    }, 120);
  }

  function zoomTimeline(delta) {
    // 下限 100：轨道宽度规则 max(100%, zoom) 决定 50% 与 100% 视觉相同，
    // 缩小无意义且读数失真（2026-08-27 用户反馈轮修正）
    state.zoom = clamp(state.zoom + delta, 100, 200);
    $('#timelineScroll')?.style.setProperty('--timeline-zoom', `${state.zoom}%`);
    renderTransportState();
    scheduleTimelineCenter();
  }

  function applyStageTransform() {
    const wrap = $('#stageZoomWrap');
    if (!wrap) return;
    const maxX = Math.max(0, ((state.stageZoom - 1) * wrap.offsetWidth) / 2);
    const maxY = Math.max(0, ((state.stageZoom - 1) * wrap.offsetHeight) / 2);
    state.stagePan = { x: clamp(state.stagePan.x, -maxX, maxX), y: clamp(state.stagePan.y, -maxY, maxY) };
    wrap.style.transform = `translate(${state.stagePan.x}px, ${state.stagePan.y}px) scale(${state.stageZoom})`;
    wrap.classList.toggle('is-zoomed', state.stageZoom > 1);
  }

  function setStageZoom(zoom) {
    const next = STAGE_ZOOM_STEPS.includes(zoom) ? zoom : 1;
    state.stageZoom = next;
    if (next === 1) state.stagePan = { x: 0, y: 0 };
    applyStageTransform();
    const readout = $('#stageZoomReadout');
    if (readout) readout.textContent = `${Math.round(next * 100)}%`;
  }

  function stepStageZoom(direction) {
    const index = STAGE_ZOOM_STEPS.indexOf(state.stageZoom);
    const nextIndex = clamp(index + direction, 0, STAGE_ZOOM_STEPS.length - 1);
    setStageZoom(STAGE_ZOOM_STEPS[nextIndex]);
  }

  function bindStageZoomControls() {
    const wrap = $('#stageZoomWrap');
    const stage = $('#viewerStage');
    if (!wrap || !stage) return;
    let pan = null;
    let panSuppressClick = false;
    wrap.addEventListener('pointerdown', (event) => {
      if (state.stageZoom <= 1) return;
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      pan = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: state.stagePan.x,
        originY: state.stagePan.y,
        moved: false,
      };
      wrap.setPointerCapture?.(event.pointerId);
    });
    wrap.addEventListener('pointermove', (event) => {
      if (!pan || event.pointerId !== pan.pointerId) return;
      const dx = event.clientX - pan.startX;
      const dy = event.clientY - pan.startY;
      if (!pan.moved && Math.hypot(dx, dy) < 4) return;
      pan.moved = true;
      wrap.classList.add('is-panning');
      state.stagePan = { x: pan.originX + dx, y: pan.originY + dy };
      applyStageTransform();
    });
    const endPan = (event) => {
      if (!pan || event.pointerId !== pan.pointerId) return;
      if (pan.moved) {
        panSuppressClick = true;
        window.setTimeout(() => { panSuppressClick = false; }, 0);
      }
      wrap.classList.remove('is-panning');
      pan = null;
    };
    wrap.addEventListener('pointerup', endPan);
    wrap.addEventListener('pointercancel', endPan);
    wrap.addEventListener('click', (event) => {
      if (!panSuppressClick) return;
      panSuppressClick = false;
      event.stopPropagation();
    }, true);
    stage.addEventListener('dblclick', (event) => {
      if (event.target.closest('.stage-zoom-controls')) return;
      setStageZoom(1);
    });
  }

  function showToast(message, isError = false) {
    const toast = $('#toast');
    if (!toast) return;
    window.clearTimeout(state.toastTimer);
    toast.textContent = message;
    toast.classList.toggle('is-error', isError);
    toast.classList.add('is-visible');
    state.toastTimer = window.setTimeout(() => toast.classList.remove('is-visible'), 2600);
  }

  // ---- 通用模态框（命名 / 确认 / 帮助）----
  function closeModal() {
    const root = $('#modalRoot');
    if (!root) return;
    root.classList.add('hidden');
    root.setAttribute('aria-hidden', 'true');
    root.innerHTML = '';
  }

  function setModalContent(html) {
    const root = $('#modalRoot');
    if (!root) return null;
    root.innerHTML = html;
    root.classList.remove('hidden');
    root.setAttribute('aria-hidden', 'false');
    const backdrop = root.querySelector('.modal-backdrop');
    if (backdrop) backdrop.addEventListener('click', closeModal);
    return root;
  }

  function promptModal({ title, label = '', value = '', placeholder = '', confirmText = '确定', cancelText = '取消' }) {
    return new Promise((resolve) => {
      const root = setModalContent(`
        <div class="modal-backdrop"></div>
        <div class="modal-card" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
          <div class="modal-head"><strong>${escapeHtml(title)}</strong><button class="modal-close" data-modal-close aria-label="关闭">×</button></div>
          <div class="modal-body"><label class="form-field"><span>${escapeHtml(label)}</span><input id="modalInput" value="${escapeHtml(value)}" placeholder="${escapeHtml(placeholder)}" /></label></div>
          <div class="modal-foot">
            <button type="button" class="topbar-button quiet" data-modal-cancel>${escapeHtml(cancelText)}</button>
            <button type="button" class="topbar-button primary" data-modal-confirm>${escapeHtml(confirmText)}</button>
          </div>
        </div>`);
      if (!root) return resolve(null);
      const input = $('#modalInput', root);
      if (input) {
        input.focus();
        input.select();
      }
      const finish = (v) => { closeModal(); resolve(v); };
      root.querySelector('[data-modal-confirm]').addEventListener('click', () => finish(input?.value.trim() ?? ''));
      root.querySelector('[data-modal-cancel]').addEventListener('click', () => finish(null));
      root.querySelector('[data-modal-close]').addEventListener('click', () => finish(null));
      input?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') finish(input.value.trim());
        if (event.key === 'Escape') finish(null);
      });
    });
  }

  function confirmModal({ title, message, confirmText = '确定', cancelText = '取消', dangerous = false }) {
    return new Promise((resolve) => {
      const root = setModalContent(`
        <div class="modal-backdrop"></div>
        <div class="modal-card" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
          <div class="modal-head"><strong>${escapeHtml(title)}</strong><button class="modal-close" data-modal-close aria-label="关闭">×</button></div>
          <div class="modal-body">${escapeHtml(message)}</div>
          <div class="modal-foot">
            <button type="button" class="topbar-button quiet" data-modal-cancel>${escapeHtml(cancelText)}</button>
            <button type="button" class="topbar-button primary ${dangerous ? 'danger-button' : ''}" data-modal-confirm>${escapeHtml(confirmText)}</button>
          </div>
        </div>`);
      if (!root) return resolve(false);
      const finish = (v) => { closeModal(); resolve(v); };
      root.querySelector('[data-modal-confirm]').addEventListener('click', () => finish(true));
      root.querySelector('[data-modal-cancel]').addEventListener('click', () => finish(false));
      root.querySelector('[data-modal-close]').addEventListener('click', () => finish(false));
    });
  }

  function infoModal({ title, html, closeText = '知道了' }) {
    const root = setModalContent(`
      <div class="modal-backdrop"></div>
      <div class="modal-card modal-info" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <div class="modal-head"><strong>${escapeHtml(title)}</strong><button class="modal-close" data-modal-close aria-label="关闭">×</button></div>
        <div class="modal-body">${html}</div>
        <div class="modal-foot"><button type="button" class="topbar-button primary" data-modal-confirm>${escapeHtml(closeText)}</button></div>
      </div>`);
    if (!root) return;
    root.querySelector('[data-modal-confirm]').addEventListener('click', closeModal);
    root.querySelector('[data-modal-close]').addEventListener('click', closeModal);
  }

  function infoChartHelp() {
    infoModal({
      title: '怎么看这些时序曲线',
      html: `
        <p><strong>左膝（蓝）/ 右膝（红）</strong>——左右膝关节各自的屈伸角度：曲线波谷约在支撑期（屈膝缓冲），波峰约在摆动后期（蹬伸）。峰值落差反映膝关节活动幅度；两条曲线应交替起伏（左右腿相位相反），若一侧持续偏低或波谷明显更深，提示左右不对称或单侧代偿。</p>
        <p><strong>骨盆 Y（青）</strong>——骨盆的高度起伏，近似身体重心垂直节奏：跑步中应呈规律小幅上下，幅度过大或节奏不齐常提示躯干上下颠簸过多。</p>
        <p><strong>质量（黄）</strong>——关键点检测置信度（0.8–1.0）：越高越可信，曲线骤降段表示该帧关键点检出差，读那附近的膝/骨盆数值时需谨慎。</p>
        <p>曲线上的 <code>null / 无数据</code> 表示该帧某指标未检出（如关节被遮挡），属正常现象，分段看有效区间即可。点击图例可单独隐藏某条曲线。</p>`,
    });
  }

  function infoZscoreHelp() {
    infoModal({
      title: '参考对比是怎么算的、怎么看',
      html: `
        <p><strong>数据来源</strong>：从步相事件（触地 / 离地 / 摆动）提取各步的时序参数（如触地膝角、触地时长），再与内置精英参考样本做比较。每个指标算出一个标准分 <b>z = (实测 − 参考均值) / 参考标准差</b>。</p>
        <div class="z-band-item"><span class="band-pill">z ≤ 1</span><span>常见范围：与参考人群几乎一致，属正常表现。</span></div>
        <div class="z-band-item"><span class="band-pill deviated">1 &lt; z ≤ 2</span><span>偏离：与参考存在可见差异，建议关注。</span></div>
        <div class="z-band-item"><span class="band-pill outlier">z &gt; 2</span><span>异常：明显超出常见范围，需重点评估。</span></div>
        <p>注意：这是工程统计分层（±1 / ±2 标准差），非医学诊断；参考样本是特定人群（如精英短跑），仅用于相近条件下的横向比较。黄 / 红分别对应“偏离”与“异常”两档。</p>`,
    });
  }

  function metricMeta(key) {
    if (key.includes('angvel')) return { unit: '°/s', decimals: 1 };
    if (key.includes('angle')) return { unit: '°', decimals: 2 };
    if (key === 'pose_quality' || key === 'valid_ratio') return { unit: '', decimals: 4 };
    if (key.includes('speed')) return { unit: 'px/s', decimals: 1 };
    return { unit: 'px', decimals: 2 };
  }

  function metricValue(key, value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
    const meta = metricMeta(key);
    return `${Number(value).toFixed(meta.decimals)}${meta.unit}`;
  }

  function renderProjectMeta() {
    if (!state.motion) return;
    const title = $('#toolbarTitle');
    const name = state.projectName || '';
    const vid = state.currentVideoId || '';
    if (title) title.textContent = name && name !== vid ? `${name} · ${vid}` : (vid || name);
    $('#videoSourceLabel').textContent = state.sourceVideoName || state.motion.source_video;
    $('#videoDimensions').textContent = `${state.motion.width}×${state.motion.height}`;
    $('#fpsLabel').textContent = `${state.motion.fps.toFixed(2)} FPS`;
    $('#timeDuration').textContent = formatTimecode(frameTime(state.frameCount - 1));
    $('#dataStatusText').textContent = state.service.mode === 'demo' ? '演示 motion.json 已加载' : '分析数据已加载';
  }

  function renderFrameState() {
    const frame = state.frames[state.currentFrame];
    if (!frame) return;
    const timecode = formatTimecode(frame.timestampMs);
    const label = frameLabel(frame.frameIndex);
    const percentage = state.frameCount > 1 ? (state.currentFrame / (state.frameCount - 1)) * 100 : 0;
    const chartX = state.frameCount > 1 ? (state.currentFrame / (state.frameCount - 1)) * 900 : 0;

    $('#stageFrameLabel').textContent = `${label} · ${timecode}`;
    $('#frameChip').textContent = label;
    $('#timeCurrent').textContent = timecode;
    $('#frameReadout').textContent = `F ${pad(frame.frameIndex, 3)} / ${state.frameCount}`;
    $('#editorFrame').textContent = label;
    $('#trackPlayhead')?.style.setProperty('left', `${percentage}%`);
    $('.playhead-label', $('#trackPlayhead') || document)?.replaceChildren(document.createTextNode(label));
    $('#chartPlayhead')?.setAttribute('x1', chartX.toFixed(2));
    $('#chartPlayhead')?.setAttribute('x2', chartX.toFixed(2));

    renderMetrics(frame);
    renderMarkerEditor();
  }

  function renderMetrics(frame) {
    $$('[data-metric]').forEach((node) => {
      const key = node.dataset.metric;
      node.textContent = metricValue(key, frame.metrics[key]);
    });

    const leftKnee = frame.metrics.left_knee_angle;
    const rightKnee = frame.metrics.right_knee_angle;
    const angleValues = $$('.angle-badges .badge-value');
    if (angleValues[0]) angleValues[0].textContent = leftKnee == null ? '—' : `${Number(leftKnee).toFixed(0)}°`;
    if (angleValues[1]) angleValues[1].textContent = rightKnee == null ? '—' : `${Number(rightKnee).toFixed(0)}°`;

    const quality = frame.metrics.pose_quality;
    const qualityNode = $('.stage-quality strong');
    if (qualityNode) qualityNode.textContent = quality == null ? '—' : `${(quality * 100).toFixed(2)}%`;

    const more = $('#metricsMore');
    if (!more) return;
    const keys = (KineFormContract.METRIC_KEYS || Object.keys(frame.metrics)).filter((key) => !PRIMARY_METRICS.has(key));
    more.innerHTML = `
      <div class="metric-more-head"><span>完整帧快照</span><span>${Object.keys(frame.metrics).length} 个键 · null 保留</span></div>
      <div class="metric-more-list">${keys.map((key) => `
        <div class="metric-more-group"><span title="${escapeHtml(key)}">${escapeHtml(METRIC_LABELS[key] || key)}</span><strong>${escapeHtml(metricValue(key, frame.metrics[key]))}</strong></div>
      `).join('')}</div>`;
  }

  function renderMarkerEditor() {
    const marker = selectedMarker();
    const labelInput = $('#markerLabel');
    const commentInput = $('#markerComment');
    const deleteButton = $('[data-action="delete-marker"]');
    if (!marker) {
      if (labelInput) { labelInput.value = ''; labelInput.disabled = true; }
      if (commentInput) { commentInput.value = ''; commentInput.disabled = true; }
      if (deleteButton) deleteButton.disabled = true;
      return;
    }
    if (labelInput) { labelInput.value = marker.label; labelInput.disabled = false; }
    if (commentInput) { commentInput.value = marker.comment; commentInput.disabled = false; }
    if (deleteButton) deleteButton.disabled = false;
  }

  function renderMarkerList() {
    const list = $('#markerList');
    if (!list) return;
    const markers = [...state.markers].sort((a, b) => a.frameIndex - b.frameIndex);
    if (!markers.length) {
      list.innerHTML = '<div class="empty-state">还没有标注<br />按 Space 在当前帧添加</div>';
      renderMarkerToolbar();
      return;
    }
    list.innerHTML = markers.map((marker) => {
      const checked = Boolean(state.multiSelect[marker.id]);
      const selected = marker.id === state.selectedMarkerId;
      return `
      <div class="marker-row ${selected ? 'is-selected' : ''} ${checked ? 'is-checked' : ''}" data-marker-id="${escapeHtml(marker.id)}">
        <input type="checkbox" class="marker-check" data-marker-check="${escapeHtml(marker.id)}" aria-label="选择标记：${escapeHtml(marker.label)}" ${checked ? 'checked' : ''} />
        <span class="marker-dot ${marker.suggested ? 'marker-dot-suggested' : ''}"></span>
        <span class="row-copy"><strong class="row-title">${escapeHtml(displayMarkerLabel(marker.label))}</strong><small class="row-meta">${frameLabel(marker.frameIndex)} · ${formatTimecode(marker.timestampMs)}</small></span>
        <span class="row-action">${marker.suggested ? '建议' : '标记'}</span>
      </div>`;
    }).join('');
    renderMarkerToolbar();
  }

  function selectedCount() {
    return state.markers.filter((marker) => state.multiSelect[marker.id]).length;
  }

  function renderMarkerToolbar() {
    const count = selectedCount();
    const total = state.markers.length;
    const allChecked = total > 0 && count === total;
    const selectAll = $('#markerSelectAll');
    const deleteButton = $('#deleteSelectedMarkers');
    const deleteCount = $('#deleteSelectedCount');
    if (selectAll) selectAll.checked = allChecked;
    if (deleteButton) {
      deleteButton.disabled = count === 0;
      deleteButton.title = count === 0 ? '勾选标记后可批量删除' : `删除选中的 ${count} 个标记`;
    }
    if (deleteCount) deleteCount.textContent = count > 0 ? String(count) : '';
  }

  function toggleMarkerSelectAll() {
    const allSelected = state.markers.length > 0 && state.markers.every((marker) => state.multiSelect[marker.id]);
    state.multiSelect = {};
    if (!allSelected) {
      state.markers.forEach((marker) => { state.multiSelect[marker.id] = true; });
    }
    renderMarkerList();
    showToast(allSelected ? '已取消全选' : `已全选 ${state.markers.length} 个标记`);
  }

  function toggleMarkerSelect(markerId, force) {
    if (force === true) state.multiSelect[markerId] = true;
    else if (force === false) delete state.multiSelect[markerId];
    else if (state.multiSelect[markerId]) delete state.multiSelect[markerId];
    else state.multiSelect[markerId] = true;
    renderMarkerList();
  }

  function deleteSelectedMarkers() {
    const ids = new Set(Object.keys(state.multiSelect).filter((id) => state.markers.some((marker) => marker.id === id)));
    const count = ids.size;
    if (!count) {
      showToast('请先勾选要删除的标记', true);
      return;
    }
    commitMarkerMutation(() => {
      state.markers = state.markers.filter((marker) => !ids.has(marker.id));
      if (!state.markers.some((marker) => marker.id === state.selectedMarkerId)) {
        state.selectedMarkerId = state.markers.at(-1)?.id || null;
      }
      state.multiSelect = {};
    });
    showToast(`已删除 ${count} 个标记，可用撤销一步恢复`);
  }

  async function clearAllMarkers() {
    if (!state.markers.length) {
      showToast('当前没有可清空的标记', true);
      return;
    }
    const confirmed = await confirmModal({
      title: '清空全部标记',
      message: `确定要删除全部 ${state.markers.length} 个标记吗？此操作占用一步撤销，可整体 Ctrl+Z 恢复。`,
      confirmText: '清空全部',
      cancelText: '取消',
      dangerous: true,
    });
    if (!confirmed) return;
    const count = state.markers.length;
    commitMarkerMutation(() => {
      state.markers = [];
      state.selectedMarkerId = null;
      state.multiSelect = {};
    });
    showToast(`已清空全部 ${count} 个标记，可用撤销一步恢复`);
  }

  function renderTimelineMarkers() {
    const container = $('#timelineMarkers');
    if (!container) return;
    container.innerHTML = [...state.markers].sort((a, b) => a.frameIndex - b.frameIndex).map((marker) => {
      const percentage = state.frameCount > 1 ? (marker.frameIndex / (state.frameCount - 1)) * 100 : 0;
      return `<button class="timeline-marker ${marker.id === state.selectedMarkerId ? 'is-selected' : ''} ${marker.suggested ? 'is-suggested' : ''}" data-marker-id="${escapeHtml(marker.id)}" style="left:${percentage.toFixed(3)}%" title="${escapeHtml(marker.label)} · ${frameLabel(marker.frameIndex)}" aria-label="${escapeHtml(marker.label)}，${frameLabel(marker.frameIndex)}"></button>`;
    }).join('');
  }

  function renderSuggestions() {
    const list = $('#suggestionList');
    if (!list) return;
    if (!state.suggestions.length) {
      list.innerHTML = '<div class="empty-state">events.json 没有建议事件</div>';
      return;
    }
    list.innerHTML = state.suggestions.map((suggestion) => {
      const adopted = state.markers.some((marker) => marker.frameIndex === suggestion.frameIndex);
      return `<button class="suggestion-row ${adopted ? 'is-adopted' : ''}" data-suggest-frame="${suggestion.frameIndex}">
        <span class="suggestion-mark yellow"></span>
        <span><strong>${escapeHtml(suggestion.label)}</strong><small>${frameLabel(suggestion.frameIndex)} · ${formatTimecode(frameTime(suggestion.frameIndex))}</small></span>
        <img class="icon icon-16" src="assets/icons/${adopted ? 'circle-check.svg' : 'circle-plus.svg'}" alt="${adopted ? '已采纳' : '采纳'}" />
      </button>`;
    }).join('');
  }

  function seriesValue(frame, series) {
    if (series === 'kneeL') return frame.metrics.left_knee_angle;
    if (series === 'kneeR') return frame.metrics.right_knee_angle;
    if (series === 'pelvis') return frame.metrics.pelvis_y;
    return frame.metrics.pose_quality;
  }

  function buildSeriesPath(series) {
    const values = state.frames.map((frame) => seriesValue(frame, series));
    const valid = values.filter((value) => value !== null && value !== undefined && Number.isFinite(Number(value))).map(Number);
    if (!valid.length) return '';
    const min = series === 'quality' ? 0.8 : Math.min(...valid);
    let max = series === 'quality' ? 1 : Math.max(...valid);
    if (Math.abs(max - min) < 0.001) max = min + 1;
    const step = Math.max(1, Math.floor(values.length / 180));
    let path = '';
    let active = false;
    for (let index = 0; index < values.length; index += step) {
      const value = values[index];
      if (value === null || value === undefined || !Number.isFinite(Number(value))) {
        active = false;
        continue;
      }
      const x = (index / Math.max(1, values.length - 1)) * 900;
      const y = 116 - ((Number(value) - min) / (max - min)) * 100;
      path += `${active ? 'L' : 'M'}${x.toFixed(2)} ${clamp(y, 12, 117).toFixed(2)} `;
      active = true;
    }
    return path.trim();
  }

  function activeSeriesBounds() {
    let min = Infinity;
    let max = -Infinity;
    for (const series of ['kneeL', 'kneeR', 'pelvis', 'quality']) {
      if (!state.series[series]) continue;
      for (const frame of state.frames) {
        const value = seriesValue(frame, series);
        if (value === null || value === undefined || !Number.isFinite(Number(value))) continue;
        min = Math.min(min, Number(value));
        max = Math.max(max, Number(value));
      }
    }
    return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : null;
  }

  function niceTickStep(span, count) {
    if (!(span > 0) || !Number.isFinite(span)) return 1;
    const raw = span / count;
    const magnitude = 10 ** Math.floor(Math.log10(raw));
    const normalized = raw / magnitude;
    const nice = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10;
    return nice * magnitude;
  }

  function formatAxisValue(value) {
    return String(Number(value.toPrecision(6)));
  }

  function renderYAxisTicks() {
    const labels = $('.chart-y-labels');
    if (!labels) return;
    const bounds = activeSeriesBounds();
    if (!bounds) {
      labels.innerHTML = '';
      return;
    }
    const step = niceTickStep(bounds.max - bounds.min, 3);
    const top = Math.ceil(bounds.max / step) * step;
    const bottom = Math.min(Math.floor(bounds.min / step) * step, top - 3 * step);
    labels.innerHTML = [top, top - step, top - 2 * step, bottom]
      .map((value) => `<span>${escapeHtml(formatAxisValue(value))}</span>`)
      .join('');
  }

  function formatAxisTime(timestampMs) {
    const seconds = Math.max(0, Math.round(Number(timestampMs) / 1000));
    return `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`;
  }

  function renderTimeAxisLabels() {
    const totalMs = Number(state.frames.at(-1)?.timestampMs) || 0;
    const ratios = [0, 0.25, 0.5, 0.75, 1];
    const xLabels = $('.chart-x-labels');
    if (xLabels) xLabels.innerHTML = ratios.map((ratio) => `<span>${formatAxisTime(totalMs * ratio)}</span>`).join('');
    const rulerTimes = $('#rulerTimes');
    if (rulerTimes) {
      rulerTimes.innerHTML = ratios
        .map((ratio) => `<span class="ruler-time mono" style="left:${(ratio * 100).toFixed(3)}%">${formatAxisTime(totalMs * ratio)}</span>`)
        .join('');
    }
  }

  function renderChart() {
    $$('[data-series-path]').forEach((path) => {
      const series = path.dataset.seriesPath;
      path.classList.toggle('hidden', !state.series[series]);
      path.setAttribute('d', buildSeriesPath(series));
    });
    $$('.chart-tab').forEach((tab) => {
      const active = state.series[tab.dataset.series];
      tab.classList.toggle('active', active);
      tab.classList.toggle('inactive', !active);
      tab.setAttribute('aria-selected', String(active));
    });
    renderYAxisTicks();
  }

  function formatStat(statistic, unit = '') {
    if (!statistic || statistic.mean === null || statistic.mean === undefined) return '—';
    return `${Number(statistic.mean).toFixed(1)}${unit}`;
  }

  function bandClass(band) {
    return band === 'common' || band === 'deviated' || band === 'outlier' ? band : 'muted';
  }

  function bandLabel(band) {
    return { common: '常见范围', deviated: '偏离', outlier: '异常', null: '未分层' }[band] || '未分层';
  }

  function gaitLabel(key) {
    const raw = String(key);
    const zh = raw.split('.').map((part) => GAIT_LABELS[part] || METRIC_LABELS[part] || part).join('');
    return zh === raw ? raw : `${zh} · ${raw}`;
  }

  function renderGaitPanel() {
    const gait = state.eventsDocument?.gait_summary;
    const summary = $('#gaitSummaryGrid');
    const references = $('#referenceList');
    const details = $('#gaitDetailGrid');
    if (!summary || !references || !details) return;
    if (!gait) {
      summary.innerHTML = '<div class="empty-state">当前 events.json 没有 gait_summary，步态面板已降级隐藏。</div>';
      references.innerHTML = '';
      details.innerHTML = '';
      $('#gaitStepCount').textContent = '—';
      return;
    }

    const nSteps = Array.isArray(gait.steps) ? gait.steps.length : 0;
    $('#gaitStepCount').textContent = `${nSteps} 步`;
    summary.innerHTML = [
      ['步频', gait.cadence_spm == null ? '—' : `${Number(gait.cadence_spm).toFixed(1)} spm`, 'cadence_spm'],
      ['平均步时', formatStat(gait.step_time_ms, ' ms'), 'step_time_ms'],
      ['左侧触地', formatStat(gait.left?.contact_time_ms, ' ms'), 'left.contact_time_ms'],
      ['右侧触地', formatStat(gait.right?.contact_time_ms, ' ms'), 'right.contact_time_ms'],
      ['身体尺度', gait.body_scale?.body_height_px == null ? '—' : `${Number(gait.body_scale.body_height_px).toFixed(1)} px`, 'body_height_px'],
      ['水平速度', gait.body_scale?.speed_mps == null ? '—' : `${Number(gait.body_scale.speed_mps).toFixed(2)} m/s`, 'speed_mps'],
    ].map(([label, value, meta]) => `<article class="gait-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(gaitLabel(meta))}</small></article>`).join('');

    const referencesData = Array.isArray(gait.reference_comparison) ? gait.reference_comparison : [];
    references.innerHTML = referencesData.length ? referencesData.flatMap((reference) => {
      const rows = [];
      for (const side of ['left', 'right']) {
        const summaryData = reference.side_summary?.[side] || {};
        const first = Object.entries(summaryData)[0];
        if (!first) continue;
        const [metric, value] = first;
        rows.push(`<div class="reference-row"><span>${escapeHtml(gaitLabel(reference.reference))} · ${side === 'left' ? '左侧' : '右侧'} · ${escapeHtml(gaitLabel(metric))}</span><span class="band-pill ${bandClass(value.band)}">z ${Number(value.mean_z).toFixed(2)} · ${bandLabel(value.band)}</span></div>`);
      }
      return rows;
    }).join('') : '<div class="empty-state">暂无参考对比</div>';

    const fatigue = gait.fatigue_trend;
    const takeoff = gait.takeoff_steps?.[0];
    details.innerHTML = [
      `<div class="gait-detail-row"><span>疲劳 · 触地时间变化</span><strong>${fatigue?.delta?.contact_time_ms == null ? '—' : `+${Number(fatigue.delta.contact_time_ms).toFixed(1)} ms`}</strong><small>${escapeHtml(gaitLabel('delta'))}</small></div>`,
      `<div class="gait-detail-row"><span>疲劳 · 摆动最小膝角</span><strong>${fatigue?.delta?.['swing.min_knee_angle'] == null ? '—' : `+${Number(fatigue.delta['swing.min_knee_angle']).toFixed(1)}°`}</strong><small>${escapeHtml(gaitLabel('delta'))}</small></div>`,
      `<div class="gait-detail-row"><span>疑似起跳步</span><strong>${takeoff ? `${takeoff.side === 'left' ? '左' : '右'}侧 · ${(Number(takeoff.confidence) * 100).toFixed(0)}%` : '—'}</strong><small>${takeoff ? `${escapeHtml(gaitLabel('ratio'))} ${Number(takeoff.ratio).toFixed(3)}` : escapeHtml(gaitLabel('takeoff_steps'))}</small></div>`,
    ].join('');
  }

  function renderReportPanel() {
    const chip = $('#reportStateChip');
    const summary = $('#reportSummary');
    const mismatch = $('#reportMismatch');
    const note = $('#reportNote');
    if (!chip || !summary || !mismatch || !note) return;
    const printButton = $('#printReportButton');
    if (printButton) {
      printButton.disabled = !state.report;
      printButton.title = state.report ? '导出报告（打印对话框可另存为 PDF）' : '请先提交分析生成报告';
    }
    const docHead = $('#reportDocHead');
    const markersSection = $('#reportMarkersSection');
    const refsSection = $('#reportRefsSection');
    const timelineSection = $('#reportTimelineSection');
    const aiSection = $('#reportAiSection');
    if (!state.report) {
      if (docHead) docHead.hidden = true;
      if (markersSection) markersSection.hidden = true;
      if (refsSection) refsSection.hidden = true;
      if (timelineSection) timelineSection.hidden = true;
      if (aiSection) aiSection.hidden = true;
      chip.textContent = state.task.status === 'failed' ? '失败' : '待提交';
      chip.className = `report-state-chip ${state.task.status === 'failed' ? 'failed' : ''}`;
      summary.innerHTML = '';
      mismatch.innerHTML = '';
      note.textContent = state.task.error || '提交分析后，任务成功时显示 score_report.json。';
      return;
    }
    chip.textContent = '已生成';
    chip.className = 'report-state-chip';
    const gait = state.report.summary?.gait;
    renderReportHead(state.report);
    summary.innerHTML = [
      ['标记数', state.report.summary?.n_markers ?? state.markers.length, 'n_markers'],
      ['步数', gait?.n_steps ?? '—', 'gait.n_steps'],
      ['步频', gait?.cadence_spm == null ? '—' : `${Number(gait.cadence_spm).toFixed(1)} spm`, 'cadence_spm'],
      ['平均触地', gait?.contact_time_ms_mean == null ? '—' : `${Number(gait.contact_time_ms_mean).toFixed(1)} ms`, 'contact_time_ms_mean'],
    ].map(([label, value, meta]) => `<article class="report-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(gaitLabel(meta))}</small></article>`).join('');
    const mismatches = (state.report.markers || []).flatMap((marker) => Object.keys(marker.metrics_checked?.mismatches || {}).map((key) => `${marker.label || frameLabel(marker.frameIndex)} · ${gaitLabel(key)}`));
    mismatch.innerHTML = mismatches.length ? `<div class="report-warning">源数据校验发现 ${mismatches.length} 个不一致指标：${escapeHtml(mismatches.join('、'))}</div>` : '';
    note.textContent = '导出方式：使用系统打印对话框，选择「另存为 PDF」即可离线导出报告。';
    renderReportMarkers();
    renderReportReferences(gait);
    renderReportTimeline();
    if (aiSection) aiSection.hidden = false;
  }

  function renderReportHead(report) {
    const head = $('#reportDocHead');
    const title = $('#reportDocTitle');
    const task = $('#reportDocTask');
    const meta = $('#reportDocMeta');
    if (!head || !title) return;
    head.hidden = false;
    const projectName = state.projectName || state.currentVideoId || report.video_id || '';
    title.textContent = exportReportTitle(projectName);
    if (task) task.textContent = `task_id ${report.task_id || state.task.id || '—'}`;
    if (meta) {
      const time = report.created_at ? new Date(report.created_at).toLocaleString('zh-CN') : formatTimecode(frameTime(state.frameCount - 1));
      meta.textContent = `源文件 ${state.sourceVideoName || state.motion?.source_video || '—'} · 帧数 ${state.frameCount} · 导出 ${time}`;
    }
  }

  function exportReportTitle(name) {
    return `步态分析报告 · ${name}`;
  }

  function renderReportMarkers() {
    const section = $('#reportMarkersSection');
    const table = $('#reportMarkersTable');
    if (!section || !table) return;
    const markers = (state.report.markers || []).filter((marker) => Number.isFinite(marker.frameIndex));
    if (!markers.length) { section.hidden = true; return; }
    section.hidden = false;
    const rows = markers.map((marker) => {
      const frame = state.frames[marker.frameIndex];
      const metrics = marker.metrics || frame?.metrics || {};
      const knee = metrics.left_knee_angle ?? metrics.right_knee_angle;
      const quality = metrics.pose_quality;
      const stepSide = marker.step?.side ? (marker.step.side === 'left' ? '左侧' : '右侧') : '—';
      return `<tr>
        <td class="num">${frameLabel(marker.frameIndex)}</td>
        <td>${escapeHtml(marker.label || '—')}</td>
        <td class="num">${knee == null ? '—' : `${Number(knee).toFixed(1)}°`}</td>
        <td class="num">${quality == null ? '—' : `${(Number(quality) * 100).toFixed(1)}%`}</td>
        <td>${stepSide}</td>
      </tr>`;
    }).join('');
    table.innerHTML = `<thead><tr><th>帧</th><th>标签</th><th>膝角</th><th>姿态质量</th><th>所属步</th></tr></thead><tbody>${rows}</tbody>`;
  }

  function renderReportReferences(gait) {
    const section = $('#reportRefsSection');
    const table = $('#reportRefsTable');
    if (!section || !table) return;
    const references = (gait?.reference_comparison || []);
    const rows = [];
    references.forEach((reference) => {
      // 兼容两种形态：新版 side_summary / 旧版 left+right 直挂
      const sideData = reference.side_summary
        || (reference.left || reference.right ? { left: reference.left || {}, right: reference.right || {} } : {});
      Object.entries(sideData).forEach(([side, metrics]) => {
        if (!metrics || typeof metrics !== 'object') return;
        Object.entries(metrics).forEach(([metric, info]) => {
          const z = info?.mean_z ?? (typeof info === 'number' ? info : null);
          const band = info?.band;
          rows.push(`<tr>
            <td>${escapeHtml(gaitLabel(reference.reference))}</td>
            <td>${side === 'left' ? '左侧' : side === 'right' ? '右侧' : escapeHtml(side)}</td>
            <td>${escapeHtml(gaitLabel(metric))}</td>
            <td class="num">${z == null ? '—' : Number(z).toFixed(2)}</td>
            <td>${band ? `<span class="band-pill ${bandClass(band)}">${escapeHtml(bandLabel(band))}</span>` : '—'}</td>
            <td class="num">${info?.n ?? '—'}</td>
          </tr>`);
        });
      });
    });
    if (!rows.length) { section.hidden = true; return; }
    section.hidden = false;
    table.innerHTML = `<thead><tr><th>参考人群</th><th>侧别</th><th>指标</th><th>z</th><th>分层</th><th>样本</th></tr></thead><tbody>${rows.join('')}</tbody>`;
  }

  function renderReportTimeline() {
    const section = $('#reportTimelineSection');
    const container = $('#reportTimeline');
    if (!section || !container) return;
    const items = (state.report.markers || []).flatMap((marker) => {
      const list = [{ frame: marker.frameIndex, label: marker.label || '标记' }];
      (marker.event_context || []).forEach((event) => {
        list.push({ frame: event.frame_index, label: `${displayMarkerLabel(String((EVENT_LABELS[event.type] || event.type).replaceAll('_', ' ')))}` });
      });
      return list;
    }).sort((a, b) => a.frame - b.frame);
    if (!items.length) { section.hidden = true; return; }
    section.hidden = false;
    container.innerHTML = items.map((item) => `
      <div class="report-tl-row"><span class="report-tl-frame">${frameLabel(item.frame)}</span><span class="report-tl-label">${escapeHtml(item.label)}</span></div>
    `).join('');
  }

  function renderInspectorState() {
    $$('.inspector-tab').forEach((tab) => {
      const active = tab.dataset.inspectorTab === state.activeInspectorTab;
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
    });
    $$('[data-inspector-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.inspectorPanel !== state.activeInspectorTab;
      panel.classList.toggle('active', !panel.hidden);
    });
    $('#markerCount').textContent = String(state.markers.length);
  }

  function renderTransportState() {
    const playIcon = $('#playIcon');
    const playButton = $('#playButton');
    const speedButton = $('#speedButton');
    if (playIcon) {
      playIcon.src = `assets/icons/${state.playing ? 'circle-pause.svg' : 'circle-play.svg'}`;
      playIcon.alt = state.playing ? '暂停' : '播放';
    }
    if (playButton) playButton.setAttribute('aria-label', state.playing ? '暂停' : '播放');
    if (speedButton) speedButton.firstChild.textContent = `${state.speed.toFixed(2).replace(/0$/, '')}× `;
    if ($('#zoomReadout')) $('#zoomReadout').textContent = `${state.zoom}%`;
  }

  function renderToolState() {
    $$('[data-tool]').forEach((button) => {
      const active = button.dataset.tool === state.activeTool;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    $('#viewerStage')?.classList.toggle('overlay-off', !state.overlay);
    $('#viewerStage')?.classList.toggle('show-grid', state.grid);
    const overlayButton = $('[data-action="toggle-overlay"]');
    if (overlayButton) {
      const demoMode = state.service.mode === 'demo';
      const hasOverlay = videoLayer.overlayAvailable; // live 项目是否有 analysis.mp4 叠加层
      const usable = demoMode || hasOverlay;
      overlayButton.disabled = !usable;
      if (!demoMode && !hasOverlay) overlayButton.title = '当前项目未生成分析视频';
      else overlayButton.title = '';
      overlayButton.setAttribute('aria-pressed', String(demoMode ? state.overlay : (hasOverlay && state.overlay)));
    }
    renderOverlayVisual();
    const audioButton = $('[data-action="toggle-audio"]');
    if (audioButton) {
      audioButton.setAttribute('aria-pressed', String(state.audio));
      audioButton.setAttribute('aria-label', state.audio ? '静音' : '取消静音');
      audioButton.classList.toggle('muted', !state.audio);
      const audioIcon = $('img', audioButton);
      if (audioIcon) {
        audioIcon.src = `assets/icons/${state.audio ? 'megaphone.svg' : 'megaphone-muted.svg'}`;
        audioIcon.alt = state.audio ? '音频开启' : '音频已静音';
      }
    }
  }

  function renderServiceState() {
    const status = $('#serviceStatus');
    const text = $('#serviceStatusText');
    const version = $('#serviceVersion');
    if (!status || !text || !version) return;
    status.dataset.serviceState = state.service.state;
    text.textContent = state.service.message;
    version.textContent = state.service.version ? `v${state.service.version}` : `client v${CLIENT_VERSION}`;
    const submitButton = $('[data-action="submit"]');
    if (submitButton) submitButton.disabled = Boolean(state.service.blocked);
  }

  function renderTaskState() {
    const drawer = $('#taskDrawer');
    if (!drawer) return;
    const active = state.task.status !== 'idle';
    drawer.hidden = !active;
    if (!active) return;
    const status = state.task.status;
    const statusChip = $('#taskStatusChip');
    const progressBar = $('#taskProgressBar');
    const progressText = $('#taskProgressText');
    const percent = $('#taskPercent');
    const detail = $('#taskDetail');
    const taskId = $('#taskIdText');
    const cancelButton = $('#cancelTaskButton');
    if (statusChip) {
      statusChip.textContent = TASK_LABELS[status] || status;
      statusChip.className = `task-status-chip ${status}`;
    }
    if (progressBar) progressBar.style.width = `${clamp(Number(state.task.percent) || 0, 0, 100)}%`;
    if (progressText) progressText.textContent = state.task.error || state.task.detail || TASK_LABELS[status] || status;
    if (percent) percent.textContent = state.task.percent == null ? '—' : `${Number(state.task.percent).toFixed(0)}%`;
    if (detail) detail.textContent = state.task.error || state.task.detail || '分析任务状态将显示在这里。';
    if (taskId) taskId.textContent = `task_id ${state.task.id || '—'}`;
    if (cancelButton) cancelButton.disabled = !['queued', 'running'].includes(status);
    // 终态显示「关闭」按钮（2026-08-27 用户反馈：任务完成后抽屉无法收起）
    const dismissButton = $('#taskDismissButton');
    if (dismissButton) dismissButton.hidden = !isTerminalTask(status);
  }

  function dismissTask() {
    // 仅终态可收起抽屉；报告数据在 state.report，不受影响
    if (!isTerminalTask(state.task.status)) return;
    clearTaskTimers();
    state.task = { ...state.task, status: 'idle', pollTimer: null, demoTimer: null };
    renderTaskState();
  }

  function render() {
    renderProjectMeta();
    renderFrameState();
    renderMarkerList();
    renderTimelineMarkers();
    renderSuggestions();
    renderChart();
    renderGaitPanel();
    renderReportPanel();
    renderInspectorState();
    renderTransportState();
    renderToolState();
    renderServiceState();
    renderTaskState();
    renderAnalysisState();
  }

  function buildSubmitPayload() {
    return KineFormContract.buildSubmitPayload({
      motion: state.motion,
      markers: state.markers,
      motionSource: state.motionSource,
      motionSha256: state.motionSha256,
    });
  }

  function isTerminalTask(status) {
    return ['succeeded', 'failed', 'cancelled'].includes(status);
  }

  function clearTaskTimers() {
    if (state.task.pollTimer) window.clearTimeout(state.task.pollTimer);
    if (state.task.demoTimer) window.clearInterval(state.task.demoTimer);
    state.task.pollTimer = null;
    state.task.demoTimer = null;
  }

  function createDemoReport(taskId) {
    const report = clone(KineFormDemoData.createDemoReport());
    report.task_id = taskId;
    report.video_id = state.motion.video_id;
    report.summary.n_markers = state.markers.length;
    report.markers = buildSubmitPayload().markers.map((marker) => ({ ...marker, step: null, event_context: null }));
    return report;
  }

  async function loadTaskReport(task) {
    if (state.service.mode === 'live' && state.api && task.id) {
      try {
        return await state.api.fetchTaskResult(task.id);
      } catch (error) {
        const apiError = handleApiError(error);
        showToast(`score_report.json 加载失败：${apiError.message}`, true);
        return null;
      }
    }
    return createDemoReport(task.id);
  }

  async function finishTask(task) {
    clearTaskTimers();
    state.task = { ...state.task, ...task, pollTimer: null, demoTimer: null };
    if (task.status === 'succeeded') {
      state.report = await loadTaskReport(task);
      state.activeInspectorTab = 'report';
      showToast('分析完成，score_report.json 已加载');
    } else if (task.status === 'failed') {
      state.activeInspectorTab = 'report';
      showToast(task.error || '分析任务失败', true);
    } else if (task.status === 'cancelled') {
      showToast('分析任务已取消');
    }
    render();
  }

  function handleApiError(error) {
    return error?.api || KineFormContract.mapApiError(error?.status || 500, error?.body || {});
  }

  async function pollApiTask(taskId, tracker, onUpdate, onFinish) {
    if (!state.api || tracker.id !== taskId) return;
    let task;
    try {
      task = await state.api.task(taskId);
    } catch (error) {
      const apiError = handleApiError(error);
      task = {
        status: 'failed',
        error: apiError.code === 'task_not_found' ? '分析服务已重启，请重新提交。' : apiError.message,
      };
    }
    Object.assign(tracker, task);
    onUpdate();
    if (isTerminalTask(tracker.status)) {
      await onFinish(task);
      return;
    }
    tracker.pollTimer = window.setTimeout(() => { void pollApiTask(taskId, tracker, onUpdate, onFinish); }, 700);
  }

  async function pollLiveTask(taskId) {
    await pollApiTask(taskId, state.task, renderTaskState, finishTask);
  }

  function startDemoTask() {
    clearTaskTimers();
    state.report = null;
    state.task = {
      id: `t_demo_${Date.now().toString(36)}`,
      status: 'queued',
      stage: 'queued',
      percent: 0,
      detail: '等待演示分析服务分配执行位',
      error: null,
      result_path: `outputs/${state.motion.video_id}/score_report.json`,
      pollTimer: null,
      demoTimer: null,
    };
    render();
    const steps = [
      { status: 'queued', stage: 'queued', percent: 0, detail: '任务已受理，等待执行位' },
      { status: 'running', stage: 'validate', percent: 22, detail: '校验 marker 与 motion.json 对齐' },
      { status: 'running', stage: 'score', percent: 60, detail: '生成步态特征与参考对比' },
      { status: 'running', stage: 'report', percent: 88, detail: '写入 score_report.json' },
      { status: 'succeeded', stage: 'complete', percent: 100, detail: '报告已生成' },
    ];
    let index = 0;
    state.task.demoTimer = window.setInterval(() => {
      const next = steps[Math.min(index, steps.length - 1)];
      state.task = { ...state.task, ...next };
      renderTaskState();
      if (isTerminalTask(next.status)) {
        const task = { ...state.task };
        void finishTask(task);
      }
      index += 1;
    }, 850);
  }

  async function submitAnalysis() {
    if (!state.markers.length) {
      showToast('至少添加一个标记后才能提交分析', true);
      return;
    }
    if (state.service.blocked) {
      showToast('分析服务版本不匹配，当前已阻止提交', true);
      return;
    }
    if (['queued', 'running', 'cancelling'].includes(state.task.status)) {
      showToast('已有分析任务正在执行');
      return;
    }
    const payload = buildSubmitPayload();
    window.__kineformLastSubmitPayload = payload;
    markSaved();

    if (state.service.mode === 'live' && state.api) {
      try {
        const response = await state.api.submit(payload);
        state.report = null;
        state.task = {
          ...state.task,
          id: response.task_id,
          status: 'queued',
          stage: 'queued',
          percent: 0,
          detail: '任务已受理，等待执行',
          error: null,
          result_path: response.result_path,
        };
        render();
        void pollLiveTask(response.task_id);
      } catch (error) {
        const apiError = handleApiError(error);
        if (apiError.code === 'duplicate_video' && apiError.taskId) {
          state.task = { ...state.task, id: apiError.taskId, status: 'queued', percent: 0, detail: '发现已有任务，已转为轮询', error: null };
          render();
          showToast('该视频已有任务，已转为轮询既有任务');
          void pollLiveTask(apiError.taskId);
          return;
        }
        state.task = { ...state.task, id: null, status: 'failed', percent: 0, detail: apiError.message, error: apiError.message };
        render();
        showToast(apiError.message, true);
      }
      return;
    }

    console.info('KineForm demo submit payload', payload);
    startDemoTask();
  }

  async function cancelTask() {
    if (!['queued', 'running'].includes(state.task.status)) return;
    if (state.service.mode !== 'live' || !state.api) {
      state.task = { ...state.task, status: 'cancelling', stage: 'cancelling', detail: '已请求取消，等待执行体检查点' };
      renderTaskState();
      window.setTimeout(() => { void finishTask({ ...state.task, status: 'cancelled', detail: '演示任务已取消' }); }, 500);
      return;
    }
    try {
      const result = await state.api.cancel(state.task.id);
      state.task = { ...state.task, ...result, detail: '已请求取消，等待执行体检查点' };
      render();
      void pollLiveTask(state.task.id);
    } catch (error) {
      const apiError = handleApiError(error);
      if (apiError.code === 'task_finished') {
        showToast('任务已经到达终态，请刷新任务状态');
        return;
      }
      showToast(apiError.message, true);
    }
  }

  function isAnalysisTaskActive() {
    return ['queued', 'running', 'cancelling'].includes(state.analysis.status);
  }

  function clearAnalysisTimers() {
    if (state.analysis.pollTimer) window.clearTimeout(state.analysis.pollTimer);
    state.analysis.pollTimer = null;
  }

  function resetAnalysisState() {
    clearAnalysisTimers();
    state.analysis = {
      id: null,
      status: 'idle',
      stage: null,
      percent: null,
      detail: null,
      error: null,
      result_path: null,
      pollTimer: null,
    };
  }

  function renderAnalysisState() {
    const banner = $('#analysisBanner');
    if (!banner) return;
    const active = isAnalysisTaskActive();
    banner.hidden = !active;
    if (active) {
      $('#analysisStageText').textContent = state.analysis.stage || TASK_LABELS[state.analysis.status] || state.analysis.status;
      $('#analysisDetailText').textContent = state.analysis.detail || state.analysis.error || '';
      $('#analysisProgressBar').style.width = `${clamp(Number(state.analysis.percent) || 0, 0, 100)}%`;
      $('#analysisPercent').textContent = state.analysis.percent == null ? '—' : `${Number(state.analysis.percent).toFixed(0)}%`;
      const cancelButton = $('#cancelAnalysisButton');
      if (cancelButton) cancelButton.disabled = state.analysis.status === 'cancelling';
    }
    $$('[data-action="analyze-video"]').forEach((button) => { button.disabled = active; });
    const projectSelect = $('#projectSelect');
    if (projectSelect) projectSelect.disabled = active;
  }

  function videoIdFromResultPath(resultPath) {
    const match = String(resultPath || '').match(/^projects\/([^/]+?)\/?$/);
    return match ? match[1] : null;
  }

  function trackAnalysisTask(taskId) {
    void pollApiTask(taskId, state.analysis, renderAnalysisState, finishAnalysisTask);
  }

  async function finishAnalysisTask(task) {
    const status = task.status;
    const error = state.analysis.error || task.error || null;
    const resultPath = state.analysis.result_path || task.result_path || null;
    resetAnalysisState();
    renderAnalysisState();
    if (status === 'succeeded') {
      showToast('视频分析完成，正在加载新项目');
      state.currentVideoId = videoIdFromResultPath(resultPath);
      await loadProjectList();
    } else if (status === 'failed') {
      showToast(error || '视频分析失败', true);
    } else if (status === 'cancelled') {
      showToast('视频分析已取消');
    }
  }

  function defaultProjectNameFromPath(path) {
    const base = String(path || '').split(/[\\/]/).pop() || '';
    const dot = base.lastIndexOf('.');
    return dot > 0 ? base.slice(0, dot) : base;
  }

  async function renameProject() {
    if (!state.motion) return;
    const chosen = await promptModal({
      title: '重命名项目',
      label: '项目名称',
      value: state.projectName || '',
      placeholder: state.currentVideoId || '项目名称',
      confirmText: '保存',
      cancelText: '取消',
    });
    if (chosen === null || chosen === (state.projectName || '')) return;
    applyProjectName(chosen);
  }

  function applyProjectName(name) {
    const trimmed = name && name.trim() ? name.trim() : null;
    state.projectName = trimmed;
    if (trimmed) window.__kineformLastProjectName = trimmed;
    renderProjectMeta();
    void persistMarkersNow();
    showToast(trimmed ? `项目已重命名为「${trimmed}」` : '已清除项目名，将回退显示视频 ID');
  }

  async function deleteProjectFlow() {
    if (state.service.mode !== 'live' || !state.api || !state.currentVideoId) {
      showToast('演示模式无项目可删除');
      return;
    }
    const videoId = state.currentVideoId;
    const displayName = state.projectName || videoId;
    const confirmed = await confirmModal({
      title: '删除项目',
      message: `将彻底删除项目「${displayName}」的全部数据（视频、标注、分析结果），删除后不可恢复。确定删除吗？`,
      confirmText: '删除',
      cancelText: '取消',
      dangerous: true,
    });
    if (!confirmed) return;
    // 取消未落盘的防抖保存，避免删除后竞态 PUT 404
    window.clearTimeout(state.persistTimer);
    state.persistTimer = null;
    try {
      await state.api.deleteProject(videoId);
    } catch (error) {
      const apiError = handleApiError(error);
      showToast(`项目删除失败：${apiError.message}`, true);
      return;
    }
    showToast(`已删除项目「${displayName}」`);
    // 删除的是当前项目 → 清空选中，loadProjectList 会切换到剩余首个项目
    if (state.currentVideoId === videoId) state.currentVideoId = null;
    await loadProjectList();
  }

  async function startAnalysisFlow() {
    if (state.service.mode !== 'live' || !state.api) {
      showToast('视频分析需要后端服务，请先连接分析服务', true);
      return;
    }
    const dialog = window.KineFormDialog;
    if (!dialog || typeof dialog.openVideo !== 'function') {
      showToast('选择视频需在桌面应用中使用', true);
      return;
    }
    if (isAnalysisTaskActive()) {
      showToast('已有视频分析任务进行中');
      return;
    }
    let picked = null;
    try {
      picked = await dialog.openVideo();
    } catch (error) {
      console.warn('Unable to open the native video dialog.', error);
      return;
    }
    if (!picked || picked.canceled || !picked.path) return;

    // 命名入口 A：分析前弹模态，预填文件名去扩展名；确认或留空随 start 提交
    const defaultName = defaultProjectNameFromPath(picked.path) || null;
    const chosenName = await promptModal({
      title: '命名分析项目',
      label: '项目名称',
      value: defaultName || '',
      placeholder: defaultName || '给这个分析起个名字（可选）',
      confirmText: '开始分析',
      cancelText: '跳过',
    });
    const projectName = chosenName && chosenName.trim() ? chosenName.trim() : null;

    state.analysis = {
      ...state.analysis,
      id: null,
      status: 'queued',
      stage: null,
      percent: 0,
      detail: '任务已提交，等待受理',
      error: null,
      result_path: null,
    };
    renderAnalysisState();
    try {
      const response = await state.api.startAnalysis(String(picked.path), projectName);
      state.analysis = {
        ...state.analysis,
        id: response.task_id,
        status: 'queued',
        result_path: response.result_path || null,
      };
      renderAnalysisState();
      showToast('视频分析任务已受理');
      trackAnalysisTask(response.task_id);
    } catch (error) {
      const apiError = handleApiError(error);
      if (apiError.code === 'duplicate_video' && apiError.taskId) {
        state.analysis = {
          ...state.analysis,
          id: apiError.taskId,
          status: 'queued',
          percent: 0,
          detail: '发现已有分析任务，已转为跟踪进度',
        };
        renderAnalysisState();
        showToast('该视频已有分析任务，已转为跟踪进度');
        trackAnalysisTask(apiError.taskId);
        return;
      }
      resetAnalysisState();
      renderAnalysisState();
      showToast(ANALYSIS_ERROR_HINTS[apiError.code] || apiError.message, true);
    }
  }

  async function cancelAnalysisTask() {
    if (!['queued', 'running'].includes(state.analysis.status)) return;
    try {
      const result = await state.api.cancel(state.analysis.id);
      Object.assign(state.analysis, result, { detail: '已请求取消，等待执行体检查点' });
      renderAnalysisState();
    } catch (error) {
      const apiError = handleApiError(error);
      if (apiError.code === 'task_finished') {
        showToast('任务已经到达终态，请等待状态刷新');
        return;
      }
      showToast(apiError.message, true);
    }
  }

  async function restoreAnalysisTask() {
    if (!window.KineFormDialog || state.service.mode !== 'live' || !state.api) return;
    let response;
    try {
      response = await state.api.tasks();
    } catch (error) {
      console.warn('Unable to list tasks for analysis restore.', error);
      return;
    }
    const tasks = Array.isArray(response) ? response : (Array.isArray(response?.tasks) ? response.tasks : []);
    const active = tasks.find((task) => task?.type === 'analyze' && ['queued', 'running', 'cancelling'].includes(task.status));
    if (!active) return;
    const taskId = active.task_id || active.id;
    if (!taskId) return;
    state.analysis = { ...state.analysis, ...active, id: taskId, pollTimer: null };
    renderAnalysisState();
    showToast('检测到进行中的视频分析任务，已恢复进度显示');
    trackAnalysisTask(taskId);
  }

  function renderProjectSelect() {
    const select = $('#projectSelect');
    if (!select) return;
    const live = state.service.mode === 'live' && state.projects.length > 0;
    select.hidden = !live;
    const deleteButton = $('#projectDeleteButton');
    if (deleteButton) deleteButton.hidden = !live;
    if (!live) return;
    select.innerHTML = state.projects.map((project) => {
      const selected = project.video_id === state.currentVideoId ? ' selected' : '';
      return `<option value="${escapeHtml(project.video_id)}"${selected}>${escapeHtml(project.video_id)}</option>`;
    }).join('');
  }

  function showStageEmpty(visible) {
    $('#stageEmpty')?.classList.toggle('hidden', !visible);
    if (visible) {
      $('#poseCanvas')?.classList.add('hidden');
      overlayVideo()?.classList.add('hidden');
      stageVideo()?.classList.add('hidden');
      videoLayer.available = false;
      videoLayer.overlayAvailable = false;
    }
  }

  function applyProjectState(motion, eventsDocument, markers, options = {}) {
    stopPlayback();
    state.motion = motion;
    state.eventsDocument = eventsDocument;
    state.fps = motion.fps;
    state.frameCount = motion.frame_count;
    state.frames = motion.frames;
    state.currentFrame = clamp(options.currentFrame ?? 0, 0, state.frameCount - 1);
    state.suggestions = buildSuggestedEvents(eventsDocument);
    state.markers = (Array.isArray(markers) ? markers : []).map(normalizeMarker);
    state.history = [];
    state.future = [];
    state.selectedMarkerId = state.markers[0]?.id || null;
    state.currentVideoId = motion.video_id;
    state.multiSelect = {};
    state.overlay = true; // 切项目时重置叠加开关（默认开）
    state.projectName = options.projectName ?? null;
    state.sourceVideoName = options.sourceVideoName ?? null;
    if (!options.keepSourceLabels) {
      state.motionSource = options.motionSource || DEMO_SOURCE;
      state.motionSha256 = options.motionSha256 ?? null;
    }
    showStageEmpty(false);
    applyVideoSource();
    renderTimeAxisLabels();
    render();
  }

  async function loadProject(videoId) {
    let motionRaw;
    try {
      motionRaw = await state.api.fetchMotion(videoId);
    } catch (error) {
      const apiError = handleApiError(error);
      if (apiError.code === 'project_not_found') {
        showToast('项目已不存在，正在刷新项目列表', true);
        await loadProjectList();
        return;
      }
      showToast(`motion.json 加载失败：${apiError.message}`, true);
      return;
    }

    let meta = null;
    try {
      meta = await state.api.fetchMeta(videoId);
    } catch (error) {
      // meta.json 为可选文件：旧项目 404 meta_not_found，容错回退，不影响加载
      if (handleApiError(error).code !== 'meta_not_found') {
        console.warn('Unable to load meta.json.', error);
      }
    }

    let eventsRaw = null;
    try {
      eventsRaw = await state.api.fetchEvents(videoId);
    } catch (error) {
      const apiError = handleApiError(error);
      if (apiError.code !== 'events_not_found') {
        console.warn('Unable to load events.json.', error);
        showToast('events.json 加载失败，按无步态事件处理', true);
      }
    }

    let markers = [];
    let annotationsProjectName = null;
    try {
      const annotations = await state.api.fetchAnnotations(videoId);
      const list = Array.isArray(annotations) ? annotations : annotations?.markers;
      if (Array.isArray(list)) markers = list;
      if (annotations && typeof annotations === 'object' && !Array.isArray(annotations) && annotations.project_name) {
        annotationsProjectName = String(annotations.project_name);
      }
    } catch (error) {
      const apiError = handleApiError(error);
      if (apiError.code !== 'annotations_not_found') {
        console.warn('Unable to load annotations.json.', error);
        showToast('annotations.json 加载失败，按空白标注起步', true);
      }
    }

    // （骨架叠加已回滚为 analysis.mp4 叠加层方案，不再加载 keypoints.json）

    applyProjectState(KineFormContract.normalizeMotion(motionRaw), KineFormContract.normalizeEvents(eventsRaw || {}), markers, {
      motionSource: `api/projects/${videoId}/motion`,
      projectName: annotationsProjectName || meta?.project_name || null,
      sourceVideoName: meta?.source_video_name || null,
    });
    renderProjectSelect();
    showToast(`已加载项目 ${annotationsProjectName || videoId}`);
  }

  async function loadProjectList() {
    let projects = [];
    try {
      const response = await state.api.listProjects();
      projects = Array.isArray(response?.projects) ? response.projects : [];
    } catch (error) {
      showToast(`项目列表加载失败：${handleApiError(error).message}`, true);
    }
    state.projects = projects;
    if (!projects.length) {
      state.currentVideoId = null;
      showStageEmpty(true);
      renderProjectSelect();
      showToast('没有可分析的项目，请先运行姿态分析生成 motion.json');
      return;
    }
    const target = projects.find((project) => project.video_id === state.currentVideoId) || projects[0];
    renderProjectSelect();
    await loadProject(target.video_id);
  }

  async function loadDemoProject() {
    const config = window.KineFormConfig || {};
    const loaded = await KineFormContract.loadProjectData({
      bridge: window.kineformBridge,
      fetchImpl: typeof window.fetch === 'function' ? window.fetch.bind(window) : null,
      motionUrl: config.motionUrl || null,
      eventsUrl: config.eventsUrl || null,
      motionFallback: KineFormDemoData.createDemoMotion(),
      eventsFallback: KineFormDemoData.createDemoEvents(),
    });
    // 先就位 motion 上下文，loadDemoMarkers 的 storage key 与 normalizeMarker 才能取到当前项目
    state.motion = loaded.motion;
    state.frames = loaded.motion.frames;
    state.frameCount = loaded.motion.frame_count;
    const markers = await loadDemoMarkers();
    applyProjectState(loaded.motion, loaded.events, markers, {
      currentFrame: 80,
      motionSource: config.motionSource || DEMO_SOURCE,
      motionSha256: config.motionSha256 || null,
      projectName: demoProjectName || null,
    });
  }

  async function probeService() {
    const config = window.KineFormConfig || {};
    if (!config.apiBaseUrl) {
      state.service = { ...state.service, mode: 'demo', state: 'demo', ready: true, blocked: false, message: '演示模式 · API 待连接' };
      renderServiceState();
      return;
    }
    try {
      const health = await state.api.health();
      const compatibility = KineFormContract.isVersionCompatible(CLIENT_VERSION, health.service_version);
      state.service = {
        ...state.service,
        mode: 'live',
        state: compatibility.compatible ? (compatibility.patchMismatch ? 'warning' : 'ready') : 'blocked',
        ready: health.status === 'ok',
        blocked: !compatibility.compatible || health.status !== 'ok',
        version: health.service_version,
        message: !compatibility.compatible ? '服务版本不匹配 · 已阻断' : compatibility.patchMismatch ? '分析服务已就绪 · patch 警告' : '分析服务已就绪',
      };
    } catch (error) {
      state.service = { ...state.service, mode: 'demo', state: 'unavailable', ready: true, blocked: false, message: '演示模式 · API 暂不可用' };
    }
    renderServiceState();
    renderProjectMeta();
  }

  function handleAction(action) {
    switch (action) {
      case 'step-back': stepFrame(-1); break;
      case 'step-forward': stepFrame(1); break;
      case 'play': togglePlayback(); break;
      case 'add-marker': addMarker(); break;
      case 'undo': undoMarkers(); break;
      case 'redo': redoMarkers(); break;
      case 'delete-marker': deleteSelectedMarker(); break;
      case 'delete-selected-markers': deleteSelectedMarkers(); break;
      case 'clear-markers': void clearAllMarkers(); break;
      case 'rename-project': void renameProject(); break;
      case 'delete-project': void deleteProjectFlow(); break;
      case 'help-chart': infoChartHelp(); break;
      case 'help-zscore': infoZscoreHelp(); break;
      case 'toggle-overlay':
        state.overlay = !state.overlay;
        renderToolState();
        // 打开叠加层时对齐到当前帧（toggle-open align）
        if (state.overlay && videoLayer.available && videoLayer.overlayAvailable) {
          void seekVideoToFrame(state.currentFrame);
        }
        break;
      case 'toggle-grid': state.grid = !state.grid; renderToolState(); break;
      case 'toggle-audio':
        state.audio = !state.audio;
        if (videoLayer.available) {
          const video = stageVideo();
          if (video) video.muted = !state.audio;
          const overlay = overlayVideo();
          if (overlay) overlay.muted = true; // 叠加层永远静音
        }
        renderToolState();
        showToast(state.audio ? '音频已开启' : '音频已静音');
        break;
      case 'toggle-speed': $('#speedMenu')?.classList.toggle('is-open'); break;
      case 'zoom-out': zoomTimeline(-25); break;
      case 'zoom-in': zoomTimeline(25); break;
      case 'stage-zoom-in': stepStageZoom(1); break;
      case 'stage-zoom-out': stepStageZoom(-1); break;
      case 'stage-zoom-reset': setStageZoom(1); break;
      case 'print-report':
        if (!state.report) {
          showToast('请先提交分析生成报告', true);
          break;
        }
        window.print();
        break;
      case 'save': void persistMarkersNow().then((saved) => { if (saved) showToast('annotations.json 已保存'); }); break;
      case 'submit': void submitAnalysis(); break;
      case 'cancel-task': void cancelTask(); break;
      case 'dismiss-task': dismissTask(); break;
      case 'analyze-video': void startAnalysisFlow(); break;
      case 'cancel-analysis': void cancelAnalysisTask(); break;
      case 'open-project':
        if (state.service.mode === 'live' && state.api) void loadProjectList().then(() => showToast('项目列表已刷新'));
        else showToast('演示模式无项目列表');
        break;
      case 'back': showToast('项目导航在桌面客户端中可用'); break;
      case 'fullscreen':
        if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => showToast('当前环境不允许全屏'));
        else showToast('当前环境不支持全屏');
        break;
      case 'help': showToast('快捷键：←/→ 逐帧，Shift ±5，K 播放，Space 打点/删除，Esc 关闭任务面板'); break;
      default: break;
    }
  }

  function bindTimelineMarkerDrag() {
    const container = $('#timelineMarkers');
    const track = $('#timelineTrack');
    if (!container || !track) return;
    container.addEventListener('pointerdown', (event) => {
      const pin = event.target.closest('[data-marker-id]');
      if (!pin) return;
      const marker = state.markers.find((item) => item.id === pin.dataset.markerId);
      if (!marker) return;
      event.preventDefault();
      event.stopPropagation();
      state.selectedMarkerId = marker.id;
      const frameFromClientX = (clientX) => {
        const rect = track.getBoundingClientRect();
        const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
        return clamp(Math.round(ratio * (state.frameCount - 1)), 0, state.frameCount - 1);
      };
      const previewFrame = (frame) => {
        const percentage = state.frameCount > 1 ? (frame / (state.frameCount - 1)) * 100 : 0;
        pin.style.left = `${percentage.toFixed(3)}%`;
        pin.title = `${marker.label} · ${frameLabel(frame)}`;
      };
      const onMove = (moveEvent) => previewFrame(frameFromClientX(moveEvent.clientX));
      const onEnd = (endEvent) => {
        pin.removeEventListener('pointermove', onMove);
        pin.removeEventListener('pointerup', onEnd);
        pin.removeEventListener('pointercancel', onEnd);
        document.body.classList.remove('is-marker-dragging');
        pin.classList.remove('is-dragging');
        const nextFrame = frameFromClientX(endEvent.clientX);
        if (nextFrame === marker.frameIndex) {
          render();
          return;
        }
        commitMarkerMutation(() => {
          const target = state.markers.find((item) => item.id === marker.id);
          target.frameIndex = nextFrame;
          target.timestampMs = frameTime(nextFrame);
          target.updatedAt = new Date().toISOString();
        });
        showToast(`${frameLabel(nextFrame)} 标记已移动`);
      };
      document.body.classList.add('is-marker-dragging');
      pin.classList.add('is-dragging');
      pin.setPointerCapture?.(event.pointerId);
      pin.addEventListener('pointermove', onMove);
      pin.addEventListener('pointerup', onEnd);
      pin.addEventListener('pointercancel', onEnd);
    });
  }

  function bindVideoEvents() {
    const video = stageVideo();
    const overlay = overlayVideo();
    if (!video) return;
    video.addEventListener('loadedmetadata', () => {
      seekVideoToFrame(state.currentFrame);
      if (overlay && videoLayer.overlayAvailable) overlay.muted = true;
    });
    video.addEventListener('seeked', () => {
      videoLayer.seeking = false;
      renderFrameState();
    });
    video.addEventListener('ended', () => stopPlayback());
    video.addEventListener('error', () => {
      if (!videoLayer.available) return;
      videoLayer.available = false;
      videoLayer.overlayAvailable = false;
      stopPlayback();
      video.classList.add('hidden');
      overlay?.classList.add('hidden');
      $('#poseCanvas')?.classList.add('hidden');
      showToast('视频不可用，已切换为示意播放');
    });
    if (overlay) {
      overlay.addEventListener('loadeddata', () => {
        if (!videoLayer.overlayAvailable) return;
        // 被动对齐：叠加层元数据就绪后跟随当前帧
        void seekVideoToFrame(state.currentFrame);
      });
      overlay.addEventListener('ended', () => {
        if (!video.paused) stopPlayback();
      });
      overlay.addEventListener('error', () => {
        if (!videoLayer.overlayAvailable) return;
        videoLayer.overlayAvailable = false;
        renderToolState();
        showToast('分析视频不可用，骨架叠加已禁用');
      });
    }
  }

  function bindEvents() {
    $$('[data-action]').forEach((button) => {
      button.addEventListener('click', () => handleAction(button.dataset.action));
    });

    $$('[data-tool]').forEach((button) => {
      button.addEventListener('click', () => {
        state.activeTool = button.dataset.tool;
        renderToolState();
        if (state.activeTool !== 'select') showToast(`${button.title?.split(' ')[0] || '工具'}已激活`);
      });
    });

    $$('.chart-tab').forEach((tab) => tab.addEventListener('click', () => toggleSeries(tab.dataset.series)));

    $$('.inspector-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        state.activeInspectorTab = tab.dataset.inspectorTab;
        renderInspectorState();
      });
    });

    $('#projectSelect')?.addEventListener('change', (event) => {
      if (event.target.value && event.target.value !== state.currentVideoId) void loadProject(event.target.value);
    });

    $('#markerList')?.addEventListener('click', (event) => {
      const check = event.target.closest('[data-marker-check]');
      if (check) {
        event.stopPropagation();
        toggleMarkerSelect(check.dataset.markerCheck);
        return;
      }
      const row = event.target.closest('[data-marker-id]');
      if (row) selectMarker(row.dataset.markerId);
    });

    $('#markerSelectAll')?.addEventListener('change', toggleMarkerSelectAll);

    $('#timelineMarkers')?.addEventListener('click', (event) => {
      const pin = event.target.closest('[data-marker-id]');
      if (pin) {
        event.stopPropagation();
        selectMarker(pin.dataset.markerId);
      }
    });

    bindTimelineMarkerDrag();

    $('#suggestionList')?.addEventListener('click', (event) => {
      const row = event.target.closest('[data-suggest-frame]');
      if (row) adoptSuggestion(Number(row.dataset.suggestFrame));
    });

    ['#timelineTrack', '#timelineRuler'].forEach((selector) => {
      $(selector)?.addEventListener('click', (event) => {
        if (event.target.closest('[data-marker-id]')) return;
        const rect = event.currentTarget.getBoundingClientRect();
        const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
        setCurrentFrame(Math.round(ratio * (state.frameCount - 1)));
      });
    });

    $('.chart-svg')?.addEventListener('click', (event) => {
      const rect = event.currentTarget.getBoundingClientRect();
      const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
      setCurrentFrame(Math.round(ratio * (state.frameCount - 1)));
    });

    $('#markerLabel')?.addEventListener('input', (event) => updateSelectedMarker('label', event.target.value));
    $('#markerComment')?.addEventListener('input', (event) => updateSelectedMarker('comment', event.target.value));

    $$('.speed-option, #speedMenu button').forEach((button) => button.addEventListener('click', () => setSpeed(button.dataset.speed)));

    $('#viewerStage')?.addEventListener('click', (event) => {
      if (state.activeTool === 'marker' && event.target.closest('.pose-canvas')) addMarker();
    });

    bindStageZoomControls();
    bindVideoEvents();

    document.addEventListener('click', (event) => {
      const speedControl = $('.speed-control');
      if (speedControl && !speedControl.contains(event.target)) $('#speedMenu')?.classList.remove('is-open');
    });

    document.addEventListener('keydown', (event) => {
      const editing = event.target.closest?.('input, textarea, select, [contenteditable="true"]');
      if (editing) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault();
        if (event.shiftKey) redoMarkers(); else undoMarkers();
        return;
      }
      if (event.key === 'Escape') {
        // 终态任务抽屉可用 Esc 收起（进行中不受影响）
        dismissTask();
        return;
      }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        const delta = event.key === 'ArrowLeft' ? -1 : 1;
        stepFrame(event.shiftKey ? delta * 5 : delta);
        return;
      }
      if (event.key === ' ' || event.code === 'Space') {
        event.preventDefault();
        const existing = state.markers.find((marker) => marker.frameIndex === state.currentFrame);
        if (existing) {
          state.selectedMarkerId = existing.id;
          deleteSelectedMarker();
        } else {
          addMarker();
        }
        return;
      }
      if (event.key.toLowerCase() === 'k') {
        event.preventDefault();
        togglePlayback();
      }
      if (event.key.toLowerCase() === 'm') {
        state.activeTool = 'marker';
        renderToolState();
      }
      if (event.key.toLowerCase() === 'v') {
        state.activeTool = 'select';
        renderToolState();
      }
    });

    if (window.KineFormEvents?.onAnalyzeVideo) {
      detachAnalyzeVideoMenu = window.KineFormEvents.onAnalyzeVideo(() => { void startAnalysisFlow(); });
    }
  }

  async function init() {
    const config = window.KineFormConfig || {};
    state.api = KineFormContract.createApiClient({
      baseUrl: config.apiBaseUrl || '',
      fetchImpl: typeof window.fetch === 'function' ? window.fetch.bind(window) : null,
    });
    bindEvents();
    render();
    await probeService();
    if (state.service.mode === 'live' && config.apiBaseUrl) {
      await loadProjectList();
      void restoreAnalysisTask();
    } else {
      await loadDemoProject();
    }
    window.__kineform = { state, buildSubmitPayload, submitAnalysis, startAnalysisFlow };
  }

  window.addEventListener('beforeunload', () => {
    stopPlayback();
    stopVideoFrameSync();
    clearTaskTimers();
    clearAnalysisTimers();
    detachAnalyzeVideoMenu?.();
  });
  document.addEventListener('DOMContentLoaded', () => { void init(); });
})();

