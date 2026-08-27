# 离线单人运动姿态分析器（KineForm Sports Pose Analyzer）

本地桌面工具：导入单人运动视频 → RTX GPU 逐帧姿态分析 → 生成带骨架/指标叠加的分析视频、逐帧关键点数据、运动学指标 CSV、事件列表与 HTML 报告，并可一键调用本机 Tracker（OpenSourcePhysics）逐帧复核。

**离线运行**：不需要网络（首次下载模型除外）、不需要云端账户、不需要数据库或 Web 后端。

---

## 1. 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Windows 10/11 x64 |
| Python | 3.11（mmcv Windows 预编译轮子最高支持 cp311） |
| GPU | NVIDIA CUDA 显卡（本项目在 RTX 4060 Laptop 8GB 上开发验证） |
| CUDA 运行时 | CUDA 12.1（随 torch 轮子自带，无需单独安装 CUDA Toolkit） |
| 磁盘 | ≥ 5 GB（环境 + 模型权重） |
| 可选 | Tracker（OpenSourcePhysics 外部逐帧复核播放器）；系统 ffmpeg（没有则用内置 imageio-ffmpeg） |

## 2. CUDA / RTX 4060 说明

- 推理默认 `cuda:0` + FP16（自动回退 FP32）；
- 不追求实时，**逐帧完整分析（frame_skip=1）**，视频越长耗时越久（RTX 4060 实测约 25-40ms/帧推理 + 渲染转码时间）；
- 显存占用 < 3GB，8GB 显卡无压力；
- 无 NVIDIA GPU 时可在 GUI/CLI 指定 `cpu` 设备运行（速度下降明显）。

## 3. 模型下载

默认模型（RTMPose-m Halpe-26, 256x192）权重放在 `models/`：

```
models/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth
```

- **自动下载**：首次分析若权重缺失，程序会提示并联网下载（OpenMMLab 官方源）；
- **手动下载**（推荐，国内更快）：

```
https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth
```

人体检测器（RTMDet-m，person 类）权重：

```
https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/rtmdet_m_8xb32-100e_coco-obj365-person-235e8209.pth
```

放入 `models/rtmdet_m_person.pth`。

架构支持切换 RTMPose-l / 384x288 输入（GUI 模型下拉框选择，权重首次使用时自动下载），全部为 Halpe-26 模型，**不会退化到 COCO-17**（加载时校验关键点元数据，不匹配直接报错）。

## 4. 安装

```powershell
# 1) 创建 Python 3.11 虚拟环境
python -m venv .venv
.\.venv\Scripts\activate

# 2) PyTorch（CUDA 12.1）
pip install torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cu121

# 3) mmcv 预编译轮子（必须是这个 URL，PyPI 上没有 Windows CUDA 版）
pip install https://download.openmmlab.com/mmcv/dist/cu121/torch2.1.0/mmcv-2.1.0-cp311-cp311-win_amd64.whl

# 4) 其余依赖
pip install mmdet==3.3.0 mmpose==1.3.2 "setuptools<81"
pip install numpy==1.26.4 opencv-python==4.11.0.86 scipy PySide6 imageio-ffmpeg pytest

# 5) 快速自检（应输出 cuda True 与三个库版本号）
python -c "import torch,numpy; print('torch',torch.__version__,'cuda',torch.cuda.is_available(),'numpy',numpy.__version__)"
```

> 注意：`numpy` 必须保持 1.26.4（torch 2.1.2 与 numpy 2.x 二进制不兼容，mmdet 安装时可能自动升级 numpy，装完请手动降回）。

## 5. 启动

```powershell
# GUI
python main.py

# 命令行（批处理/冒烟测试）
python scripts/run_analysis.py "D:\我的视频.mp4"
python scripts/run_analysis.py video.mp4 --model rtmpose-l-halpe26-384x288 --no-fp16
```

单元测试（不需要 GPU）：

```powershell
python -m pytest tests/ -q
```

## 6. 完整工作流示例

1. 启动 GUI，点击「选择视频…」选择一段单人运动视频；
2. 程序自动探测并显示：时长、帧率、总帧数、宽高、是否可变帧率（VFR 一律先转恒定帧率 CFR 再分析）；
3. 确认模型（默认 RTMPose-m Halpe-26）、FP16、叠加显示项；
4. 点击「开始分析」：进度条依次经过 探测→CFR→逐帧推理→后处理→指标→事件→渲染→导出；
5. 完成后查看概览（有效帧比例、平均姿态质量、膝/髋/躯干角范围、事件列表、警告）；
6. 按需点击：
   - 「打开分析视频」/「打开纯骨架视频」——系统播放器播放；
   - 「打开项目目录」——查看全部产物；
   - 「在 Tracker 打开原视频 / 分析视频」——进入 Tracker 逐帧/慢放/标定/测角；
   - 「打开 HTML 报告」——浏览器查看曲线与统计。

每次分析生成独立项目目录：

```
projects/2026-08-25_153000_我的视频/
├─ source_cfr.mp4      # 恒定帧率化的源视频（CFR 时为副本）
├─ analysis.mp4        # 完整叠加：骨架+角度+轨迹+事件标签+帧号（H.264，保留原音频）
├─ analysis_skeleton.mp4  # 纯骨架版
├─ manifest.json       # 分析元数据（模型、fps、帧数、状态）
├─ keypoints.json      # 逐帧 raw + filtered 关键点（26 点，含置信度与状态）
├─ metrics.csv         # 逐帧运动学指标（角度/轨迹/速度/质量）
├─ events.json         # 关键事件（关节角极值、躯干倾角、骨盆高度、姿态丢失边界）
└─ report.html         # 自包含 HTML 报告（曲线图 + 统计表）
```

## 7. Tracker 配置

- Tracker（OpenSourcePhysics 开源视频分析工具，GPL v3）仅作为**外部播放器**调用（`Tracker.exe <视频路径>`），本项目不修改/不嵌入/不分发 Tracker；
- 官网下载：https://opensourcephysics.github.io/tracker-website/ （Windows x64 安装包，自带 Java 运行时）；
- 在 GUI「Tracker 路径」行点击「浏览…」选择 `Tracker.exe`，或点击「检测」自动查找常见安装位置（`D:\Tracker\Tracker.exe`、`C:\Program Files\Tracker\Tracker.exe` 等）；
- 未配置或路径失效时点击相关按钮会给出清晰提示，不会崩溃，也不会自动下载 Tracker；
- 推荐用法：Tracker 中打开 `analysis.mp4` 做逐帧/慢放复核，可用其标定、测角、点跟踪工具与本项目自动分析结果互验。

## 8. 已知限制

1. **单目 2D 未标定数据**：所有坐标为像素、角度为图像平面投影角，**不代表真实三维角度、速度或距离**；侧面机位（运动平面平行于画面）时膝/髋角才最接近真实矢状面角度；
2. **单人场景**：多人同框时按「与上一帧框 IoU 最大」规则锁定一个主体，其他人被忽略；无多目标跟踪/ID 系统；
3. **事件为通用极值事件**（关节角极小、躯干倾角、骨盆高度、角速度、姿态丢失边界），未指定运动项目时不做「起跳/落地/发力」等语义判定，也没有运动评分；动作模板接口已预留；
4. VFR 视频会被转成 CFR 再分析（时间戳绑定 CFR 视频）；探测无法确凿判断时保守地执行转换；
5. 跳跃类腾空时间指标在低帧率（<30fps）视频上误差增大；
6. 低置信度关键点（score<0.35）标记无效，短缺口（≤5 帧）线性插值，长缺口保持缺失——不伪造数据；
7. Windows 平台专项开发，其他平台未测试。

## 9. 目录结构

```
sports_pose_analyzer/
├─ app/
│  ├─ ui/            # PySide6 界面
│  ├─ pipeline/      # 分析工作流编排
│  ├─ video/         # ffprobe/ffmpeg、CFR 标准化、H.264 转码
│  ├─ detection/     # 人体检测 + 单人主体选择（IoU 规则）
│  ├─ pose/          # RTMPose Halpe-26 推理（模型注册表驱动）
│  ├─ postprocess/   # 无效点/插值/One Euro 滤波/跳点剔除
│  ├─ biomechanics/  # 关节角/躯干倾角/轨迹/速度/对称性
│  ├─ events/        # 通用事件检测（可扩展动作模板）
│  ├─ render/        # 骨架与指标视频渲染（双预设）
│  ├─ exporters/     # JSON/CSV/HTML 导出
│  ├─ external_player/  # Tracker 外部启动
│  ├─ common/        # Halpe-26 元数据、数据模型、时间映射
│  └─ config/        # 默认配置/模型注册表、用户设置
├─ models/           # 权重（不入库）
├─ projects/         # 分析项目产物（不入库）
├─ scripts/          # CLI 入口
├─ tests/            # 单元测试（无需 GPU）
├─ main.py           # GUI 入口
├─ requirements.txt
└─ README.md
```
