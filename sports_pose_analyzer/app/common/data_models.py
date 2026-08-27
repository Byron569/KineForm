"""共享数据模型（dataclass）与序列化工具。

约定：
- 关键点数组 shape = (F, 26, 3)，通道为 (x, y, score)；
- 无效关键点的 x/y 置为 NaN（score 保留模型原始输出值）；
- 一切运动学序列中无效样本用 NaN 表示。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .halpe26 import KEYPOINT_NAMES, NUM_KEYPOINTS

SCHEMA_VERSION = '1.0'


# ---------------- 基础 ----------------
@dataclass
class VideoInfo:
    """ffprobe/探测得到的视频信息。"""
    path: str
    width: int
    height: int
    fps: float
    frame_count: int          # 探测值（可能不精确，分析以实际解码为准）
    duration_s: float
    vfr: Optional[bool]       # None = 无法判断（探测降级）
    has_audio: bool
    video_codec: str = ''
    probe_method: str = ''    # 'ffprobe' | 'opencv+ffmpeg'


@dataclass
class Detection:
    """单人人体检测框（xyxy 像素坐标 + 置信度）。"""
    x1: float
    y1: float
    x2: float
    y2: float
    score: float

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)


@dataclass
class KeypointRecord:
    """导出 JSON 用的单个关键点。"""
    name: str
    x: Optional[float]
    y: Optional[float]
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {'name': self.name,
                'x': None if self.x is None or not math.isfinite(self.x) else round(float(self.x), 2),
                'y': None if self.y is None or not math.isfinite(self.y) else round(float(self.y), 2),
                'score': round(float(self.score), 4)}


@dataclass
class FrameRecord:
    """keypoints.json 中的单帧记录（符合规范 schema）。"""
    frame_index: int
    timestamp_ms: float
    status: str = 'ok'   # ok | person_not_found | low_pose_confidence
    person_bbox_xyxy: Optional[list[float]] = None
    detection_score: Optional[float] = None
    pose_quality: Optional[float] = None
    raw_keypoints: Optional[list[KeypointRecord]] = None
    filtered_keypoints: Optional[list[KeypointRecord]] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            'frame_index': self.frame_index,
            'timestamp_ms': round(float(self.timestamp_ms), 2),
            'status': self.status,
        }
        d['person_bbox_xyxy'] = (
            [round(v, 1) for v in self.person_bbox_xyxy]
            if self.person_bbox_xyxy is not None else None)
        d['detection_score'] = (
            round(float(self.detection_score), 4)
            if self.detection_score is not None else None)
        d['pose_quality'] = (
            round(float(self.pose_quality), 4)
            if self.pose_quality is not None else None)
        d['raw_keypoints'] = (
            [k.to_dict() for k in self.raw_keypoints]
            if self.raw_keypoints is not None else None)
        d['filtered_keypoints'] = (
            [k.to_dict() for k in self.filtered_keypoints]
            if self.filtered_keypoints is not None else None)
        return d

    @staticmethod
    def from_arrays(frame_index: int, timestamp_ms: float, status: str,
                    bbox: Optional[np.ndarray], det_score: Optional[float],
                    pose_quality: Optional[float],
                    raw: Optional[np.ndarray],
                    filtered: Optional[np.ndarray]) -> 'FrameRecord':
        """从 (26,3) 数组构造。数组通道 (x, y, score)，无效点 x/y=NaN。"""

        def to_records(arr: Optional[np.ndarray]) -> Optional[list[KeypointRecord]]:
            if arr is None:
                return None
            out = []
            for i in range(arr.shape[0]):
                x, y, s = float(arr[i, 0]), float(arr[i, 1]), float(arr[i, 2])
                out.append(KeypointRecord(
                    KEYPOINT_NAMES[i],
                    None if not math.isfinite(x) else x,
                    None if not math.isfinite(y) else y,
                    s))
            return out

        return FrameRecord(
            frame_index=frame_index,
            timestamp_ms=timestamp_ms,
            status=status,
            person_bbox_xyxy=[float(v) for v in bbox] if bbox is not None else None,
            detection_score=det_score,
            pose_quality=pose_quality,
            raw_keypoints=to_records(raw),
            filtered_keypoints=to_records(filtered))


@dataclass
class Event:
    """关键事件（峰值/极值/姿态丢失边界）。"""
    type: str
    frame_index: int
    timestamp_ms: float
    value: float
    unit: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            'type': self.type,
            'frame_index': self.frame_index,
            'timestamp_ms': round(float(self.timestamp_ms), 1),
            'value': round(float(self.value), 2),
            'unit': self.unit,
            'confidence': round(float(self.confidence), 3),
        }


# ---------------- 运动学结果 ----------------
ANGLE_KEYS = ('left_knee', 'right_knee', 'left_hip', 'right_hip',
              'left_ankle', 'right_ankle', 'left_elbow', 'right_elbow')


@dataclass
class MetricsResult:
    """逐帧二维运动学指标（全部为图像坐标系，未标定）。"""
    fps: float
    frame_indices: np.ndarray                 # (F,) int
    timestamps_ms: np.ndarray                 # (F,) float
    angles: dict[str, np.ndarray]             # ANGLE_KEYS -> (F,) 度
    angular_velocity: dict[str, np.ndarray]   # ANGLE_KEYS -> (F,) 度/秒
    torso_lean: np.ndarray                    # (F,) 带符号角度（正=向图像右倾）
    trajectories: dict[str, np.ndarray]       # pelvis/head/left_heel/right_heel -> (F,2) px
    keypoint_speeds: np.ndarray               # (F,26) px/s
    pelvis_speed: np.ndarray                  # (F,) px/s
    pose_quality: np.ndarray                   # (F,) 0..1；无姿态帧为 0
    valid_ratio: np.ndarray                    # (F,) 0..1
    missing_ratio: np.ndarray                  # (F,) 0..1
    symmetry_index: dict[str, float]           # 汇总对称性指标（标量）
    # 节段角（度）：'left/right_thigh' 髋→膝相对水平、
    # 'left/right_shank' 膝→踝相对竖直；旧数据可缺省为空 dict
    segment_angles: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def frame_count(self) -> int:
        return int(len(self.frame_indices))


@dataclass
class ProjectManifest:
    """manifest.json 内容。"""
    source_video: str
    fps: float
    frame_count: int
    width: int
    height: int
    pose_model: str
    pose_input_size: list[int]      # [w, h]
    detector: str
    created_at: str                 # ISO-8601
    analysis_status: str = 'completed'
    schema_version: str = SCHEMA_VERSION
    # 附加统计（非规范必需）
    valid_frames: int = 0
    valid_ratio: float = 0.0
    avg_pose_quality: float = 0.0
    inference_ms_per_frame: float = 0.0
    source_video_original: str = ''
    vfr_converted: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisSummary:
    """分析概览（GUI 与 HTML 报告共用）。"""
    total_frames: int
    valid_frames: int
    valid_ratio: float
    avg_pose_quality: float
    angle_stats: dict[str, dict[str, float]]   # 角度名 -> {min,max,mean}
    events: list[Event] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """一次完整分析的产物。"""
    project_dir: Path
    manifest: ProjectManifest
    summary: AnalysisSummary
    paths: dict[str, Path] = field(default_factory=dict)  # 名称 -> 文件路径
    metrics: Optional[MetricsResult] = None
    # 步态汇总（events.json 的 gait_summary 同源）：body_scale / steps /
    # reference_comparison / fatigue_trend / takeoff_steps；无步态事件
    # 时 steps 为空列表，GUI 按此降级展示
    gait_summary: Optional[dict] = None


# ---------------- 序列化工具 ----------------
def to_jsonable(obj: Any) -> Any:
    """递归把 numpy 类型转成原生 JSON 类型。"""
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if not math.isfinite(v) else v
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def write_json(path: Path | str, payload: Any, *, indent: int = 2) -> None:
    """写 JSON（UTF-8, ensure_ascii=False, NaN→null）。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_jsonable(payload), ensure_ascii=False, indent=indent)
    Path(path).write_text(text, encoding='utf-8')


def kpts_array_to_records(arr: Optional[np.ndarray]) -> Optional[list[KeypointRecord]]:
    """(26,3) 数组 → KeypointRecord 列表（辅助函数）。"""
    if arr is None:
        return None
    return FrameRecord.from_arrays(
        0, 0.0, 'ok', None, None, None, arr, None).raw_keypoints


__all__ = [
    'SCHEMA_VERSION', 'VideoInfo', 'Detection', 'KeypointRecord',
    'FrameRecord', 'Event', 'MetricsResult', 'ProjectManifest',
    'AnalysisSummary', 'AnalysisResult', 'ANGLE_KEYS',
    'to_jsonable', 'write_json', 'kpts_array_to_records',
    'NUM_KEYPOINTS',
]
