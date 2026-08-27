"""RTMPose Halpe-26 姿态推理封装（注册表驱动，支持 m/l 与 256x192/384x288 切换）。"""
from __future__ import annotations

import numpy as np

from ..common.halpe26 import KEYPOINT_NAMES, NUM_KEYPOINTS, verify_against_mmpose
from ..common.io_utils import download_if_missing
from ..config.defaults import PoseModelSpec


class RTMPoseRunner:
    """Top-down 姿态估计器。estimate(frame, bbox) → (26,3) 数组 [x, y, score]。"""

    def __init__(self, spec: PoseModelSpec, device: str = 'cuda:0',
                 fp16: bool = True):
        download_if_missing(spec.checkpoint_path, spec.checkpoint_url)
        from mmpose.apis import init_model
        self.spec = spec
        self.device = device
        self.model = init_model(str(spec.config_path),
                                str(spec.checkpoint_path), device=device)
        # 关键点元数据校验：防止误用 COCO-17 等非 Halpe-26 模型
        names = None
        if hasattr(self.model, 'dataset_meta'):
            names = self.model.dataset_meta.get('keypoint_names')
        if names is None and hasattr(self.model, 'cfg'):
            meta = self.model.cfg.get('dataset_info') or {}
            names = meta.get('keypoint_info') and None  # 仅结构提示
        verify_against_mmpose(list(names) if names is not None else None)
        self.fp16 = bool(fp16) and str(device).startswith('cuda')
        self._fp16_disabled_warned = False

    @property
    def name(self) -> str:
        return self.spec.display_name

    def estimate(self, frame_bgr: np.ndarray,
                 bbox_xyxy) -> np.ndarray:
        """对单个 bbox 做姿态估计。

        bbox_xyxy: 长度 4 序列 (x1, y1, x2, y2)。
        返回 (26, 3) float32，通道 (x, y, score)。
        """
        from mmpose.apis import inference_topdown
        import torch
        box = np.asarray(bbox_xyxy, dtype=np.float32).reshape(1, 4)
        res = None
        if self.fp16:
            try:
                with torch.autocast('cuda', dtype=torch.float16):
                    res = inference_topdown(self.model, frame_bgr, box)
            except Exception:
                res = None
            if res is not None:
                k, s = self._extract(res)
                if k is not None and (np.isnan(k).any() or np.isinf(k).any()
                                      or np.isnan(s).any()):
                    res = None  # FP16 数值异常 → 回退 FP32
                    self.fp16 = False
                    if not self._fp16_disabled_warned:
                        print('警告: FP16 推理输出异常，已自动切换 FP32。')
                        self._fp16_disabled_warned = True
        if res is None:
            res = inference_topdown(self.model, frame_bgr, box)
        k, s = self._extract(res)
        if k is None:
            return np.full((NUM_KEYPOINTS, 3), np.nan, dtype=np.float32)
        return np.concatenate([k.astype(np.float32),
                               s.astype(np.float32)[:, None]], axis=1)

    @staticmethod
    def _extract(res):
        if not res:
            return None, None
        pred = res[0].pred_instances
        return pred.keypoints[0], pred.keypoint_scores[0]

    @property
    def keypoint_names(self) -> tuple[str, ...]:
        return KEYPOINT_NAMES
