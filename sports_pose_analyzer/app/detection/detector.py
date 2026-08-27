"""人体检测器封装（仅保留 person 类）与单人主体选择。"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..common.data_models import Detection
from ..config.defaults import DetectorSpec


class PersonDetector:
    """RTMDet 人体检测器（MMDetection）。"""

    def __init__(self, spec: DetectorSpec, device: str = 'cuda:0',
                 score_thr: float | None = None):
        from ..common.io_utils import download_if_missing
        download_if_missing(spec.checkpoint_path, spec.checkpoint_url)
        from mmdet.apis import init_detector
        self.spec = spec
        self.device = device
        self.score_thr = spec.score_thr if score_thr is None else score_thr
        self.model = init_detector(str(spec.config_path),
                                   str(spec.checkpoint_path), device=device)

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """返回 person 类检测框列表（按分数降序）。

        每次调用前重置 default_scope 为 mmdet：mmpose 的推理接口会把
        全局 scope 切到 mmpose，若不重置，mmdet pipeline 中的
        PackDetInputs 等 transform 会在 mmpose 注册表里找不到。
        """
        from mmdet.apis import inference_detector
        from mmengine.registry import init_default_scope
        init_default_scope('mmdet')
        result = inference_detector(self.model, frame_bgr)
        pred = result.pred_instances
        labels = pred.labels.cpu().numpy()
        scores = pred.scores.cpu().numpy()
        boxes = pred.bboxes.cpu().numpy()
        out = []
        for box, score, label in zip(boxes, scores, labels):
            if label == 0 and score > self.score_thr:
                out.append(Detection(float(box[0]), float(box[1]),
                                     float(box[2]), float(box[3]),
                                     float(score)))
        out.sort(key=lambda d: d.score, reverse=True)
        return out


def iou_xyxy(a, b) -> float:
    """两个 xyxy 框的 IoU。"""
    ax1, ay1, ax2, ay2 = a[0], a[1], a[2], a[3]
    bx1, by1, bx2, by2 = b[0], b[1], b[2], b[3]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(ix2 - ix1, 0.0), max(iy2 - iy1, 0.0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(ax2 - ax1, 0.0) * max(ay2 - ay1, 0.0)
    area_b = max(bx2 - bx1, 0.0) * max(by2 - by1, 0.0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def select_subject(detections: list[Detection],
                   prev_bbox: Optional[tuple],
                   min_iou: float = 0.3) -> Optional[Detection]:
    """单人主体选择（不维护 Track ID）。

    规则：
    - 无检测 → None；
    - 无上一帧框（首帧/上一帧丢失）→ 取最高分；
    - 有上一帧框 → 取与上一帧框 IoU 最大的候选；
      若最大 IoU < min_iou（主体突变），回退最高分。
    """
    if not detections:
        return None
    if prev_bbox is None:
        return detections[0]
    best, best_iou = None, -1.0
    for det in detections:
        v = iou_xyxy(det.xyxy, prev_bbox)
        if v > best_iou:
            best, best_iou = det, v
    if best is not None and best_iou >= min_iou:
        return best
    return detections[0]
