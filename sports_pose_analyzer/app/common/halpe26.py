"""Halpe-26 关键点元数据。

点名称与顺序严格对应 MMPose 官方数据集定义
(configs/_base_/datasets/halpe26.py)，不得自行改动或混入 COCO-17 顺序。
运行时会与 MMPose 安装内的元数据交叉校验（见 verify_against_mmpose）。
"""
from __future__ import annotations

from pathlib import Path

NUM_KEYPOINTS = 26

# 索引常量（与 KEYPOINT_NAMES 一一对应）
NOSE = 0
LEFT_EYE, RIGHT_EYE = 1, 2
LEFT_EAR, RIGHT_EAR = 3, 4
LEFT_SHOULDER, RIGHT_SHOULDER = 5, 6
LEFT_ELBOW, RIGHT_ELBOW = 7, 8
LEFT_WRIST, RIGHT_WRIST = 9, 10
LEFT_HIP, RIGHT_HIP = 11, 12
LEFT_KNEE, RIGHT_KNEE = 13, 14
LEFT_ANKLE, RIGHT_ANKLE = 15, 16
HEAD, NECK, HIP = 17, 18, 19
LEFT_BIG_TOE, RIGHT_BIG_TOE = 20, 21
LEFT_SMALL_TOE, RIGHT_SMALL_TOE = 22, 23
LEFT_HEEL, RIGHT_HEEL = 24, 25

# 顺序必须与 MMPose halpe26 数据集定义完全一致
KEYPOINT_NAMES: tuple[str, ...] = (
    'nose',
    'left_eye', 'right_eye',
    'left_ear', 'right_ear',
    'left_shoulder', 'right_shoulder',
    'left_elbow', 'right_elbow',
    'left_wrist', 'right_wrist',
    'left_hip', 'right_hip',
    'left_knee', 'right_knee',
    'left_ankle', 'right_ankle',
    'head', 'neck', 'hip',
    'left_big_toe', 'right_big_toe',
    'left_small_toe', 'right_small_toe',
    'left_heel', 'right_heel',
)

NAME_TO_INDEX: dict[str, int] = {n: i for i, n in enumerate(KEYPOINT_NAMES)}

# 骨架连线（来源：MMPose halpe26 skeleton_info，颜色按左/右/中轴区分，BGR）
# (点A, 点B, 侧别)  侧别: 'left' / 'right' / 'mid'
SKELETON_LINKS: tuple[tuple[int, int, str], ...] = (
    (LEFT_ANKLE, LEFT_KNEE, 'left'),
    (LEFT_KNEE, LEFT_HIP, 'left'),
    (LEFT_HIP, HIP, 'left'),
    (LEFT_ANKLE, LEFT_BIG_TOE, 'left'),
    (LEFT_ANKLE, LEFT_SMALL_TOE, 'left'),
    (LEFT_ANKLE, LEFT_HEEL, 'left'),
    (RIGHT_ANKLE, RIGHT_KNEE, 'right'),
    (RIGHT_KNEE, RIGHT_HIP, 'right'),
    (RIGHT_HIP, HIP, 'right'),
    (RIGHT_ANKLE, RIGHT_BIG_TOE, 'right'),
    (RIGHT_ANKLE, RIGHT_SMALL_TOE, 'right'),
    (RIGHT_ANKLE, RIGHT_HEEL, 'right'),
    (HEAD, NECK, 'mid'),
    (NECK, HIP, 'mid'),
    (NECK, LEFT_SHOULDER, 'left'),
    (LEFT_SHOULDER, LEFT_ELBOW, 'left'),
    (LEFT_ELBOW, LEFT_WRIST, 'left'),
    (NECK, RIGHT_SHOULDER, 'right'),
    (RIGHT_SHOULDER, RIGHT_ELBOW, 'right'),
    (RIGHT_ELBOW, RIGHT_WRIST, 'right'),
    (LEFT_EYE, RIGHT_EYE, 'mid'),
    (NOSE, LEFT_EYE, 'mid'),
    (NOSE, RIGHT_EYE, 'mid'),
    (LEFT_EYE, LEFT_EAR, 'left'),
    (RIGHT_EYE, RIGHT_EAR, 'right'),
    (LEFT_EAR, LEFT_SHOULDER, 'left'),
    (RIGHT_EAR, RIGHT_SHOULDER, 'right'),
)

SIDE_COLORS = {  # BGR
    'left': (60, 200, 60),
    'right': (0, 140, 255),
    'mid': (200, 160, 60),
}

# 关节角定义: 键名 -> (近端点, 关节顶点, 远端点)；伸直=180°
ANGLE_DEFS: dict[str, tuple[int, int, int]] = {
    'left_knee': (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE),
    'right_knee': (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE),
    'left_hip': (LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE),
    'right_hip': (RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE),
    'left_ankle': (LEFT_KNEE, LEFT_ANKLE, LEFT_BIG_TOE),
    'right_ankle': (RIGHT_KNEE, RIGHT_ANKLE, RIGHT_BIG_TOE),
    'left_elbow': (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST),
    'right_elbow': (RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST),
}

ANGLE_DISPLAY_NAMES = {
    'left_knee': '左膝', 'right_knee': '右膝',
    'left_hip': '左髋', 'right_hip': '右髋',
    'left_ankle': '左踝', 'right_ankle': '右踝',
    'left_elbow': '左肘', 'right_elbow': '右肘',
}


def _mmpose_halpe26_config_path() -> Path | None:
    """返回已安装 MMPose 包内 halpe26 数据集配置路径（不存在则 None）。"""
    try:
        import mmpose  # noqa: F401
    except ImportError:
        return None
    p = Path(mmpose.__file__).parent / '.mim' / 'configs' / '_base_' / 'datasets' / 'halpe26.py'
    return p if p.exists() else None


def mmpose_keypoint_names() -> list[str] | None:
    """从 MMPose 元数据读取 halpe26 点名（按索引顺序）；不可用时返回 None。"""
    path = _mmpose_halpe26_config_path()
    if path is None:
        return None
    from mmengine.config import Config
    info = Config.fromfile(str(path)).dataset_info['keypoint_info']
    return [info[i]['name'] for i in range(len(info))]


def verify_against_mmpose(model_keypoint_names: list[str] | None = None) -> None:
    """校验本模块常量与 MMPose 元数据（及实际加载模型）是否一致。

    - 任一不一致直接抛 RuntimeError，避免静默使用错误的关键点顺序。
    - MMPose 未安装时跳过（仅单元测试场景）。
    """
    ref = mmpose_keypoint_names()
    if ref is not None and tuple(ref) != KEYPOINT_NAMES:
        raise RuntimeError(
            'Halpe-26 关键点定义与 MMPose 元数据不一致：\n'
            f'本模块: {KEYPOINT_NAMES}\nMMPose: {tuple(ref)}')
    if model_keypoint_names is not None:
        if tuple(model_keypoint_names) != KEYPOINT_NAMES:
            raise RuntimeError(
                '已加载模型的关键点定义不是 Halpe-26（可能误用了 COCO-17 等模型）：\n'
                f'模型输出: {tuple(model_keypoint_names)}')


def body_height_px(kpts: 'object') -> float | None:
    """用头顶(HEAD)到双踝中点的像素距离估计身体尺度（用于阈值归一化）。

    kpts: (F, 26, 3) 关键点数组（x, y, score），无效点为 NaN。
    返回视频中位数身高像素；样本不足返回 None。
    """
    import numpy as np
    arr = np.asarray(kpts, dtype=float)
    if arr.ndim != 3 or arr.shape[1] != NUM_KEYPOINTS:
        return None
    head_y = arr[:, HEAD, 1]
    ank_y = (arr[:, LEFT_ANKLE, 1] + arr[:, RIGHT_ANKLE, 1]) / 2
    h = np.abs(head_y - ank_y)   # 图像 y 向下：头顶 y < 踝 y，取绝对值
    h = h[np.isfinite(h)]
    return float(np.median(h)) if len(h) >= 3 and np.median(h) > 10 else None
