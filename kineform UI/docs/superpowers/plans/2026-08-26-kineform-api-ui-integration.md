# KineForm API Contract UI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the static KineForm video annotation prototype into a contract-aligned demo that loads motion/events data, persists annotations, presents gait/report context, and models health/submission task states while preserving Google light-mode tokens.

**Architecture:** Keep the current single-screen HTML/CSS shell. Add a small browser/CommonJS-compatible `contract-adapter.js` for schema normalization, annotation envelopes, API error/version handling, and HTTP calls; add `demo-data.js` for contract-shaped fallback data; keep UI orchestration in `app.js`. The demo uses fallback data when no local project bridge or FastAPI service is available, while real Electron integration can provide `window.kineformBridge` and a dynamic API base URL later.

**Tech Stack:** Vanilla HTML, CSS, browser JavaScript, Node built-in `node:test`, no new runtime dependencies.

---

### Task 1: Contract adapter and test harness

**Files:**
- Create: `contract-adapter.js`
- Test: `contract-adapter.test.js`
- Modify: `index.html` to load the adapter before `app.js`

- [ ] Write failing tests for motion normalization, exact timestamp lookup, annotation envelope shape, version compatibility, API error-code mapping, and submit payload shape.
- [ ] Run `node --test contract-adapter.test.js` and confirm the tests fail because the adapter does not exist.
- [ ] Implement the smallest pure adapter API: `normalizeMotion`, `normalizeEvents`, `getFrameTimestamp`, `buildAnnotationsDocument`, `buildSubmitPayload`, `isVersionCompatible`, `mapApiError`, and `createApiClient`.
- [ ] Run the focused test and the full test command; confirm all pass.

### Task 2: Contract-shaped demo data and project loading

**Files:**
- Create: `demo-data.js`
- Modify: `app.js`

- [ ] Add a 450-frame demo motion model containing all contract metric keys, intentional `null` values, exact `timestampMs`, and a `gait_summary`/events fixture.
- [ ] Load `motion.json` and `events.json` through the optional Electron bridge or browser fetch, falling back to demo data without breaking the preview.
- [ ] Derive `video_id`, `fps`, `frame_count`, resolution, duration, and current-frame metrics from the loaded model.
- [ ] Preserve `null` metrics as gaps/`—` and use `frames[frameIndex].timestampMs` for every displayed and submitted timestamp.

### Task 3: Annotation envelope, dynamic events, gait and report UI

**Files:**
- Modify: `index.html`
- Modify: `styles.css`
- Modify: `app.js`

- [ ] Add inspector tabs for `步态详情` and `分析报告`, plus compact service/task status areas that use existing Google light tokens.
- [ ] Render contract event suggestions dynamically, including suggested styling and one-click adoption.
- [ ] Persist an `annotations.json`-shaped document through the optional bridge, with localStorage only as browser-demo fallback.
- [ ] Render gait summary cards, step context, reference z-band rows, fatigue trend, takeoff steps, and report mismatch warnings while hiding optional sections when absent.
- [ ] Keep the current editor density: show key frame metrics first and put the full 36-key data behind compact grouped sections.

### Task 4: Health, submit, poll, cancel and error states

**Files:**
- Modify: `index.html`
- Modify: `styles.css`
- Modify: `app.js`

- [ ] Probe `/api/health` on startup and render ready/demo/unavailable/version-warning states.
- [ ] Submit the exact `video_id`, fps, frame count, marker snapshots, and `motion` metadata to `/api/analysis/submit`.
- [ ] Poll `/api/tasks/{task_id}` every 0.5–1s until `succeeded`, `failed`, or `cancelled`; support `cancelling` and a visible cancel action.
- [ ] Handle stable error codes including duplicate task, queue full, task not found after restart, and finished task.
- [ ] Use a deterministic mock task only when the local API is unavailable, so the static preview remains reviewable.

### Task 5: Verification and visual review

**Files:**
- Modify only if verification finds a regression.

- [ ] Run `node --test contract-adapter.test.js` and `node --check app.js`.
- [ ] Use the browser to confirm the app loads with no console errors, service status is visible, marker adoption updates the count/timeline, task progress reaches a terminal state, and gait/report tabs render.
- [ ] Confirm Google light-mode requirements: #4285F4 primary, near-white surfaces, #EBEBEB borders, 8px baseline radius, DM Sans UI values, JetBrains Mono technical values, and no elevated shadows.

**Known boundary:** This prototype cannot directly read arbitrary local folders or launch Electron/FastAPI. The adapter therefore supports the production bridge/API contract and provides deterministic local demo fallbacks for browser review.
