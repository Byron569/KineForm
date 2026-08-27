"""默认配置：路径、模型注册表、阈值、渲染开关。

模型注册表驱动，便于以后切换 RTMPose-l / 384x288 等变体；
全部为 Halpe-26 模型，禁止注册 COCO-17 模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / 'models'
PROJECTS_DIR = PROJECT_ROOT / 'projects'
SETTINGS_PATH = PROJECT_ROOT / 'user_settings.json'
TESTS_ASSETS_DIR = PROJECT_ROOT / 'tests' / 'assets'


# ---------------- 模型注册表 ----------------
@dataclass(frozen=True)
class PoseModelSpec:
    key: str
    display_name: str
    config_rel: str          # 相对 mmpose .mim 的配置路径
    checkpoint_filename: str
    checkpoint_url: str
    input_size: tuple[int, int]   # (w, h)
    num_keypoints: int = 26

    @property
    def config_path(self) -> Path:
        import mmpose
        return Path(mmpose.__file__).parent / '.mim' / self.config_rel

    @property
    def checkpoint_path(self) -> Path:
        return MODELS_DIR / self.checkpoint_filename


_RTMP = 'configs/body_2d_keypoint/rtmpose/body8'
_URL = 'https://download.openmmlab.com/mmpose/v1/projects/rtmposev1'

MODEL_REGISTRY: dict[str, PoseModelSpec] = {
    'rtmpose-m-halpe26-256x192': PoseModelSpec(
        key='rtmpose-m-halpe26-256x192',
        display_name='RTMPose-m Halpe-26 (256x192) [默认]',
        config_rel=f'{_RTMP}/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py',
        checkpoint_filename='rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth',
        checkpoint_url=f'{_URL}/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth',
        input_size=(192, 256)),
    'rtmpose-l-halpe26-256x192': PoseModelSpec(
        key='rtmpose-l-halpe26-256x192',
        display_name='RTMPose-l Halpe-26 (256x192)',
        config_rel=f'{_RTMP}/rtmpose-l_8xb512-700e_body8-halpe26-256x192.py',
        checkpoint_filename='rtmpose-l_simcc-body7_pt-body7-halpe26_700e-256x192-2abb7558_20230605.pth',
        checkpoint_url=f'{_URL}/rtmpose-l_simcc-body7_pt-body7-halpe26_700e-256x192-2abb7558_20230605.pth',
        input_size=(192, 256)),
    'rtmpose-m-halpe26-384x288': PoseModelSpec(
        key='rtmpose-m-halpe26-384x288',
        display_name='RTMPose-m Halpe-26 (384x288)',
        config_rel=f'{_RTMP}/rtmpose-m_8xb512-700e_body8-halpe26-384x288.py',
        checkpoint_filename='rtmpose-m_simcc-body7_pt-body7-halpe26_700e-384x288-89e6428b_20230605.pth',
        checkpoint_url=f'{_URL}/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-384x288-89e6428b_20230605.pth',
        input_size=(288, 384)),
    'rtmpose-l-halpe26-384x288': PoseModelSpec(
        key='rtmpose-l-halpe26-384x288',
        display_name='RTMPose-l Halpe-26 (384x288)',
        config_rel=f'{_RTMP}/rtmpose-l_8xb512-700e_body8-halpe26-384x288.py',
        checkpoint_filename='rtmpose-l_simcc-body7_pt-body7-halpe26_700e-384x288-734182ce_20230605.pth',
        checkpoint_url=f'{_URL}/rtmpose-l_simcc-body7_pt-body7-halpe26_700e-384x288-734182ce_20230605.pth',
        input_size=(288, 384)),
}

DEFAULT_MODEL_KEY = 'rtmpose-m-halpe26-256x192'


@dataclass(frozen=True)
class DetectorSpec:
    name: str
    config_rel: str
    checkpoint_filename: str
    checkpoint_url: str
    score_thr: float = 0.3

    @property
    def config_path(self) -> Path:
        import mmpose
        return Path(mmpose.__file__).parent / '.mim' / self.config_rel

    @property
    def checkpoint_path(self) -> Path:
        return MODELS_DIR / self.checkpoint_filename


DETECTOR = DetectorSpec(
    name='RTMDet-m (COCO/Objects365 person)',
    config_rel='demo/mmdetection_cfg/rtmdet_m_640-8xb32_coco-person.py',
    checkpoint_filename='rtmdet_m_person.pth',
    checkpoint_url='https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/'
                   'rtmdet_m_8xb32-100e_coco-obj365-person-235e8209.pth')


# ---------------- 阈值 ----------------
@dataclass
class Thresholds:
    keypoint_score_thr: float = 0.35   # 低于此分数的关键点视为无效
    max_interp_gap: int = 5            # 缺失 ≤N 帧才允许线性插值
    det_score_thr: float = 0.30        # 人体检测分数阈值
    min_iou: float = 0.30              # 与上一帧框的 IoU 低于此值时改选最高分框
    low_pose_valid_ratio: float = 0.50 # 有效点比例低于此值 → low_pose_confidence
    low_pose_mean_score: float = 0.30  # 平均分低于此值 → low_pose_confidence
    # One Euro Filter 参数
    one_euro_min_cutoff: float = 1.5
    one_euro_beta: float = 0.10
    one_euro_d_cutoff: float = 1.0
    # 跳点检测
    max_kpt_jump_ratio: float = 0.35   # 单帧位移 > 该值×身高 视为可疑跳点
    limb_change_ratio: float = 0.40    # 左右肢体长度单帧突变比例


# ---------------- 渲染 ----------------
@dataclass
class OverlayConfig:
    draw_skeleton: bool = True         # 骨架连线
    draw_keypoints: bool = True        # 关键点圆点
    draw_point_ids: bool = False       # 关键点编号
    draw_angles: bool = True           # 关节角度数值
    draw_trajectory: bool = True       # 骨盆短时轨迹
    draw_event_labels: bool = True     # 事件标签
    draw_frame_info: bool = True       # 帧号+时间戳
    draw_quality: bool = True          # 姿态质量
    trajectory_frames: int = 30        # 轨迹长度（帧）


def preset_skeleton_only() -> OverlayConfig:
    """预设 A：仅骨架和关键点。"""
    return OverlayConfig(
        draw_skeleton=True, draw_keypoints=True, draw_point_ids=False,
        draw_angles=False, draw_trajectory=False, draw_event_labels=False,
        draw_frame_info=False, draw_quality=False)


def preset_full() -> OverlayConfig:
    """预设 B：完整信息（默认）。"""
    return OverlayConfig()


# ---------------- Tracker（外部逐帧复核播放器） ----------------
TRACKER_COMMON_PATHS = [
    r'D:\Tracker\Tracker.exe',
    r'C:\Program Files\Tracker\Tracker.exe',
    r'C:\Program Files (x86)\Tracker\Tracker.exe',
    str(Path.home() / 'Tracker' / 'Tracker.exe'),
    str(Path.home() / 'AppData' / 'Local' / 'Tracker' / 'Tracker.exe'),
]

DEVICE_DEFAULT = 'cuda:0'


def ensure_models_dir() -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return MODELS_DIR
