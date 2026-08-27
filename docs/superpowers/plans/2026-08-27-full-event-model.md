# 全量事件模型增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有 `events.json` 输出和 `gait_summary` 的前提下，为全部 12 类现有事件建立统一的训练数据格式、可选多标签时序模型、按类型融合与规则回退机制。

**Architecture:** 保留现有纯 NumPy/SciPy 规则检测器作为候选生成和无模型回退；新增纯数据的特征/预测协议与事件融合层，模型训练使用 PyTorch TCN，多标签输出覆盖全部事件类型。模型只校准已有的 `MetricsResult` 时序特征，不直接从原始视频训练；没有真实标签的事件使用“规则候选 + 人工修正”的标注流程，不能当作负样本。

**Tech Stack:** Python 3.11, NumPy, SciPy, PyTorch 2.1.2, pytest, JSON/JSONL/NPZ。运行主链路不在顶层导入 PyTorch，保持无 GPU 测试可运行。

---

## 文件边界

新增文件：

- `sports_pose_analyzer/app/events/event_types.py`：全量事件类型、事件分组和类型级后处理配置。
- `sports_pose_analyzer/app/events/features.py`：从 `MetricsResult` 构造模型输入，统一处理缺失值和掩码。
- `sports_pose_analyzer/app/events/model.py`：推理协议、预测数据结构和可选模型加载入口；不在模块顶层导入 torch。
- `sports_pose_analyzer/app/events/fusion.py`：把规则事件和模型候选按类型融合，执行类型级约束。
- `sports_pose_analyzer/training/__init__.py`、`sports_pose_analyzer/training/events/__init__.py`：训练包入口。
- `sports_pose_analyzer/training/events/dataset.py`：事件训练样本 NPZ/JSONL 读取、未标注掩码和受试者分组。
- `sports_pose_analyzer/training/events/tcn.py`：全量多标签时序网络和掩码 BCE 损失。
- `sports_pose_analyzer/training/events/train.py`：训练入口、受试者分组切分、权重保存。
- `sports_pose_analyzer/training/events/evaluate.py`：按事件类型计算时间容差指标。
- `sports_pose_analyzer/scripts/prepare_event_dataset.py`：统一数据集格式校验和转换入口。
- `sports_pose_analyzer/scripts/train_event_model.py`：命令行训练入口。
- `sports_pose_analyzer/scripts/evaluate_event_model.py`：命令行评估入口。
- `sports_pose_analyzer/tests/test_event_types.py`：类型清单和分组契约测试。
- `sports_pose_analyzer/tests/test_event_features.py`：特征形状、掩码和缺失值测试。
- `sports_pose_analyzer/tests/test_event_model.py`：预测协议、形状和 CPU smoke test。
- `sports_pose_analyzer/tests/test_event_dataset.py`：数据读取、未标注字段和 subject split 测试。
- `sports_pose_analyzer/tests/test_event_fusion.py`：全量事件保留、融合、去重、顺序约束和回退测试。

修改文件：

- `sports_pose_analyzer/app/common/data_models.py`：给 `Event` 增加默认值为空的可选模型元数据，旧 JSON 字段保持不变。
- `sports_pose_analyzer/app/events/detector.py`：保留全部现有检测器，在 `detect_events` 增加可选模型参数并接入融合层；默认参数路径行为不变。
- `sports_pose_analyzer/app/config/settings.py`：增加可选 `event_model_path`，空值表示不加载模型。
- `sports_pose_analyzer/app/pipeline/orchestrator.py`：在事件计算阶段按配置加载模型；加载失败时记录 warning 并继续规则检测。
- `sports_pose_analyzer/README.md`：记录数据格式、训练/评估命令、事件类型和商业许可注意事项。

不修改：`gait_summary` 的生成逻辑、前端事件展示、`score_report.json` AI 字段和现有用户未提交的 backend/UI 修改。

---

### Task 1: 固化全量事件类型和事件元数据契约

**Files:**
- Create: `sports_pose_analyzer/app/events/event_types.py`
- Modify: `sports_pose_analyzer/app/common/data_models.py:Event`
- Test: `sports_pose_analyzer/tests/test_event_types.py`
- Test: `sports_pose_analyzer/tests/test_serialization.py`

- [ ] **Step 1: Write the failing tests**

在 `test_event_types.py` 中先写出完整清单和分组契约：

```python
from app.events.event_types import EVENT_TYPES, EVENT_GROUPS


def test_event_types_cover_every_existing_events_json_type():
    assert set(EVENT_TYPES) == {
        'min_left_knee_angle', 'min_right_knee_angle',
        'max_torso_lean', 'max_pelvis_height', 'min_pelvis_height',
        'max_joint_angular_velocity', 'pose_lost_start', 'pose_lost_end',
        'left_touchdown', 'right_touchdown', 'left_toe_off', 'right_toe_off',
    }


def test_event_groups_cover_all_types_once():
    grouped = [event_type for values in EVENT_GROUPS.values()
                for event_type in values]
    assert len(grouped) == len(EVENT_TYPES)
    assert set(grouped) == set(EVENT_TYPES)
```

在 `test_serialization.py` 中增加旧事件构造测试，要求默认元数据不改变已有输出字段：

```python
def test_event_to_dict_omits_optional_model_metadata_by_default():
    event = Event('max_torso_lean', 10, 400.0, 12.5, 'degree', 0.8)
    assert event.to_dict() == {
        'type': 'max_torso_lean', 'frame_index': 10,
        'timestamp_ms': 400.0, 'value': 12.5,
        'unit': 'degree', 'confidence': 0.8,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_types.py tests/test_serialization.py -q`

Expected: FAIL because `event_types.py` and the optional metadata contract do not exist.

- [ ] **Step 3: Write the minimal implementation**

`event_types.py` 定义固定顺序的 `EVENT_TYPES`，并将类型分成 `gait_contact`、`kinematic_extrema`、`angular_velocity`、`pose_quality` 四组。`Event` 增加默认值为空的 `source: str | None`、`uncertainty_ms: float | None`、`phase: str | None`；`to_dict()` 只有在字段非空时才写入，旧事件 JSON 不增加新键。

- [ ] **Step 4: Run tests to verify they pass**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_types.py tests/test_serialization.py -q`

Expected: PASS，且已有 `Event.to_dict` 数值精度测试继续通过。

- [ ] **Step 5: Commit**

```powershell
git add -- sports_pose_analyzer/app/events/event_types.py sports_pose_analyzer/app/common/data_models.py sports_pose_analyzer/tests/test_event_types.py sports_pose_analyzer/tests/test_serialization.py
git commit -m "feat: define full event type contract"
```

### Task 2: 建立统一的模型输入特征层

**Files:**
- Create: `sports_pose_analyzer/app/events/features.py`
- Test: `sports_pose_analyzer/tests/test_event_features.py`

- [ ] **Step 1: Write the failing tests**

在测试文件中复用 `tests/test_events.py` 的 `_make_metrics()` 构造器，覆盖正常、NaN 和空序列：

```python
import numpy as np

from test_events import _make_metrics
from app.events.features import build_event_features


def test_build_event_features_returns_frame_aligned_values_and_missing_mask():
    metrics = _make_metrics(n=8)
    batch = build_event_features(metrics)
    assert batch.values.shape[0] == metrics.frame_count
    assert batch.values.shape == batch.missing_mask.shape
    assert batch.values.shape[1] == len(batch.names)
    assert np.isfinite(batch.values).all()
    assert batch.missing_mask.dtype == bool


def test_build_event_features_marks_nan_measurements_without_leaking_nan():
    metrics = _make_metrics(n=8)
    metrics.trajectories['left_heel'][3, 0] = np.nan
    batch = build_event_features(metrics)
    assert batch.missing_mask[3].any()
    assert np.isfinite(batch.values[3]).all()


def test_build_event_features_empty_metrics_has_zero_rows():
    batch = build_event_features(_make_metrics(n=0))
    assert batch.values.shape[0] == 0
    assert batch.missing_mask.shape[0] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_features.py -q`

Expected: FAIL because `EventFeatureBatch` and `build_event_features` do not exist.

- [ ] **Step 3: Write the minimal implementation**

`EventFeatureBatch` 使用 `values: np.ndarray`、`missing_mask: np.ndarray`、`names: tuple[str, ...]`。特征按固定顺序读取当前 `MetricsResult`：左右脚跟相对骨盆 x/y、左右脚跟速度、8 个关节角、8 个角速度、躯干倾角、骨盆 x/y/速度、6 个节段角、姿态质量、有效比例和缺失比例。每个原始标量增加一个对应 missing mask；有限值按序列统计量归一化，非有限值替换为 0。该模块只能依赖 NumPy 和现有数据模型，不导入 torch。

- [ ] **Step 4: Run tests to verify they pass**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_features.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add -- sports_pose_analyzer/app/events/features.py sports_pose_analyzer/tests/test_event_features.py
git commit -m "feat: build event model feature batches"
```

### Task 3: 建立带未标注掩码的训练数据格式

**Files:**
- Create: `sports_pose_analyzer/training/__init__.py`
- Create: `sports_pose_analyzer/training/events/__init__.py`
- Create: `sports_pose_analyzer/training/events/dataset.py`
- Create: `sports_pose_analyzer/scripts/prepare_event_dataset.py`
- Test: `sports_pose_analyzer/tests/test_event_dataset.py`

- [ ] **Step 1: Write the failing tests**

训练样本使用一个 JSONL manifest 和每样本一个 NPZ：NPZ 中 `features` 是 `(T,D)`，`labels` 是 `(T,12)`，标签值为 `1` 事件、`0` 已标注无事件、`-1` 未标注；manifest 记录 `subject_id`、`session_id`、`fps`、`source`、`npz_path` 和许可信息。

```python
import json

import numpy as np

from app.events.event_types import EVENT_TYPES
from training.events.dataset import load_event_sample, split_by_subject


def _write_manifest(tmp_path, subject_id='subject-001'):
    tmp_path.mkdir(parents=True, exist_ok=True)
    features = np.zeros((6, 4), dtype=np.float32)
    labels = np.zeros((6, len(EVENT_TYPES)), dtype=np.float32)
    labels[:, EVENT_TYPES.index('max_torso_lean')] = -1
    labels[2, EVENT_TYPES.index('left_touchdown')] = 1
    sample_path = tmp_path / 'sample.npz'
    np.savez(sample_path, features=features, labels=labels)
    manifest_path = tmp_path / 'manifest.jsonl'
    manifest_path.write_text(json.dumps({
        'subject_id': subject_id, 'session_id': 'session-001',
        'fps': 100.0, 'source': 'synthetic',
        'license': 'test-only', 'npz_path': str(sample_path),
    }) + '\n', encoding='utf-8')
    return manifest_path


def test_load_event_sample_preserves_unlabeled_mask(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    sample = load_event_sample(manifest_path)
    assert sample.features.shape[0] == sample.labels.shape[0]
    assert sample.labels.shape[1] == len(EVENT_TYPES)
    assert sample.label_mask.shape == sample.labels.shape
    assert not sample.label_mask[:, EVENT_TYPES.index('max_torso_lean')].any()


def test_unlabeled_event_is_not_converted_to_negative(tmp_path):
    manifest_path = _write_manifest(tmp_path)
    sample = load_event_sample(manifest_path)
    torso_idx = EVENT_TYPES.index('max_torso_lean')
    assert (sample.labels[:, torso_idx] == -1).all()


def test_group_split_never_shares_subject_between_train_and_validation(tmp_path):
    samples = [
        load_event_sample(_write_manifest(
            tmp_path / f'subject-{i}', subject_id=f'subject-{i}'))
        for i in range(4)
    ]
    train, valid = split_by_subject(samples, valid_ratio=0.25, seed=7)
    assert {s.subject_id for s in train}.isdisjoint(
        {s.subject_id for s in valid})
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_dataset.py -q`

Expected: FAIL because the sample loader and group split do not exist.

- [ ] **Step 3: Write the minimal implementation**

实现 `EventSample`、`load_event_sample()`、`load_manifest()` 和 `split_by_subject()`。加载器拒绝特征行数与标签行数不一致、未知事件类型和不存在的 NPZ 路径；允许某个事件通道全为 `-1`。`prepare_event_dataset.py` 只负责格式校验和转换，不自动把“没有标签”填成负类。所有数据源记录原始数据集名称、版本、许可证和转换规则。

- [ ] **Step 4: Run tests to verify they pass**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_dataset.py -q`

Expected: PASS。

- [ ] **Step 5: Commit**

```powershell
git add -- sports_pose_analyzer/training sports_pose_analyzer/scripts/prepare_event_dataset.py sports_pose_analyzer/tests/test_event_dataset.py
git commit -m "feat: add masked event training dataset format"
```

### Task 4: 实现全量多标签 TCN 和推理协议

**Files:**
- Create: `sports_pose_analyzer/app/events/model.py`
- Create: `sports_pose_analyzer/training/events/tcn.py`
- Test: `sports_pose_analyzer/tests/test_event_model.py`

- [ ] **Step 1: Write the failing tests**

先用不依赖权重的协议测试固定形状，再用小尺寸 CPU smoke test：

```python
import numpy as np
import torch

from app.events.event_types import EVENT_TYPES
from app.events.model import EventPrediction
from training.events.tcn import TemporalEventNet, masked_event_loss


def test_event_prediction_requires_all_event_channels():
    prediction = EventPrediction(
        probabilities=np.zeros((8, len(EVENT_TYPES)), dtype=np.float32),
        frame_indices=np.arange(8),
        fps=30.0,
    )
    assert prediction.probabilities.shape == (8, len(EVENT_TYPES))
    prediction.validate()


def test_temporal_event_net_returns_one_probability_channel_per_event():
    model = TemporalEventNet(input_dim=6, hidden_dim=8, blocks=2)
    output = model(torch.zeros(2, 12, 6))
    assert output.shape == (2, 12, len(EVENT_TYPES))


def test_masked_loss_ignores_unlabeled_channels():
    logits = torch.zeros(1, 4, len(EVENT_TYPES))
    labels = torch.zeros_like(logits)
    labels[:, :, EVENT_TYPES.index('max_torso_lean')] = -1
    loss = masked_event_loss(logits, labels)
    assert torch.isfinite(loss)
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_model.py -q`

Expected: FAIL because the prediction protocol, TCN and masked loss do not exist.

- [ ] **Step 3: Write the minimal implementation**

`TemporalEventNet` 输入 `[batch, time, features]`，使用 1D temporal convolution blocks 和 dilation，输出 `[batch, time, 12]` logits。训练损失使用 `BCEWithLogitsLoss(reduction='none')`，只对 `labels >= 0` 的位置求平均；多标签 sigmoid 允许同一帧出现多个事件。`EventModel` Protocol 定义 `predict(batch: EventFeatureBatch) -> EventPrediction`。torch 只在 `tcn.py` 或显式加载函数内导入，生产主链路未配置模型时不加载。

- [ ] **Step 4: Run tests to verify they pass**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_model.py -q`

Expected: PASS；若当前环境没有可用 torch，应将 torch smoke test 标记为明确的环境跳过，并保留协议测试通过，不能静默跳过真实失败。

- [ ] **Step 5: Commit**

```powershell
git add -- sports_pose_analyzer/app/events/model.py sports_pose_analyzer/training/events/tcn.py sports_pose_analyzer/tests/test_event_model.py sports_pose_analyzer/requirements.txt
git commit -m "feat: add multi-label temporal event model"
```

### Task 5: 实现模型候选解码和全量事件融合

**Files:**
- Create: `sports_pose_analyzer/app/events/fusion.py`
- Modify: `sports_pose_analyzer/app/events/detector.py`
- Test: `sports_pose_analyzer/tests/test_event_fusion.py`
- Test: `sports_pose_analyzer/tests/test_events.py`
- Test: `sports_pose_analyzer/tests/test_gait.py`

- [ ] **Step 1: Write the failing tests**

先证明无模型时旧输出完全保持，再证明模型候选能校准全部类型且不会丢失规则事件：

```python
import numpy as np

from test_events import _make_metrics
from app.common.data_models import Event
from app.events.detector import detect_events
from app.events.event_types import EVENT_TYPES
from app.events.fusion import fuse_events
from app.events.model import EventPrediction


def _prediction(peaks, n=24, fps=30.0):
    probabilities = np.zeros((n, len(EVENT_TYPES)), dtype=np.float32)
    for event_type, frame in peaks.items():
        probabilities[frame, EVENT_TYPES.index(event_type)] = 0.95
    return EventPrediction(
        probabilities=probabilities,
        frame_indices=np.arange(n),
        fps=fps,
    )


def test_fuse_without_model_returns_rule_events_unchanged():
    metrics = _make_metrics(n=24)
    statuses = ['ok'] * 24
    expected = detect_events(metrics, statuses)
    assert detect_events(metrics, statuses, event_model=None) == expected


def test_fuse_model_candidates_preserves_all_existing_event_types():
    metrics = _make_metrics(n=24)
    statuses = ['ok'] * 24
    rule_events = [
        Event(event_type, frame, float(frame), 1.0, 'unit', 0.7)
        for event_type, frame in zip(EVENT_TYPES, range(len(EVENT_TYPES)))
    ]
    prediction = _prediction({event_type: index
                              for index, event_type in enumerate(EVENT_TYPES)})
    merged = fuse_events(rule_events, prediction, metrics, statuses)
    assert set(event.type for event in merged) == set(EVENT_TYPES)


def test_fuse_rejects_duplicate_and_invalid_gait_order():
    metrics = _make_metrics(n=24)
    statuses = ['ok'] * 24
    prediction = _prediction({
        'left_touchdown': 12,
        'left_toe_off': 4,
        'right_touchdown': 18,
    })
    merged = fuse_events([], prediction, metrics, statuses)
    keys = [(event.type, event.frame_index) for event in merged]
    assert len(keys) == len(set(keys))
    left_events = [event for event in merged
                   if event.type in ('left_touchdown', 'left_toe_off')]
    assert [event.type for event in left_events] != [
        'left_touchdown', 'left_toe_off']
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_fusion.py tests/test_events.py tests/test_gait.py -q`

Expected: FAIL because `detect_events` 没有模型参数，融合和类型级约束尚不存在。

- [ ] **Step 3: Write the minimal implementation**

在 `fusion.py` 实现：

1. 按 `EVENT_TYPES` 读取模型概率，找出超过各类型阈值的局部候选；
2. 将模型候选与同类型规则事件在时间容差内匹配，匹配时使用模型帧校准事件时间，保留规则事件的单位和值语义；
3. 高置信模型候选可以新增事件，但低置信孤立候选不覆盖规则事件；
4. 对步态事件执行左右脚交替和 touchdown/toe-off 顺序检查；
5. 对膝角、躯干倾角、骨盆高度和角速度执行极值方向、最小间隔和值有效性检查；
6. 对姿态丢失边界使用连续无效/有效状态检查，过滤单帧抖动；
7. 最终按 `(frame_index, 原有检测器顺序)` 稳定排序，并按 `(type, frame_index)` 去重。

`detector.detect_events(metrics, statuses, event_model=None)` 默认保持旧签名行为。传入模型时，先运行所有现有规则检测器，再把所有规则事件和模型候选交给 `fuse_events()`；模型异常由上层捕获，不能在这里删除规则结果。

- [ ] **Step 4: Run tests to verify they pass**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_fusion.py tests/test_events.py tests/test_gait.py -q`

Expected: PASS，且当前所有通用事件、全部步态事件测试和 `gait_summary` 测试继续通过。

- [ ] **Step 5: Commit**

```powershell
git add -- sports_pose_analyzer/app/events/fusion.py sports_pose_analyzer/app/events/detector.py sports_pose_analyzer/tests/test_event_fusion.py sports_pose_analyzer/tests/test_events.py sports_pose_analyzer/tests/test_gait.py
git commit -m "feat: fuse model predictions with all event rules"
```

### Task 6: 接入可选模型配置和规则回退

**Files:**
- Modify: `sports_pose_analyzer/app/config/settings.py`
- Modify: `sports_pose_analyzer/app/pipeline/orchestrator.py`
- Test: `sports_pose_analyzer/tests/test_event_model.py`
- Test: `sports_pose_analyzer/tests/test_events.py`

- [ ] **Step 1: Write the failing tests**

```python
from app.config.settings import UserSettings
from app.events.model import load_configured_event_model


def test_empty_event_model_path_keeps_model_disabled(tmp_path):
    settings = UserSettings(event_model_path='')
    model, warning = load_configured_event_model(settings.event_model_path)
    assert model is None
    assert warning is None


def test_missing_event_model_path_falls_back_without_raising(tmp_path):
    settings = UserSettings(event_model_path=str(tmp_path / 'missing.pt'))
    model, warning = load_configured_event_model(settings.event_model_path)
    assert model is None
    assert warning
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_model.py tests/test_events.py -q`

Expected: FAIL because the setting and loader do not exist.

- [ ] **Step 3: Write the minimal implementation**

给 `UserSettings` 增加 `event_model_path: str = ''`。在 `model.py` 增加 `load_configured_event_model(path)`：空路径返回 `(None, None)`；文件不存在、权重版本不匹配或 torch 加载失败时返回 `(None, warning)`，不抛出到分析主流程。`orchestrator.py` 在现有 `detect_events` 调用之前加载一次模型，warning 加入现有 `warnings`，然后调用 `detect_events(metrics, statuses, event_model=model)`。事件模型加载不改变 `gait_summary` 的后续计算。

- [ ] **Step 4: Run tests to verify they pass**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_model.py tests/test_events.py -q`

Expected: PASS；无模型路径时生成的事件和现有结果一致。

- [ ] **Step 5: Commit**

```powershell
git add -- sports_pose_analyzer/app/config/settings.py sports_pose_analyzer/app/events/model.py sports_pose_analyzer/app/pipeline/orchestrator.py sports_pose_analyzer/tests/test_event_model.py sports_pose_analyzer/tests/test_events.py
git commit -m "feat: add optional event model fallback"
```

### Task 7: 实现训练、评估命令和真实数据接入边界

**Files:**
- Create: `sports_pose_analyzer/training/events/train.py`
- Create: `sports_pose_analyzer/training/events/evaluate.py`
- Create: `sports_pose_analyzer/scripts/train_event_model.py`
- Create: `sports_pose_analyzer/scripts/evaluate_event_model.py`
- Modify: `sports_pose_analyzer/README.md`
- Test: `sports_pose_analyzer/tests/test_event_dataset.py`
- Test: `sports_pose_analyzer/tests/test_event_model.py`

- [ ] **Step 1: Write the failing tests**

```python
import json

import numpy as np

from app.events.event_types import EVENT_TYPES
from training.events.evaluate import score_events
from training.events.train import train_event_model


def test_event_metrics_use_frame_tolerance_per_type():
    truth = {'left_touchdown': [100], 'max_torso_lean': [200]}
    pred = {'left_touchdown': [102], 'max_torso_lean': [220]}
    scores = score_events(truth, pred, fps=100.0, tolerances_frames=[1, 2, 5])
    assert scores['left_touchdown']['f1@2'] == 1.0
    assert scores['max_torso_lean']['f1@2'] == 0.0


def test_training_command_can_run_one_cpu_epoch_on_synthetic_data(tmp_path):
    manifest_path = _write_synthetic_manifest(tmp_path)
    output_path = tmp_path / 'event_model.pt'
    result = train_event_model(manifest_path, output_path, epochs=1, device='cpu')
    assert result['event_types'] == list(EVENT_TYPES)
    assert output_path.exists()


def _write_synthetic_manifest(tmp_path):
    sample_path = tmp_path / 'sample.npz'
    np.savez(
        sample_path,
        features=np.zeros((16, 6), dtype=np.float32),
        labels=np.zeros((16, len(EVENT_TYPES)), dtype=np.float32),
    )
    manifest_path = tmp_path / 'manifest.jsonl'
    manifest_path.write_text(json.dumps({
        'subject_id': 'synthetic-001', 'session_id': 'session-001',
        'fps': 100.0, 'source': 'synthetic', 'license': 'test-only',
        'npz_path': str(sample_path),
    }) + '\n', encoding='utf-8')
    return manifest_path
```

- [ ] **Step 2: Run tests to verify they fail**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_dataset.py tests/test_event_model.py -q`

Expected: FAIL because scoring and training entry points do not exist。

- [ ] **Step 3: Write the minimal implementation**

`train.py` 读取 masked samples，按 subject split，计算训练集正样本权重，保存模型权重、输入特征名称、`EVENT_TYPES` 顺序、归一化参数、训练数据 manifest 摘要和代码版本。`evaluate.py` 对每个事件类型分别计算 Precision/Recall/F1@±1/±2/±5 帧、时间 MAE、漏检数和误报数；事件通道全为 `unlabeled` 时输出 `status='unlabeled'`，不输出虚假的 0 分。命令行参数明确要求 manifest、输出路径、device、epochs 和 seed。

README 记录：

- Fukuchi、Van Hooren、Mendeley 数据分别能监督哪些事件；
- 没有标签的通道必须保持 `-1`；
- train/valid/test 按 subject/session 分组；
- 低 FPS、高速运动和遮挡要单独评估；
- AthletePose3D、AthleticsPose、Fitness-AQA、NS-AQA 等非商业数据不能直接用于商业模型发布。

- [ ] **Step 4: Run tests to verify they pass**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_event_dataset.py tests/test_event_model.py -q`

Expected: PASS，CPU synthetic smoke test 可以产生可加载的权重和全量事件元数据。

- [ ] **Step 5: Commit**

```powershell
git add -- sports_pose_analyzer/training/events/train.py sports_pose_analyzer/training/events/evaluate.py sports_pose_analyzer/scripts/train_event_model.py sports_pose_analyzer/scripts/evaluate_event_model.py sports_pose_analyzer/README.md sports_pose_analyzer/tests/test_event_dataset.py sports_pose_analyzer/tests/test_event_model.py
git commit -m "feat: add event model training and evaluation commands"
```

### Task 8: 全量回归验证与数据集接入验收

**Files:**
- Test: `sports_pose_analyzer/tests/test_serialization.py`
- Test: `sports_pose_analyzer/tests/test_motion_json.py`
- Test: `sports_pose_analyzer/tests/test_events.py`
- Test: `sports_pose_analyzer/tests/test_gait.py`
- No production file changes in this task

- [ ] **Step 1: Run the complete Python test suite**

Run from `sports_pose_analyzer`: `python -m pytest -q`

Expected: all existing and new tests pass with exit code 0。

- [ ] **Step 2: Run a generated events JSON compatibility check**

Run from `sports_pose_analyzer`: `python -m pytest tests/test_serialization.py tests/test_events.py tests/test_gait.py tests/test_event_fusion.py -q`

Expected: 旧事件字段、全部 12 类事件、`gait_summary` 相关测试全部通过；没有模型文件时事件结果与改造前一致。

- [ ] **Step 3: Run the CPU training/evaluation smoke commands**

Run:

```powershell
cd sports_pose_analyzer
python scripts/prepare_event_dataset.py --help
python scripts/train_event_model.py --help
python scripts/evaluate_event_model.py --help
```

Expected: 三个命令均退出 0，并显示 manifest、模型输出、device 和评估参数。

- [ ] **Step 4: Inspect the final diff and existing user changes**

Run these commands separately:

```powershell
git diff --check
git status --short
git diff --stat HEAD
```

Expected: 没有空白错误；提交只包含本计划范围内的文件；既有 backend/UI/API_CONTRACT 修改不被重写、回滚或混入。

---

## 实施限制

这份计划可以先完成代码接口、合成数据训练和回归测试，但不能在没有真实标注的情况下声称模型已经改善实际事件准确率。对膝角度、躯干倾角、骨盆高度、角速度和姿态丢失事件，需要先从真实 KineForm 视频或对应 3D 数据生成候选，再人工确认标签；Fukuchi、Van Hooren 和 Mendeley 主要直接监督步态接触事件。

真实数据接入时，优先使用允许的 CC BY 数据；非商业数据集只能用于受许可的研究实验。模型准确率验收必须按事件类型和受试者分组报告，不能把不同事件混成一个总 F1。

