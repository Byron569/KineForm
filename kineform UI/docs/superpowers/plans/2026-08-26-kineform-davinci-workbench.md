# KineForm DaVinci Workbench Implementation Plan

> **For agentic workers:** This plan is executed inline in the current session. The deliverable is a reviewable static HTML prototype, not the Electron/FastAPI integration.

**Goal:** Build a light, Google Design Skill-aligned, DaVinci Resolve-inspired KineForm motion-analysis workbench that makes video-frame review, pose metrics, marker annotation, suggested events, chart inspection, and timeline navigation immediately understandable.

**Architecture:** Use a zero-build static app with `index.html`, `styles.css`, and `app.js`. Keep the visual shell and token definitions in CSS, keep all prototype state and interactions in one small vanilla-JS controller, and use copied SVG icons from the Google Design Skill asset pack. Model marker state after `annotations.json`; model frame state after `motion.json` and always update display time from the frame table.

**Tech Stack:** HTML, CSS, vanilla JavaScript, inline SVG for the pose/chart visualization, Google Design tokens from the supplied skill archive, copied SVG icon assets.

---

### Task 1: Copy design assets and create the static shell

**Files:**
- Create: `assets/icons/*.svg` from the supplied Google Design Skill archive
- Create: `index.html`

- [x] Copy the supplied SVG icons into `assets/icons/` and reference them by file path.
- [x] Create a semantic shell with topbar, tool rail, viewer, inspector, chart panel, transport bar, timeline, and toast regions.
- [x] Include real Chinese product copy from the API contract: project/video identity, current-frame metrics, markers, suggested events, submit state, and keyboard hints.

### Task 2: Implement the Google/KineForm visual system

**Files:**
- Create: `styles.css`

- [x] Define Google light analytical tokens: `#ffffff` / `#f9f9fa` / `#eff1f4` surfaces, `#ebebeb` borders, `#0e1115` primary text, `#7f8d9f` muted text, `#4285f4` interaction, and chart colors `#4285f4`, `#ea4335`, `#fbbc05`, `#0043ad`, `#34a853`.
- [x] Use DM Sans for interface copy and JetBrains Mono for frame/timecode/metric data; use the 8px baseline radius, `3.84px` spacing rhythm, thin borders, and zero-elevation surfaces from the supplied tokens.
- [x] Make the composition responsive down to a compact view while preserving the desktop editing hierarchy.
- [x] Style marker states distinctly: selected, suggested, and regular.

### Task 3: Add motion-analysis interactions

**Files:**
- Create: `app.js`

- [ ] Maintain `currentFrame`, `fps`, `frames[]`, and `markers[]` state; use `frames[frameIndex].timestampMs` for displayed timecode.
- [ ] Implement previous/next frame, Shift ±5 frames, K play/pause, Space add marker, timeline scrubbing, chart series toggles, zoom controls, and speed menu.
- [ ] Implement marker selection, marker creation, suggested-event adoption, marker deletion, and annotation comment editing.
- [ ] Implement local prototype save status and a submit toast that reports the intended `POST /api/analysis/submit` payload shape without making a network request.
- [ ] Keep keyboard shortcuts disabled while the label/comment inputs are focused.

### Task 4: Verify the reviewable artifact

**Files:**
- Verify: `index.html`, `styles.css`, `app.js`, `assets/icons/*.svg`

- [ ] Serve the directory with a local HTTP server and load the page in a browser.
- [ ] Verify no missing asset requests, no console errors, and correct initial 1440×900 layout.
- [ ] Exercise frame stepping, playback, marker creation, suggestion adoption, chart toggles, timeline scrubbing, and submit feedback.
- [ ] Re-read the API contract against the implemented state model and report any intentionally prototype-only behavior.
