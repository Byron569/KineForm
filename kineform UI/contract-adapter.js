(function attachKineFormContract(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.KineFormContract = api;
})(typeof window !== 'undefined' ? window : globalThis, () => {
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

  const ERROR_ACTIONS = {
    markers_empty: 'add-marker',
    unknown_video: 'open-project',
    frame_index_out_of_range: 'check-frame',
    video_not_found: 'pick-video',
    video_invalid: 'pick-video',
    duplicate_video: 'poll-existing',
    queue_full: 'retry',
    task_not_found: 'restart',
    task_finished: 'refresh-task',
  };

  function asFiniteNumber(value, fallback = null) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function normalizeMotion(raw) {
    if (!raw || !Array.isArray(raw.frames)) throw new TypeError('motion.frames must be an array');
    const frames = raw.frames.map((frame, index) => ({
      ...frame,
      frameIndex: index,
      timestampMs: asFiniteNumber(frame?.timestampMs),
      metrics: { ...(frame?.metrics || {}) },
    }));
    return {
      ...raw,
      schema_version: String(raw.schema_version || '1.0'),
      video_id: String(raw.video_id || 'unknown-video'),
      source_video: String(raw.source_video || 'source_cfr.mp4'),
      fps: asFiniteNumber(raw.fps, 0),
      frame_count: frames.length,
      width: asFiniteNumber(raw.width, 0),
      height: asFiniteNumber(raw.height, 0),
      created_at: String(raw.created_at || new Date(0).toISOString()),
      frames,
    };
  }

  function normalizeEvents(raw) {
    const document = Array.isArray(raw) ? { events: raw } : (raw || {});
    return {
      ...document,
      schema_version: String(document.schema_version || '1.0'),
      events: Array.isArray(document.events) ? document.events : [],
    };
  }

  function getFrameTimestamp(motion, frameIndex) {
    const frame = motion?.frames?.[Number(frameIndex)];
    return frame ? asFiniteNumber(frame.timestampMs) : null;
  }

  function buildAnnotationsDocument({ videoId, fps, markers, projectName, schemaVersion = '1.0' }) {
    const document = {
      schema_version: schemaVersion,
      video_id: String(videoId),
      fps: asFiniteNumber(fps, 0),
      markers: (Array.isArray(markers) ? markers : []).map((marker) => ({
        id: String(marker.id),
        frameIndex: Number(marker.frameIndex),
        timestampMs: asFiniteNumber(marker.timestampMs),
        label: String(marker.label || ''),
        comment: String(marker.comment || ''),
        createdAt: String(marker.createdAt || ''),
        updatedAt: String(marker.updatedAt || marker.createdAt || ''),
      })),
    };
    // 项目命名持久化：只在校名非空时落盘（后端 annotations 保存 allow extra 字段）
    if (projectName) document.project_name = String(projectName);
    return document;
  }

  function buildSubmitPayload({ motion, markers, motionSource = 'motion.json', motionSha256 }) {
    const normalizedMotion = normalizeMotion(motion);
    const payload = {
      video_id: normalizedMotion.video_id,
      fps: normalizedMotion.fps,
      frame_count: normalizedMotion.frame_count,
      markers: (Array.isArray(markers) ? markers : []).map((marker) => {
        const frameIndex = Number(marker.frameIndex);
        const sourceFrame = normalizedMotion.frames[frameIndex];
        return {
          id: String(marker.id),
          frameIndex,
          timestampMs: getFrameTimestamp(normalizedMotion, frameIndex),
          label: String(marker.label || ''),
          comment: String(marker.comment || ''),
          metrics: { ...(sourceFrame?.metrics || marker.metrics || {}) },
        };
      }),
      motion: { source: String(motionSource) },
    };
    if (motionSha256) payload.motion.sha256 = String(motionSha256);
    return payload;
  }

  function parseVersion(version) {
    const match = String(version || '').match(/^(\d+)\.(\d+)\.(\d+)$/);
    return match ? match.slice(1).map(Number) : null;
  }

  function isVersionCompatible(clientVersion, serviceVersion) {
    const client = parseVersion(clientVersion);
    const service = parseVersion(serviceVersion);
    if (!client || !service) return { compatible: false, patchMismatch: false };
    const compatible = client[0] === service[0] && client[1] === service[1];
    return { compatible, patchMismatch: compatible && client[2] !== service[2] };
  }

  function mapApiError(status, body = {}) {
    const code = String(body?.error?.code || `http_${status}`);
    return {
      status,
      code,
      message: String(body?.error?.message || '分析服务暂时不可用'),
      taskId: body?.task_id ? String(body.task_id) : null,
      action: ERROR_ACTIONS[code] || 'retry',
    };
  }

  function createApiClient({ baseUrl = '', fetchImpl = globalThis.fetch } = {}) {
    const rootUrl = String(baseUrl).replace(/\/+$/, '');
    if (typeof fetchImpl !== 'function') throw new TypeError('fetchImpl must be a function');

    async function request(path, options = {}) {
      const headers = { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) };
      const response = await fetchImpl(`${rootUrl}${path}`, { ...options, headers });
      let body = null;
      try { body = await response.json(); } catch { body = null; }
      if (!response.ok) {
        const error = new Error(body?.error?.message || `HTTP ${response.status}`);
        error.api = mapApiError(response.status, body || {});
        throw error;
      }
      return body;
    }

    return {
      health: () => request('/api/health'),
      submit: (payload) => request('/api/analysis/submit', { method: 'POST', body: JSON.stringify(payload) }),
      startAnalysis: (videoPath, projectName) => request('/api/analysis/start', { method: 'POST', body: JSON.stringify({
        video_path: String(videoPath),
        ...(projectName ? { project_name: String(projectName) } : {}),
      }) }),
      tasks: () => request('/api/tasks'),
      task: (taskId) => request(`/api/tasks/${encodeURIComponent(taskId)}`),
      cancel: (taskId) => request(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' }),
      listProjects: () => request('/api/projects'),
      fetchMeta: (videoId) => request(`/api/projects/${encodeURIComponent(videoId)}/meta`),
      fetchMotion: (videoId) => request(`/api/projects/${encodeURIComponent(videoId)}/motion`),
      fetchEvents: (videoId) => request(`/api/projects/${encodeURIComponent(videoId)}/events`),
      fetchAnnotations: (videoId) => request(`/api/projects/${encodeURIComponent(videoId)}/annotations`),
      saveAnnotations: (videoId, document) => request(`/api/projects/${encodeURIComponent(videoId)}/annotations`, { method: 'PUT', body: JSON.stringify(document) }),
      fetchTaskResult: (taskId) => request(`/api/tasks/${encodeURIComponent(taskId)}/result`),
      videoUrl: (videoId) => `${rootUrl}/api/projects/${encodeURIComponent(videoId)}/video`,
      analysisUrl: (videoId) => `${rootUrl}/api/projects/${encodeURIComponent(videoId)}/analysis`,
    };
  }

  async function readProjectJson({ bridge, fetchImpl = globalThis.fetch, url, fileName, fallback }) {
    if (bridge?.readProjectFile) {
      try {
        const bridged = await bridge.readProjectFile(fileName);
        if (bridged) return typeof bridged === 'string' ? JSON.parse(bridged) : bridged;
      } catch (error) {
        console.warn(`Unable to read ${fileName} through the project bridge.`, error);
      }
    }
    if (typeof fetchImpl === 'function' && url) {
      try {
        const response = await fetchImpl(url);
        if (response.ok) return await response.json();
      } catch (error) {
        console.info(`Using demo fallback because ${url} is unavailable.`, error);
      }
    }
    return fallback;
  }

  async function loadProjectData({ bridge, fetchImpl = globalThis.fetch, motionUrl, eventsUrl, motionFallback, eventsFallback }) {
    const [motionRaw, eventsRaw] = await Promise.all([
      readProjectJson({ bridge, fetchImpl, url: motionUrl, fileName: 'motion.json', fallback: motionFallback }),
      readProjectJson({ bridge, fetchImpl, url: eventsUrl, fileName: 'events.json', fallback: eventsFallback }),
    ]);
    return { motion: normalizeMotion(motionRaw), events: normalizeEvents(eventsRaw) };
  }

  return {
    METRIC_KEYS,
    buildAnnotationsDocument,
    buildSubmitPayload,
    createApiClient,
    getFrameTimestamp,
    isVersionCompatible,
    loadProjectData,
    mapApiError,
    normalizeEvents,
    normalizeMotion,
  };
});
