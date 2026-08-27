# 短跑事件检测增强设计

## 目标

第一阶段增强 `events.json` 的短跑/跑步事件识别，同时完整保留并强化现有全部事件类型和 `gait_summary` 数据。模型不只优化步态接触事件，还要覆盖现有通用极值事件、角速度事件和姿态丢失边界事件。

- `min_left_knee_angle`
- `min_right_knee_angle`
- `max_torso_lean`
- `max_pelvis_height`
- `min_pelvis_height`
- `max_joint_angular_velocity`
- `pose_lost_start`
- `pose_lost_end`
- `left_touchdown`
- `right_touchdown`
- `left_toe_off`
- `right_toe_off`

输出需要保持现有事件格式兼容，同时为后续模型训练和报告分析保留事件置信度、来源和不确定性扩展空间。

现有的通用事件和派生步态摘要不能因为接入模型而减少。全部事件类型都要进入统一的训练/校准流程，并继续正常采集、输出和参加回归测试。本阶段不实现 `score_report.json` 的 AI 分析，不处理跳高起跳/落地，不引入端到端原始视频大模型。

## 当前实现与问题

KineForm 先使用 RTMPose Halpe-26 生成逐帧 2D 关键点，再计算角度、轨迹、速度和姿态质量。当前步态事件主要使用脚跟相对骨盆的水平位移、低通滤波和峰谷检测；通用事件检测器还会寻找角度、骨盆高度和角速度的极值。

现有方法缺少显式的时序约束：它不能稳定表达 touchdown/toe-off 的先后关系、左右脚交替、不同跑速下的周期变化，也不能区分低置信度关键点导致的伪峰。低帧率视频下，短跑支撑期只有少数帧，单纯依赖峰谷无法保证毫秒级定位。

## 设计方案

### 1. 保留现有规则并增加可替换的模型接口

不立即删除 Zeni/峰谷检测，也不删除现有通用事件检测器。第一版采用“全量事件保留、全量事件模型增强”的混合流程：

```text
逐帧关键点与运动学特征
        ↓
规则候选事件（现有 Zeni/峰谷/通用极值）
        ↓
多任务时序模型逐帧事件概率/边界概率
        ↓
按事件类型融合、顺序约束和最小间隔约束
        ↓
events.json
```

模型不可用、输入不足或置信度低时，所有事件类型继续使用对应的规则结果，保证现有管线可以运行。模型接口应接收已经存在的 `MetricsResult` 特征，而不是重新读取视频，避免第一阶段引入第二套姿态估计链路。模型合并过程不能过滤掉模型未覆盖的现有事件类型。

当前 `events[]` 中需要继续支持并进入模型训练/校准目标的类型包括：

- `min_left_knee_angle`、`min_right_knee_angle`；
- `max_torso_lean`；
- `max_pelvis_height`、`min_pelvis_height`；
- `max_joint_angular_velocity`；
- `pose_lost_start`、`pose_lost_end`；
- `left_touchdown`、`right_touchdown`、`left_toe_off`、`right_toe_off`。

此外，`events.json` 中已有的 `gait_summary` 仍需完整保留，包括步态时空参数、逐步特征、疲劳趋势、疑似起跳步和参考比较等派生数据。前端展示使用的历史别名（例如 `pelvis_highest`、`torso_lean_peak`）如果出现在旧数据中，读取端也必须继续兼容，但不在本阶段新增别名写出。

### 2. 事件模型的输入和输出

事件模型以固定长度的逐帧窗口为输入。输入特征优先使用项目已有数据：

- 左右脚跟相对骨盆的坐标和速度；
- 左右膝角度与角速度；
- 骨盆高度和水平速度；
- 躯干倾角；
- 关键点置信度、姿态质量和缺失掩码；
- 帧时间间隔或 FPS。

模型输出为每一帧的多标签事件概率，而不是单一互斥类别。这样同一帧可以同时出现例如膝角度极值、躯干倾角极值和步态事件。模型覆盖全部现有事件类型：

```text
none（所有事件概率均低于阈值）
min_left_knee_angle
min_right_knee_angle
max_torso_lean
max_pelvis_height
min_pelvis_height
max_joint_angular_velocity
pose_lost_start
pose_lost_end
left_touchdown
right_touchdown
left_toe_off
right_toe_off
```

后处理将概率序列转换为全部事件候选，再与对应规则检测器的结果融合。不同事件类型使用各自的后处理参数和标签约束：

- 步态事件检查左右脚交替、touchdown/toe-off 顺序和步态周期；
- 膝角、躯干倾角和骨盆高度事件检查极值方向、峰间距和数值有效性；
- 最大关节角速度事件保留现有“按角速度序列寻找全局最大”的语义；内部可以携带来源关节，导出时不破坏旧字段；
- 姿态丢失事件检查有效/无效状态转换，不能只因为单帧置信度波动就产生边界。

所有事件类型都必须满足：

- 同一帧相同事件只保留一个结果；
- 同一类型的相邻候选必须满足该类型的最小间隔；
- 无法满足该类型时序或数值约束的低置信度候选应被舍弃或标记为不确定；
- 事件排序以 `frame_index` 为主，时间戳由统一帧时间轴生成。
- 合并后不能删除或覆盖任何既有 `events[]` 类型；
- `gait_summary` 不从 `events.json` 中移除，也不因模型不可用而改为空值。

### 3. 事件 JSON 的兼容扩展

现有字段继续保留：`type`、`frame_index`、`timestamp_ms`、`value`、`unit`、`confidence`。

模型接入后可增加以下可选字段，不改变旧客户端读取方式：

```json
{
  "type": "left_touchdown",
  "frame_index": 183,
  "timestamp_ms": 1525.0,
  "value": 0.91,
  "unit": "probability",
  "confidence": 0.91,
  "source": "tcn+zeni",
  "uncertainty_ms": 8.4,
  "phase": "stance_start"
}
```

第一轮实现如果还没有可靠的不确定性估计，可以只增加内部接口，不在 JSON 中伪造 `uncertainty_ms`。任何新增字段必须是可选字段，并保持 `events.json` schema 版本兼容。

### 4. 数据集与训练数据格式

第一阶段先定义统一的中间格式，而不是把不同数据集直接拼接。每个样本至少包含全部事件类型的标签数组；没有标注的事件类型必须明确标记为 `unlabeled`，不能错误地当作 `none`：

```json
{
  "subject_id": "subject-001",
  "session_id": "session-001",
  "fps": 200,
  "features": [[0.1, 0.2, 0.0]],
  "labels": {
    "min_left_knee_angle": ["unlabeled"],
    "min_right_knee_angle": ["unlabeled"],
    "max_torso_lean": ["unlabeled"],
    "max_pelvis_height": ["unlabeled"],
    "min_pelvis_height": ["unlabeled"],
    "max_joint_angular_velocity": ["unlabeled"],
    "pose_lost_start": ["unlabeled"],
    "pose_lost_end": ["unlabeled"],
    "left_touchdown": [1525.0],
    "right_touchdown": [],
    "left_toe_off": [1610.0],
    "right_toe_off": []
  },
  "source": "force-plate"
}
```

不同事件类型需要不同标签来源，不能用一个数据集的标签填充所有事件：

- touchdown/toe-off 优先使用力台、足部传感器或人工逐帧标注；
- 膝角度、躯干倾角、骨盆高度和角速度事件，需要根据连续运动学曲线的极值生成候选，再由人工抽样校正，或直接使用人工事件帧标注；
- 姿态丢失边界需要根据关键点有效性、遮挡和人工可见性标注建立边界标签；
- Fukuchi Running、Van Hooren Running、Mendeley Sprint Event Dataset 主要提供步态接触事件或运动学监督，不能未经标注直接训练其他事件类型。

实验室 3D 数据与 KineForm 单目 2D 数据存在域差异，后续需要通过 3D 到 2D 投影、关键点噪声、遮挡和低帧率采样进行域适配，并使用少量真实 KineForm 视频校准。对于没有公开标签的事件类型，第一版应先采用“规则生成候选 + 人工纠正”的弱监督流程，再训练模型学习规则误差。

数据划分必须以运动员/受试者为单位，而不是以帧为单位，避免同一运动员的相邻帧泄漏到训练集和测试集。

### 5. 评估标准

事件模型必须与现有规则结果进行对比，至少报告：

- touchdown 和 toe-off 分开统计；
- ±1、±2、±5 帧容差下的 Precision、Recall、F1；
- 事件时间的毫秒级平均绝对误差和中位绝对误差；
- 漏检率和每分钟误报数；
- 低 FPS、快速运动、关键点遮挡场景的分组结果。

没有真实标注的事件不能用于宣称模型准确率。力台标注可以作为金标准来源，但转换到视觉事件时需要记录数据来源和转换规则。

## 错误处理与回退

- 输入帧数不足以组成一个完整时间窗口时，继续使用现有规则检测；
- 特征全为空或姿态质量低于现有有效比例时，不生成模型事件，并在内部记录原因；
- 模型文件缺失、版本不匹配或推理异常时，不阻塞主分析流程，回退到规则检测；
- 所有模型事件必须经过统一的去重、排序和时序约束；
- 不因为模型置信度高就覆盖明显违反事件顺序的结果。

## 测试范围

第一轮测试覆盖：

1. 标签格式可以表达全部现有事件类型、无事件帧和未标注状态；
2. 模型输出经过后处理后事件按帧排序；
3. 同一事件不会重复写入同一帧；
4. 步态顺序约束、极值约束、角速度约束和姿态边界约束分别生效；
5. 模型不可用时全部事件类型的规则回退路径保持现有行为；
6. 低质量/缺失特征不会导致分析崩溃；
7. 旧版 `events.json` 读取逻辑仍然有效；
8. 合并模型事件后，所有既有 `events[]` 类型仍然存在且没有被重复覆盖；
9. `gait_summary` 的原有字段和内容结构保持兼容；
10. 任何事件类型没有真实标签时，不会被错误计入该类型的准确率。

## 非目标

- 本阶段不训练从原始视频直接识别动作的视觉大模型；
- 本阶段不实现动作好坏评分和自然语言报告；
- 本阶段不修改前端事件展示交互，除非兼容性测试发现必须调整；
- 本阶段不把非商业数据集用于商业模型发布；
- 本阶段不把不同数据集的分数或事件标签未经转换直接混合。

## 成功标准

第一阶段完成的最低标准是：在不依赖模型文件时现有管线行为不回归；在提供全量事件模型或测试替身时，全部既有事件类型可以按照统一格式进入 `events.json`；原有所有事件类型和 `gait_summary` 仍完整输出；系统通过分类型约束、顺序、去重、回退和兼容性测试。每个事件类型只有在接入对应真实标注后，才能通过该类型的时间容差指标进行验收。

