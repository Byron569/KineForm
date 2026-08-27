# KineForm 标注客户端接口契约

版本：1.0（2026-08-26）
适用：自研 Electron + Vue3 标注客户端（基于 ks233/video-annotator，MIT 协议）与 Python 分析侧的数据对接。
Python 侧实现：[writers.py](file:///d:/KineForm/sports_pose_analyzer/app/exporters/writers.py) `export_motion_json`，管线接入点：[orchestrator.py](file:///d:/KineForm/sports_pose_analyzer/app/pipeline/orchestrator.py)。

---

## 1. 数据流总览

```
Python 分析管线（现有，已完成）
  └─ 项目目录 outputs/<project_name>/
       ├─ analysis.mp4          骨架叠加视频（客户端播放）
       ├─ analysis_skeleton.mp4 纯骨架视频
       ├─ motion.json           ★ 时序指标数据（本契约）
       ├─ events.json           自动检测事件（可选，预填打点建议）
       └─ manifest.json / metrics.csv / report.html

标注客户端（已建成，Electron + Vue3，数据全走 HTTP）
  ├─ 项目列表 / motion / events / annotations / 视频均经资源端点加载（§4.7）
  ├─ 教练打点 → PUT /api/projects/{video_id}/annotations 持久化 annotations.json（§4.7）
  ├─ 视频姿态分析 → POST /api/analysis/start（§4.8）→ 管线产出新项目目录（motion.json / events.json / analysis.mp4…）
  │     └─ succeeded 后前端刷新项目列表（GET /api/projects，§4.7）加载新项目
  └─ 提交分析 → POST /api/analysis/submit → Python 本地服务（backend/，已实现 v0.1.0，契约见 §4）
       ├─ 任务落盘 submitted_markers.json / score_report.json（§6）
       └─ GET /api/tasks/{task_id} 轮询至终态（§4.2）→ succeeded 后经 GET /api/tasks/{task_id}/result 读取 score_report.json（§4.7）
```

## 2. motion.json（客户端只读输入）

每次分析完成后由管线自动生成在项目目录内。

### 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 当前 `"1.0"` |
| `video_id` | string | 项目目录名（唯一标识，提交时原样带回） |
| `source_video` | string | 恒为 `"source_cfr.mp4"`（CFR 标准化后的源） |
| `fps` | number | 帧率，保留 3 位小数（如 29.97） |
| `frame_count` | int | 帧总数 = `frames.length` |
| `width` / `height` | int | 分辨率（像素） |
| `created_at` | string | ISO-8601 分析时间 |
| `frames` | array | 逐帧记录，`frames[i].frameIndex == i` |

### 单帧记录

```json
{
  "frameIndex": 80,
  "timestampMs": 2669.3,
  "metrics": {
    "left_knee_angle": 142.13,
    "left_knee_angvel": -210.5,
    "pose_quality": 0.9412,
    "...": "见下表"
  }
}
```

metrics 全部 34 个键（无效帧为 `null`，**不是 0**）：

| 分组 | 键 | 单位 |
|---|---|---|
| 关节角 ×8 | `{left\|right}_{knee\|hip\|ankle\|elbow}_angle` | 度 [0,180] |
| 关节角速度 ×8 | `{left\|right}_{knee\|hip\|ankle\|elbow}_angvel` | 度/秒 |
| 躯干倾角 | `torso_lean_angle`（正=向图像右倾） | 度 |
| 节段角 ×4 | `left/right_thigh_angle`（髋→膝相对水平，前上为正）、`left/right_shank_angle`（膝→踝相对竖直，前倾为正） | 度 |
| 肩角 ×2 | `left/right_shoulder_angle`（Hanley 解剖约定：0°=站立下垂，前摆为正，后摆为负） | 度 |
| 骨盆（近似重心） | `pelvis_x` / `pelvis_y` / `pelvis_speed_px_s` | px / px/s |
| 头部 | `head_x` / `head_y` | px |
| 脚跟 | `left_heel_x/y`、`right_heel_x/y` | px |
| 质量 | `pose_quality`（0..1）、`valid_ratio`（0..1） | — |

### 帧对齐规则（重要）

- **跳帧一律用 `frames[i].timestampMs` 查表设置 `video.currentTime`，禁止用 `frameIndex / fps` 自行换算**——29.97 等非整数帧率会累积漂移。
- `timestampMs` 精度 0.1ms，角度/轨迹精度 2 位小数。
- 打点帧的指标取法：`motion.frames[frameIndex].metrics`，直接索引，无需查找。

## 3. annotations.json（客户端读写，经服务端持久化）

与视频/项目绑定，实际存放路径 = 服务端项目目录 `outputs/<video_id>/annotations.json`；前端读写均走 §4.7 资源端点（GET 读取、PUT 保存），无 bridge / 本地文件直写依赖。下次打开同视频经 GET 自动加载（404 `annotations_not_found` 时空白起步）。

```json
{
  "schema_version": "1.0",
  "video_id": "2026-08-26_103000_test_running",
  "fps": 29.97,
  "markers": [
    {
      "id": "m_aB3xK9",
      "frameIndex": 80,
      "timestampMs": 2669.3,
      "label": "起跳瞬间",
      "comment": "右脚蹬离地面",
      "createdAt": "2026-08-26T11:00:00",
      "updatedAt": "2026-08-26T11:05:00"
    }
  ]
}
```

- `id`：客户端生成（nanoid），拖拽改时间、改标签时保持不变；
- `frameIndex` 与 `timestampMs` 必须同步更新（以 `timestampMs = motion.frames[frameIndex].timestampMs` 为准）；
- 删除打点 = 从数组移除（客户端自行实现撤销栈）。

## 4. 服务 API（P0）

后端形态：**FastAPI 本地服务**（`backend/`，**已实现，版本 0.1.0**），由 Electron 主进程拉起（`127.0.0.1` 动态端口），保持完全离线；运行与集成形态见 §8。端点分两组：任务组 6 个——提交（§4.1）、任务详情轮询（§4.2）、取消（§4.3）、任务列表（§4.4）、健康探测（§4.5）、视频分析启动（§4.8）；项目资源组 9 个（§4.7，前端数据加载入口）。错误体统一（§4.6）。

### 4.1 POST /api/analysis/submit（提交分析）

#### 请求

`POST http://127.0.0.1:<port>/api/analysis/submit`
`Content-Type: application/json`

```json
{
  "video_id": "2026-08-26_103000_test_running",
  "fps": 29.97,
  "frame_count": 450,
  "markers": [
    {
      "id": "m_aB3xK9",
      "frameIndex": 80,
      "timestampMs": 2669.3,
      "label": "起跳瞬间",
      "comment": "右脚蹬离地面",
      "metrics": {
        "left_knee_angle": 142.13,
        "right_knee_angle": 138.7,
        "pelvis_y": 372.4,
        "pose_quality": 0.9412
      }
    }
  ],
  "motion": {
    "source": "path/to/motion.json",
    "sha256": "…（可选，校验数据一致性）"
  }
}
```

- `markers[].metrics`：该帧指标快照，字段与 motion.json 完全同名，由客户端从 `motion.frames[frameIndex].metrics` 原样复制（服务端也可以只收 frameIndex 自己查表，此处冗余是为离线排查方便）。

#### 服务端处理（P0 执行体）

1. **同步校验**：`markers` / `video_id` / `frameIndex`（规则见下方 400 错误码）；
2. **打点持久化**：请求原样**覆盖写入**项目目录 `outputs/<video_id>/submitted_markers.json`（§6.1）；
3. **生成基础报告** `outputs/<video_id>/score_report.json`（§6.2）：逐 marker 帧指标快照 + 所属步态步特征 + 邻近事件上下文 + gait 摘要。

其中 2–3 在受理后的异步任务内执行。动作分段/评分模型（待建）——模型就绪后仅替换任务内部执行体，本章请求/响应契约与 §6 产物结构不变。

#### 同步校验错误（400）

```json
{"error": {"code": "markers_empty", "message": "中文错误说明"}}
```

| code | 触发条件 |
|---|---|
| `markers_empty` | `markers` 为空数组 |
| `unknown_video` | `video_id` 在服务端无对应项目目录 |
| `frame_index_out_of_range` | 任一 `frameIndex` 越界 |

- `video_id` 合法性以**服务端**项目目录为准：`outputs/<video_id>/` 存在且含 `motion.json`；
- `frameIndex` 合法范围以**服务端** motion.json 的 `frame_count` 为准（`0 ≤ frameIndex < frame_count`）。

#### 任务冲突（409）

| code | 触发条件 | 附带字段 |
|---|---|---|
| `duplicate_video` | 同 `video_id` 已有活跃任务（status ∈ `queued` / `running` / `cancelling`） | `task_id`：既有任务 id |
| `queue_full` | 排队位满（并发上限 = 1 运行 + 1 排队） | — |

```json
{"error": {"code": "duplicate_video", "message": "…"}, "task_id": "t_20260826_110001"}
```

- 收到 `duplicate_video` 后客户端应转为轮询既有任务（§4.2），不要重复提交。

#### 响应

```json
{
  "status": "accepted",
  "task_id": "t_20260826_110001",
  "result_path": "outputs/<video_id>/score_report.json"
}
```

- HTTP 202：已受理（分析异步执行），客户端转为轮询任务（§4.2）直至终态；
- `result_path` 为**预定**的报告路径——任务到达 `succeeded` 前读取无意义；succeeded 后报告经 §4.7 result 端点获取，`result_path` 仅展示用途。

### 4.2 GET /api/tasks/{task_id}（任务详情轮询）

`GET http://127.0.0.1:<port>/api/tasks/{task_id}`

#### 响应（200）

```json
{
  "task_id": "t_20260826_110001",
  "video_id": "2026-08-26_103000_test_running",
  "type": "report",
  "status": "running",
  "stage": "…",
  "percent": 60,
  "detail": "…",
  "error": null,
  "result_path": "outputs/<video_id>/score_report.json",
  "created_at": "2026-08-26T11:00:01",
  "started_at": "2026-08-26T11:00:01",
  "finished_at": null
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` / `video_id` | string | 任务 / 项目标识 |
| `type` | string | 任务类型：`report`（打点报告，§4.1）/ `analyze`（视频分析，§4.8）；additive 新增字段，旧消费者应忽略未知值 |
| `status` | string | 任务状态，枚举见下表 |
| `stage` | string\|null | 当前执行阶段标识（展示用） |
| `percent` | number\|null | 进度百分比 0–100 |
| `detail` | string\|null | 进度的中文描述（展示用） |
| `error` | string\|null | 失败原因；仅 `failed` 非 null |
| `result_path` | string | 预定报告路径（同 §4.1 响应） |
| `created_at` / `started_at` / `finished_at` | string\|null | ISO-8601：受理 / 开始执行 / 到达终态时间；未发生为 null |

status 枚举：

| status | 含义 |
|---|---|
| `queued` | 排队中（并发位被占用，等待执行） |
| `running` | 执行中 |
| `cancelling` | 已请求取消，等待执行体到检查点 |
| `succeeded` | 成功：report 任务报告已生成，经 `GET /api/tasks/{task_id}/result`（§4.7）读取；analyze 任务产物获取见 §4.8 |
| `failed` | 失败：`error` 含原因 |
| `cancelled` | 已取消 |

状态机（终态：`succeeded` / `failed` / `cancelled`）：

```
queued ──→ running ──→ succeeded
   │           │  └──→ failed
   │           ↓
   │      cancelling ──→ cancelled
   └────────────────────────→ cancelled
```

- 前端建议轮询间隔 **0.5–1s**，到达终态即停止；
- 任务表为进程内存态，**服务重启后清空**（见 §8）：此前非终态的任务轮询将收到 404，前端应提示「服务已重启，请重新提交」；
- 404 响应体：`{"error": {"code": "task_not_found", "message": "…"}}`。

### 4.3 POST /api/tasks/{task_id}/cancel（取消任务）

#### 响应（200）

```json
{"task_id": "t_20260826_110001", "status": "cancelling"}
```

- `status` 为受理取消后的当前状态：非终态任务成功受理后为 `cancelling`；
- `cancelling → cancelled` 依赖执行体到达检查点，**非瞬时**，需继续轮询 §4.2 至终态；
- **幂等**：对 `cancelling` 态任务重复 cancel 返回 200，状态不变（仍 `cancelling`）；
- 终态任务（`succeeded` / `failed` / `cancelled`）→ 409 `{"error": {"code": "task_finished", "message": "…"}}`；
- 任务不存在 → 404 `task_not_found`。

### 4.4 GET /api/tasks（任务列表）

```json
{"tasks": ["…元素结构同 §4.2 单任务响应…"], "queue_length": 1}
```

- `tasks`：任务对象数组，字段同 §4.2 响应；
- `queue_length`：当前排队中（`queued`）任务数。

### 4.5 GET /api/health（就绪探测）

```json
{"status": "ok", "service_version": "0.1.0", "busy": false}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | string | `"ok"` = 服务就绪 |
| `service_version` | string | 服务端版本（`主.次.patch` 三段） |
| `busy` | boolean | 服务忙标志 |

- 前端启动时调用本端点做**就绪探测**（Electron 拉起服务后轮询至 `status == "ok"`）与**版本比对**；
- 版本比对规则：客户端内置版本与 `service_version` ——**主版本或次版本不一致 → 阻断**（提示版本不匹配，禁止使用）；**patch 不一致 → 警告**（可继续使用）。

### 4.6 统一错误体

所有 4xx / 5xx 响应体均为：

```json
{"error": {"code": "…", "message": "…"}}
```

- `code`：**稳定机器码**，客户端据此做逻辑分支；
- `message`：中文人读描述，仅供展示，不得用于逻辑判断。

P0 错误码汇总：

| code | HTTP | 端点 | 场景 |
|---|---|---|---|
| `markers_empty` | 400 | submit | `markers` 为空数组 |
| `unknown_video` | 400 | submit | `video_id` 无服务端项目目录 |
| `frame_index_out_of_range` | 400 | submit | `frameIndex` 越界 |
| `duplicate_video` | 409 | submit | 同 `video_id` 已有活跃任务（响应体附带 `task_id`） |
| `queue_full` | 409 | submit | 排队位满（1 运行 + 1 排队） |
| `task_not_found` | 404 | tasks 系列 | 任务不存在（含服务重启后任务表已清空） |
| `task_finished` | 409 | cancel | 任务已处于终态 |
| `project_not_found` | 404 | projects 资源组 | `video_id` 无项目目录 / 无 motion.json / 含穿越片段（§4.7） |
| `events_not_found` | 404 | projects/events | 该项目无 events.json |
| `annotations_not_found` | 404 | projects/annotations GET | 该项目无 annotations.json（前端空白起步） |
| `video_id_mismatch` | 400 | projects/annotations PUT | 请求体 `video_id` 与路径参数不一致 |
| `video_not_found` | 404 | projects/video、analysis | 对应视频文件缺失 |
| `task_not_finished` | 409 | tasks/result | 任务状态非 `succeeded` |
| `report_not_found` | 404 | tasks/result | 任务已成功但 score_report.json 不在盘 |
| `video_not_found` | 400 | start | `video_path` 指向的文件不存在（§4.8；与上文资源组同名码按端点与 HTTP 状态区分） |
| `video_invalid` | 400 | start | `video_path` 非字符串/为空，或扩展名不在白名单（§4.8） |
| `meta_not_found` | 404 | projects/meta | 项目存在但无 meta.json（旧项目）——前端回退显示默认值 |

### 4.7 项目资源端点（前端数据加载入口，已实现）

前端数据全走 HTTP API（本组端点 + 任务组 §4.1–§4.5、§4.8），无 bridge 依赖、无本地文件直读；demo 模式（未注入 `apiBaseUrl`，即无 `window.KineFormConfig`）仅用 localStorage，不访问任何端点。数据根与 submit 一致（`OUTPUTS_DIR`，见 §8.1）；JSON 资源**原样字节返回**（FileResponse 流式，不重序列化），视频走 FileResponse 原生 Range/206。

#### GET /api/projects（项目枚举）

仅枚举 `OUTPUTS_DIR` 一级子目录中**含 motion.json** 者（有效项目判据），按 `video_id` 倒序：

```json
{"projects": [{"video_id": "2026-08-26_103000_test_running", "fps": 29.97, "frame_count": 450, "width": 1920, "height": 1080, "created_at": "2026-08-26T10:30:05", "has_events": true, "has_annotations": false}]}
```

- `has_events` / `has_annotations`：events.json / annotations.json 是否在盘，前端据此决定是否请求对应资源；
- 损坏（非 JSON 对象）的 motion.json 项目直接跳过，不报错。

#### GET /api/projects/{video_id}/motion

返回 motion.json **原样**内容（契约见 §2）。项目无效 → 404 `project_not_found`。

#### GET /api/projects/{video_id}/events

返回 events.json **原样**内容（契约见 §5）。该项目无该文件 → 404 `events_not_found`，前端按**无步态数据**处理（隐藏步态相关面板）。

#### GET /api/projects/{video_id}/annotations

返回 annotations.json **原样**内容（契约见 §3）。该项目无该文件 → 404 `annotations_not_found`，前端按**空白起步**处理。

#### GET /api/projects/{video_id}/meta

返回 `outputs/<video_id>/meta.json` **原样**内容——分析成功后由服务端写入（见 §4.8 产物）：

```json
{"source_video_name": "run_back.mp4", "project_name": "晨跑训练", "analyzed_at": "2026-08-27T10:00:00"}
```

- `source_video_name`：用户导入时的**原始文件名**（含扩展名，必得）；
- `project_name`：用户命名（**可选**——未命名时省略该键）；
- `analyzed_at`：分析完成的本地 ISO-8601 时间串。**已有 meta.json 会被分析覆盖更新**。
- 旧项目（本次改动前分析，无 meta.json）→ 404 `meta_not_found`，前端据此**回退显示默认值**（如用 `video_id` 或 motion 元数据），属预期。

#### PUT /api/projects/{video_id}/annotations（保存标注）

请求体 = §3 annotations.json 完整文档；服务端**全量覆盖写盘** `outputs/<video_id>/annotations.json`（不做合并，前端 500ms 防抖后调用）。

- `body.video_id` 与路径参数不一致 → 400 `video_id_mismatch`；
- 响应（200）：

```json
{"status": "saved", "path": "outputs/<video_id>/annotations.json"}
```

#### GET /api/projects/{video_id}/video 与 GET /api/projects/{video_id}/analysis

分别返回 `source_cfr.mp4`（CFR 标准化源视频）与 `analysis.mp4`（叠加骨架分析视频），`Content-Type: video/mp4`；FileResponse 原生支持 Range/206，`<video>` 拖动播放与逐帧 seek 直接可用（前端消费方式见 §7.5）。文件缺失 → 404 `video_not_found`。

#### GET /api/tasks/{task_id}/result（score_report 获取）

任务 `succeeded` 后返回 `outputs/<video_id>/score_report.json` **原样**内容（契约见 §6）。**仅服务 report 任务**（§4.1）；analyze 任务（§4.8）调用将得到 404 `report_not_found`，其产物获取方式见 §4.8。

- 任务不存在 → 404 `task_not_found`；
- 任务状态非 `succeeded`（含 queued / running / cancelling / failed / cancelled）→ 409 `task_not_finished`；
- 任务已成功但报告文件不在盘 → 404 `report_not_found`。

#### video_id 防穿越（全部 projects 端点共用）

`video_id` 含 `/`、`\`、`..`、`:`（Windows 盘符形式）或为空时，与「目录不存在 / 无 motion.json」**统一**返回 404 `project_not_found`（不区分，避免向客户端泄露目录结构）。校验发生在路径参数**解码后**的字符串上，路径编码（如 `%2e%2e%2f`）无法绕过。

### 4.8 POST /api/analysis/start（视频姿态分析任务）

应用内直接发起视频姿态分析：提交**本地视频文件路径**，服务端调用分析管线（sports_pose_analyzer）在项目根下产出新项目目录，此后与既有项目完全同构——经 §4.7 资源端点加载，教练打点与报告提交（§4.1）照常可用。

#### 请求

`POST http://127.0.0.1:<port>/api/analysis/start`
`Content-Type: application/json`

```json
{
  "video_path": "D:/Videos/test_running.mp4",
  "project_name": "晨跑训练"
}
```

- `video_path`：本地视频文件的**绝对路径**字符串；扩展名白名单 `mp4` / `mov` / `avi` / `mkv` / `webm` / `m4v`（大小写不敏感）。建议经 `window.KineFormDialog.openVideo()`（§8.2）原生对话框选取，避免手输路径拼写错误。
- `project_name`：**可选**用户命名（str | null）——非字符串 → 422 `validation_error` 兜底；省略 / null / 空串均视为**未命名**（不影响受理）。仅供服务端写入项目 meta.json（§4.7 meta 端点），随 `video_id` 在会话内持久化展示。

#### 同步校验错误（400）

| code | 触发条件 |
|---|---|
| `video_not_found` | `video_path` 指向的文件不存在 |
| `video_invalid` | `video_path` 非字符串/为空，或扩展名不在白名单 |

#### 任务冲突（409）

错误体结构与 §4.1 一致：

| code | 触发条件 | 附带字段 |
|---|---|---|
| `duplicate_video` | 同一视频已有活跃任务（status ∈ `queued` / `running` / `cancelling`） | `task_id`：既有任务 id |
| `queue_full` | 排队位满（1 运行 + 1 排队） | — |

- 去重键 = 源视频**绝对路径小写规范化**（Windows 路径大小写不敏感），与 report 任务的 `video_id` 去重键不同——分析任务与报告任务之间互不去重，但**共享同一队列**（GPU 推理互斥）；
- 收到 `duplicate_video` 后转为轮询既有任务（§4.2），不要重复提交。

#### 响应（202）

```json
{
  "status": "accepted",
  "task_id": "t_20260826_140001",
  "result_path": "projects/pending"
}
```

- 受理时新项目目录名（含时间戳）尚未产生，`result_path` 为占位值 `"projects/pending"`；任务 `succeeded` 后服务端将其**覆写**为 `projects/<项目目录名>`——目录名即新项目的 `video_id`，前端据此刷新项目列表（`GET /api/projects`，§4.7）并加载产物（motion.json / events.json / analysis.mp4）。

#### 轮询（复用 §4.2）

轮询方式、状态机、404 语义与 §4.2 完全一致，注意两点差异：

- 快照 `type` 为 `"analyze"`（§4.2 字段表）；
- 快照 `video_id` 在受理时即**源视频规范化路径**（非项目目录名），`succeeded` 后也不回写——新项目 `video_id` 一律从 `result_path`（`projects/` 之后的部分）提取，勿读 `video_id` 字段。

#### 运行时特性（前端预期管理）

- **耗时**：数分钟（GPU）至十几分钟（CPU），与视频时长正相关；
- **首次分析含模型加载 30–60s**：期间进度停在 0% 属预期，勿判定为卡死；
- **取消**（§4.3）：模型加载期内不即时响应，加载完成后的首个检查点生效；
- **watchdog**：running 且无进度超过 900s → `failed`（§4.2 通用规则对分析任务同样生效）。

#### 产物获取（防误用）

分析任务的产物是**新项目目录**而非单份报告文件：`succeeded` 后读快照 `result_path` 得到新项目 `video_id`，再经 §4.7 资源端点（项目列表 / motion / events / video / analysis）加载。**不要**调用 `GET /api/tasks/{task_id}/result`——该端点仅服务 report 任务（§4.7），对 analyze 任务调用将得到 404 `report_not_found`。

## 5. events.json（打点预填建议 + gait_summary 步态契约）

顶层结构 `{"schema_version": "1.0", "events": [...][, "gait_summary": {...}]}`。事件记录字段见 [data_models.py](file:///d:/KineForm/sports_pose_analyzer/app/common/data_models.py) `Event.to_dict`。

客户端可在加载时读取项目目录 events.json，把自动检测的事件（如骨盆最高点、最大躯干倾角）预填为「建议打点」（标记 `suggested: true`，样式区分），教练可一键采纳或忽略。

**步态事件（P0，Zeni 方法）**：事件类型 `left/right_touchdown`（触地）、`left/right_toe_off`（离地），value = 脚跟相对骨盆前后位置（px，正值 = 脚在前方），实现见 [gait.py](file:///d:/KineForm/sports_pose_analyzer/app/events/gait.py)。

### 5.1 gait_summary 总览（生产者 / 消费者 / 顶层字段）

- **生产者**：[orchestrator.py](file:///d:/KineForm/sports_pose_analyzer/app/pipeline/orchestrator.py) L175-222——`gait_temporal_params`（左右侧时空参数）+ `body_scale`（尺度归一化）+ `gait_step_features`（每步特征）+ `compare_steps_to_reference`（精英参考对比）+ `fatigue_trend`（疲劳趋势）+ `identify_takeoff_steps`（起跳步识别），整体经 `export_events_json` 写入 events.json 的 `gait_summary` 键。
- **消费者**：① GUI 对话框 `GaitDetailDialog`（[dialogs.py](file:///d:/KineForm/sports_pose_analyzer/app/ui/dialogs.py)，主窗口「步态详情…」按钮入口）；② Electron+Vue3 前端（本契约的服务对象）。

```json
{
  "schema_version": "1.0",
  "events": [ "…含 left/right_touchdown、left/right_toe_off…" ],
  "gait_summary": {
    "left":             { "…": "见 §5.2" },
    "right":            { "…": "见 §5.2" },
    "step_time_ms":     { "mean": 350.0, "std": 12.3, "min": 330.0, "max": 380.0, "count": 12 },
    "cadence_spm":      171.4,
    "body_scale":       { "…": "见 §5.4" },
    "steps":            [ { "…": "见 §5.3" } ],
    "reference_comparison": [ { "…": "见 §5.5" } ],
    "fatigue_trend":    { "…": "见 §5.6" },
    "takeoff_steps":    [ { "…": "见 §5.7" } ]
  }
}
```

| 字段 | 类型 | 单位 | 可空 | 说明 |
|---|---|---|---|---|
| `left` / `right` | object | — | 否 | 左右侧时空参数汇总，见 §5.2 |
| `step_time_ms` | object\|null | ms | 是 | 全局步时间（左右交替合并的相邻触地间隔），结构同 §5.2 统计块 |
| `cadence_spm` | number\|null | steps/min | 是 | 步频 = 60000 / step_time_ms.mean；样本不足为 null |
| `body_scale` | object | — | 否 | 身体尺度与速度，见 §5.4（内部值可 null） |
| `steps` | array | — | 否 | 每步特征（按 td_frame 升序），见 §5.3；无步态事件 = 空数组 |
| `reference_comparison` | array | — | 键可缺 | 精英参考 z-score 对比，见 §5.5；**仅 steps 非空时写入** |
| `fatigue_trend` | object\|null | — | 是 | 前/后半程对比，见 §5.6；步数 < 6 为 null |
| `takeoff_steps` | array | — | 否 | 跳高起跳步识别，见 §5.7；无起跳步 = 空数组 |

**统计块**（下文 `{mean,std,min,max,count}`）：数值保留 2 位小数，`count` 为样本数；样本不足时整个块为 `null`。

### 5.2 左右侧时空参数汇总（left / right）

| 字段 | 类型 | 单位 | 可空 | 说明 |
|---|---|---|---|---|
| `n_touchdowns` / `n_toe_offs` | int | 个 | 否 | 该侧触地/离地事件数 |
| `contact_time_ms` | object\|null | ms | 是 | 触地时间：TD 后第一个同侧 TO |
| `flight_time_ms` | object\|null | ms | 是 | 腾空时间：TO 后第一个同侧 TD |
| `stride_time_ms` | object\|null | ms | 是 | 步态周期：相邻同侧 TD 间隔 |
| `stance_ratio` | object\|null | % | 是 | 支撑比 ×100（触地/周期）；额外含 `mean_frac`（无量纲均值，4 位小数），便于直接对照文献支撑比 |

### 5.3 steps[]：每步事件条件化特征

结构见 [gait.py](file:///d:/KineForm/sports_pose_analyzer/app/events/gait.py) `gait_step_features`。按 `(td_frame, side)` 升序；角度单位度（1 位小数）、时间 ms（1 位小数）、`*_norm` 无量纲（像素/身高，4 位小数）。**角度缺失输出 `null`，不是 0**。行进方向自动检测（骨盆 x 首末）：左向跑时 thigh/shank/shoulder/foot_pelvis_dist 已自动翻转，语义与右向跑一致。末步（无下一次同侧触地）`next_td_frame`/`flight_time_ms`/`stride_time_ms`/`stance_ratio`/`flight_support_ratio` 为 null。

| 字段 | 类型 | 单位 | 可空 | 说明 |
|---|---|---|---|---|
| `side` | string | — | 否 | `left` / `right` |
| `td_frame` / `to_frame` | int | 帧 | 否 | 触地/离地帧号（与 motion.json `frameIndex` 同轴，可直接索引） |
| `next_td_frame` | int\|null | 帧 | 是 | 下一次同侧触地帧号；末步为 null |
| `contact_time_ms` | number | ms | 否 | 触地时间 |
| `flight_time_ms` / `stride_time_ms` | number\|null | ms | 是 | 腾空 / 步态周期时间 |
| `stance_ratio` | number\|null | 0..1 | 是 | 支撑比（触地帧数/周期帧数，4 位小数） |
| `flight_support_ratio` | number\|null | — | 是 | 腾空/支撑比 |
| `stride_length_px` | number\|null | px | 是 | 整周期骨盆水平位移（方向无关） |
| `stride_length_norm` | number\|null | 身高比 | 是 | 步长/身高；body_height_px 无效为 null |
| `stride_length_m` | number\|null | m | 是 | 仅提供真实身高（m_per_px）时输出 |
| `pelvis_vertical_range_px` / `_norm` | number\|null | px / 身高比 | 是 | 骨盆垂直振幅（整周期；末步仅支撑期） |
| `touchdown` | object | — | 否 | TD 快照（内嵌值可 null），见下表 |
| `midstance` | object\|null | — | 是 | 支撑期内 \|脚跟−骨盆 x\| 最小帧（Hanley 中足位 2D 近似）；找不到为 null |
| `toe_off` | object | — | 否 | TO 快照（内嵌值可 null） |
| `stance` | object | — | 否 | 支撑期特征（内嵌值可 null） |
| `swing` | object | — | 否 | 摆动期特征（内嵌值可 null；末步无摆动段） |

快照嵌套字段（各值均可 null）：

| 分组 | 键 | 单位 | 说明 |
|---|---|---|---|
| `touchdown` | `knee/hip/ankle_angle`、`torso_lean_angle`、`thigh/shank/shoulder/elbow_angle` | 度 | TD 帧角度快照；肩角为 Hanley 解剖约定（0°=站立下垂，前摆正/后摆负） |
| | `foot_pelvis_dist_px` / `foot_pelvis_dist_norm` | px / 身高比 | 触地帧脚跟相对骨盆前后距离（正 = 脚在前方）；跳高 CM-foot 距离同源指标 |
| | `foot_rel_vx_px_s` | px/s | 触地前 3 帧脚相对骨盆水平速度（负 = 触地前后向回摆，"主动扒地"代理） |
| `midstance` | `frame`、`knee/hip/ankle/shoulder/elbow_angle` | 帧 / 度 | 中足位快照 |
| `toe_off` | `knee/hip/ankle/shoulder/elbow_angle` | 度 | TO 帧快照 |
| `stance` | `min_knee_angle`、`knee_collapse_deg`、`knee/ankle/hip_rom_deg` | 度 | 支撑期：最小膝角、膝塌陷（TD 膝角 − 支撑期最小膝角）、各关节 ROM |
| `swing` | `min_knee_angle`、`max_thigh_angle` | 度 | 摆动期：最小膝角（midswing）、最大抬腿 |

### 5.4 body_scale（尺度归一化）

| 字段 | 类型 | 单位 | 可空 | 说明 |
|---|---|---|---|---|
| `body_height_px` | number\|null | px | 是 | 头顶→双踝中点像素距离中位数；所有 `*_norm` 的分母 |
| `leg_length_px` | number\|null | px | 是 | 髋→踝距离中位数（Miyashiro 腿长像素近似，屈膝帧略低估） |
| `m_per_px` | number（可选键） | m/px | 键可缺 | 仅当提供运动员真实身高（user_settings.json 的 `athlete_height_m` 或 CLI `--height`）时输出 |
| `speed_px_s` | number（可选键） | px/s | 键可缺 | 骨盆 x 最小二乘斜率（假设过地匀速；跑步机场景 ≈0）；仅骨盆轨迹有效时输出 |
| `speed_mps` | number（可选键） | m/s | 键可缺 | speed_px_s × m_per_px，依赖真实身高 |

### 5.5 reference_comparison[]（精英参考 z-score 对比）

实现见 [references.py](file:///d:/KineForm/sports_pose_analyzer/app/biomechanics/references.py) `compare_steps_to_reference`。**仅 steps 非空时写入**该键。每条对应一个参考库：自动对比库 `sprint_max_v`（Mattes 2021 短跑）、`marathon_m` / `marathon_f`（Hanley 2020 马拉松）；识别到起跳步时追加 `hj_takeoff_success`（Nicholson 2024 跳高）。`marathon_800m_f`（Hanley 2022）已收录但需赛段上下文，不自动对比。

| 字段 | 类型 | 说明 |
|---|---|---|
| `reference` | string | 参考库键 |
| `source` / `sample` | string | 文献出处 / 样本描述 |
| `angle_definition` | string | 该参考库的角度定义说明（见下方可比性规则） |
| `context` | string\|null | 仅上下文参考库（跳高/800m）附带的适用条件说明 |
| `disclaimer` | string | 统计分层与 2D 投影误差的免责说明 |
| `skipped_metrics` | object | `{指标路径: 不可比原因}`——被跳过指标的唯一登记处 |
| `steps` | array | `[{td_frame, side, metrics: {指标路径: {value, ref_mean, ref_sd, ref_range, z, band}}}]`；该步缺该指标时静默跳过 |
| `side_summary` | object | `{side: {指标路径: {mean_z, band, n}}}`，左右各自平均 z |
| `global` | object | 全局指标对比；目前仅 sprint_max_v 的 `cadence_hz`（全局步频 Hz） |

- 指标路径为点号嵌套：`touchdown.knee_angle`、`stance.min_knee_angle`、`swing.max_thigh_angle`、`contact_time_ms` 等，与 steps 字段一一对应。
- **z-score band 语义**（工程统计分层，非官方/医学阈值）：`z = (value − ref_mean) / ref_sd`（2 位小数）——
  - `common`：\|z\| ≤ 1
  - `deviated`：1 < \|z\| ≤ 2
  - `outlier`：\|z\| > 2
- 文献只给均值/范围而无 SD 的参考值（如 Hanley 马拉松多数值）：`z`/`band` 为 `null`，仅输出参考值——**null ≠ common，前端须区分渲染**。
- **angle_definition 与 skipped_metrics**：参考库自带角度定义；**角度定义与本项目不一致的指标不可比**（典型：马拉松踝角——Hanley 站立参考 ≈110° vs 本项目 knee-ankle-toe 站立 ≈90°），这类指标不进入 `steps[].metrics` 与 z 计算，原因登记在 `skipped_metrics`。前端不得对 skipped 指标自行计算偏差。

### 5.6 fatigue_trend（前/后半程疲劳趋势）

实现见 [fatigue.py](file:///d:/KineForm/sports_pose_analyzer/app/events/fatigue.py)。steps 按 td_frame 升序对半切分（奇数步前半多一步），**步数 < 6 时为 null**。只输出 delta，不做疲劳阈值判定（解读交由展示层）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `n_steps` / `split_at` | int | 总步数 / 前半步数（= 后半起始索引） |
| `halves` | object | `{first/second: {指标: 均值\|null}}`（1 位小数；某半无有效样本该指标为 null） |
| `delta` | object | `{指标: second − first}`，仅两半均有值的指标出现 |
| `delta_pct` | object | `{指标: (second−first)/first×100}`（%）；first 均值为 0 时不输出（除零保护） |

指标键沿用点号嵌套约定（同 §5.5）：`contact_time_ms`、`flight_time_ms`、`stride_time_ms`、`stance_ratio`、`pelvis_vertical_range_px`、`stride_length_px`、`touchdown.knee_angle`、`stance.min_knee_angle`、`stance.knee_collapse_deg`、`swing.min_knee_angle`、`swing.max_thigh_angle`、`touchdown.shoulder_angle`。正值 = 后程增大（Hanley 2020 方向性结论：疲劳后触地时间延长、摆动最小膝角增大约 5°）。

### 5.7 takeoff_steps[]（跳高起跳步识别）

实现见 [takeoff.py](file:///d:/KineForm/sports_pose_analyzer/app/events/takeoff.py)。判据（保守，宁漏报不误报）：末步（`next_td_frame` 为 null）且触地时间 > 1.4 × 全部有效步中位数，且有效步 ≥ 4。按 td_frame 升序；无起跳步 = 空数组。

| 字段 | 类型 | 单位 | 说明 |
|---|---|---|---|
| `td_frame` / `side` | int / string | 帧 | 起跳触地帧号与侧别 |
| `contact_time_ms` | number | ms | 该步触地时间 |
| `contact_median_ms` | number | ms | 全部有效步触地时间中位数 |
| `ratio` | number | — | contact_time_ms / contact_median_ms（3 位小数） |
| `confidence` | number | 0..1 | clamp(ratio / 2.8, 0, 1)——比值恰为阈值（1.4）时 0.5，达 2×阈值饱和为 1 |
| `reason` | string | — | 中文判据说明（供报告/界面直接展示） |

注意：视频若拍到落垫，落垫缓冲接触可能被误报为起跳步，前端展示时建议附 confidence 供人工甄别。

### 5.8 兼容规则（gait_summary 演进）

events.json 顶层 `schema_version` 当前为 `"1.0"`，`gait_summary` 为该版本内 additive 新增键：

1. **additive 兼容**：新增可选字段/可选键（值可为 null 或整个键缺失）——消费者**必须忽略未知键**、把缺失的可选键视为 null，不得因未知键报错。
2. **breaking 变更**：改名、删除已有字段、改变字段语义（含单位、角度约定、z-band 边界含义）——必须提升 events.json 的 `schema_version` 并由 Python 侧与客户端协商一致后才可切换；未经协商不得上线。
3. `gait_summary` 键整体可选：P0 之前的旧 events.json 无此键，消费者须容忍文件级缺失（GUI 降级隐藏入口，前端隐藏面板）。
4. 条件存在的键按「键可缺」处理：`reference_comparison` 仅 steps 非空时存在；`m_per_px`/`speed_px_s`/`speed_mps` 仅提供真实身高时存在；steps 各 `*_m`/`*_norm` 字段依赖对应尺度。

**客户端建议**：TD/TO 事件 + steps 的 midstance 可直接预填为建议打点；reference_comparison 适合做"偏离热力条"展示（每步 z 值着色，skipped_metrics 指标置灰）；fatigue_trend 适合做前/后半程对比条形图。

## 6. score_report.json 与 submitted_markers.json（P0 产物契约）

submit 受理后，任务在**服务端项目目录** `outputs/<video_id>/` 内产出两份 P0 产物：submitted_markers.json（打点留档）与 score_report.json（基础报告）。`score_report.json` 在任务到达 `succeeded`（§4.2）后，经 `GET /api/tasks/{task_id}/result`（§4.7）获取——`result_path` 字段仅展示用途，前端不经它读文件。

### 6.1 submitted_markers.json（打点留档）

同步校验通过后，服务端将提交内容原样留档——**每次提交覆盖写入**，记录「客户端到底提交了什么」，供离线排查：

```json
{
  "schema_version": "1.0",
  "task_id": "t_20260826_110001",
  "video_id": "2026-08-26_103000_test_running",
  "submitted_at": "2026-08-26T11:00:01",
  "markers": ["…请求体 markers 数组原样…"],
  "motion": {"…": "请求体 motion 对象原样"}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 当前 `"1.0"` |
| `task_id` | string | 受理本次提交的任务 id |
| `video_id` | string | 项目目录名 |
| `submitted_at` | string | ISO-8601 受理时间 |
| `markers` | array | 请求体 `markers` **原样**保存 |
| `motion` | object | 请求体 `motion` **原样**保存（含 `source` / `sha256`） |

### 6.2 score_report.json（基础报告）

#### 顶层字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | string | 当前 `"1.0"` |
| `task_id` | string | 生成本报告的任务 id |
| `video_id` | string | 项目目录名 |
| `created_at` | string | ISO-8601 报告生成时间 |
| `markers` | array | 逐打点记录，见下表 |
| `summary` | object | 汇总摘要，见下表 |

#### markers[] 元素

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` / `frameIndex` / `timestampMs` / `label` / `comment` | — | 打点信息，**请求原样** |
| `metrics` | object | 请求携带的该帧指标快照，**原样** |
| `metrics_checked` | object（可选键） | 服务端源数据校验：以 motion.json `frames[frameIndex].metrics` 为基准，与请求 `metrics` **逐键比对**，差值 > 0.01 的键记入 `mismatches`；完全一致时整个键省略 |
| `step` | object\|null | 该帧所属步：gait_summary.steps 中满足 `step.td_frame ≤ frameIndex < step.next_td_frame` 的元素快照（该侧末步 `next_td_frame = null` 时上界不限）；无 gait_summary / 无匹配步时 null。元素结构同 §5.3 |
| `event_context` | array\|null | 打点 **±2 帧**内的邻近自动事件（源自 events.json，事件类型见 §5）；无邻近事件时 null |

`event_context[]` 元素：

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | 事件类型（如 `left_touchdown`、`right_toe_off`） |
| `frame_index` | int | 事件帧号 |
| `timestamp_ms` | number | 事件时间戳（ms） |
| `delta_frames` | int | 事件帧 − 打点帧（有符号，±2 以内） |

#### summary 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `n_markers` | int | 打点总数 |
| `gait` | object\|null | gait 摘要，见下表；无 gait_summary 时 null |
| `fatigue_trend` | object\|null | `{n_steps, delta}`：疲劳趋势摘要（delta 为关键字段，源数据见 §5.6）；源为 null（步数 < 6）时 null |
| `takeoff_steps` | array\|null | 起跳步列表，元素同 §5.7；无 gait_summary 时 null |

`summary.gait` 字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `n_steps` | int | 步数（= gait_summary.steps 长度） |
| `cadence_spm` | number\|null | 步频（源 gait_summary.cadence_spm） |
| `contact_time_ms_mean` | number\|null | 触地时间均值 |
| `reference_comparison` | array | 每条 `{reference, 每侧 mean_z}`：自 §5.5 `side_summary` 提取的各侧平均 z（指标路径 → mean_z） |

#### 示例

```json
{
  "schema_version": "1.0",
  "task_id": "t_20260826_110001",
  "video_id": "2026-08-26_103000_test_running",
  "created_at": "2026-08-26T11:00:03",
  "markers": [
    {
      "id": "m_aB3xK9",
      "frameIndex": 80,
      "timestampMs": 2669.3,
      "label": "起跳瞬间",
      "comment": "右脚蹬离地面",
      "metrics": {"…": "请求 metrics 原样；与源数据一致时无 metrics_checked 键"},
      "step": {"…": "所属步快照，结构同 §5.3"},
      "event_context": [
        {"type": "right_toe_off", "frame_index": 81, "timestamp_ms": 2702.6, "delta_frames": 1}
      ]
    }
  ],
  "summary": {
    "n_markers": 1,
    "gait": {
      "n_steps": 12,
      "cadence_spm": 171.4,
      "contact_time_ms_mean": 128.5,
      "reference_comparison": [
        {"reference": "sprint_max_v", "left": {"…": "mean_z"}, "right": {"…": "mean_z"}}
      ]
    },
    "fatigue_trend": {"n_steps": 12, "delta": {"…": "关键字段，同 §5.6"}},
    "takeoff_steps": [{"…": "同 §5.7"}]
  }
}
```

- `metrics_checked` 仅在存在不一致键时出现，形态 `{"mismatches": {指标键: …}}`；
- 客户端建议：`metrics_checked` 不一致键在指标旁标注「源数据不一致」；`step` / `event_context` 作为打点详情面板的上下文信息展示。

### 6.3 兼容规则（产物演进）

本节两份产物均为 **v1 additive 承诺**（同 §5.8 精神）：

1. **additive 兼容**：v1 内新增可选字段/可选键（值可为 null 或整键缺失）——消费者必须忽略未知键、把缺失的可选键视为 null，不得因未知键报错；
2. **breaking 变更**：改名、删除已有字段、改变字段语义（含单位、精度、null 语义、step 匹配规则、±2 帧事件窗口）——必须提升对应文件的 `schema_version`，由 Python 侧与客户端协商一致后才可切换，未经协商不得上线。

## 7. 已知约定与坑（前端实现必读）

1. **fps 非整数**：见 §2 帧对齐规则，一切时间换算走查表。
2. **null ≠ 0**：无效帧指标是 `null`，曲线断开（ECharts 用 `connectNulls: false`），不要补 0。
3. **键盘交互**：←/→ ±1 帧，Shift+←/→ ±5 帧，空格打点；焦点在输入框（label/comment 编辑）时不拦截按键；播放/暂停建议用 K 键。
4. **seek 节流**：`video.currentTime` 赋值是异步的，连按方向键需等 `seeked` 事件后再接受下一次步进（或维护目标帧号队列）。
5. **视频加载（HTTP，勿用自定义协议）**：视频统一走 `GET /api/projects/{video_id}/video`（及 `/analysis`，§4.7），`<video src>` 直接消费——starlette ≥0.39 FileResponse 原生支持 Range/206，拖动播放与逐帧 seek 可用。放弃 `kineform://` 自定义协议的理由：① starlette 原生 Range 支持，无需自研协议处理器；② 避开 Electron `protocol.handle` 已知媒体兼容问题（electron/electron#51442）；③ 开发态纯浏览器即可调试（不依赖 Electron 壳）。**注意**：跨源 canvas 抽帧要求响应带 CORS 头（后端已 `allow_origins=*`，见 §8.3）且 `<video>` 声明 `crossorigin="anonymous"`，否则 `drawImage` 后 canvas 被污染（tainted）无法读像素。
6. **video-annotator 现状**：Vue 3.5 + Vuetify 3 + video.js，单组件 Main.vue（~1900 行），无状态管理库、无 Electron、无逐帧步进、无曲线面板——这些全部需要新增；其时间轴笔记数据模型与 §3 不同，需替换为 markers 模型。

---

## 8. 服务运行与集成（P0 说明）

### 8.1 开发态启动

cwd = `backend/`：

```
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**项目目录根对齐**：本文档中 `outputs/<video_id>/` 为展示性前缀（如 `result_path` 字段）；服务端实际项目根与推理管线单一事实来源一致 = `sports_pose_analyzer/projects/`（`backend/app/core/config.py` 的 `OUTPUTS_DIR`，可用环境变量 `KINEFORM_OUTPUTS_DIR` 覆盖）。前端无需关心磁盘真实路径。

### 8.2 生产态（Electron 拉起，壳已实现）

Electron 壳已实现（`electron/` 目录），要点：

- 主进程拉起服务子进程，绑定 `127.0.0.1` **动态端口**；preload 经 `contextBridge` 注入 `window.KineFormConfig.apiBaseUrl`（渲染进程以 `ipcRenderer.sendSync` 同步取端口）；
- 以 `GET /api/health`（§4.5）**探活**：启动期 100ms 间隔轮询，就绪（`status == "ok"`）后进入主界面；运行期每 30s 复查；
- 应用退出时在 `before-quit` 中 `taskkill /T /F` **清理**服务子进程树；
- `KINEFORM_DEV=1` 开发模式：固定端口 8000、不 spawn 后端（配合 §8.1 手动启动）；
- 后端日志落 `%APPDATA%/KineForm/logs/backend.log`；
- 自定义应用菜单（替代默认菜单）：**文件** → 分析视频…（Ctrl+O）/ 退出；**视图** → 重新加载 / 切换开发者工具；
- UI 能力桥（preload `contextBridge` 注入，配合 §4.8 视频分析）：`window.KineFormDialog.openVideo()` 打开原生文件选择对话框（返回 `{canceled, path}`，文件过滤器即 §4.8 扩展名白名单）；`window.KineFormEvents.onAnalyzeVideo(cb)` 订阅菜单「分析视频」事件（返回取消订阅函数）。**注意：这是 UI 能力桥、非数据通道**——仅打开对话框与传递菜单事件，业务数据仍全走 HTTP（§4）；
- electron-builder 打包**仍待做**（后端 PyInstaller onedir 打包方案已调研）。

### 8.3 CORS 与任务表语义

- CORS：`allow_origins = *`——纯本地回环服务且无凭证，无实际风险；
- 任务表为**进程内存态**：服务重启即清空（先例：ComfyUI 的 history 同语义）——客户端按 §4.2 的 404 处理，提示用户重新提交。
