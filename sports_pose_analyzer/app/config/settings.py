"""用户设置（JSON 持久化，文件不入库）。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .defaults import (DEFAULT_MODEL_KEY, PROJECTS_DIR, SETTINGS_PATH,
                       OverlayConfig, Thresholds, preset_full)


@dataclass
class UserSettings:
    tracker_path: str = ''
    projects_root: str = str(PROJECTS_DIR)
    last_video_dir: str = ''
    model_key: str = DEFAULT_MODEL_KEY
    fp16: bool = True
    device: str = 'cuda:0'
    # 运动员真实身高（米）：提供后启用像素→米换算（步长 m、跑速 m/s）
    athlete_height_m: Optional[float] = None
    thresholds: Thresholds = field(default_factory=Thresholds)
    overlay: OverlayConfig = field(default_factory=preset_full)


def load_settings(path: Path | None = None) -> UserSettings:
    path = Path(path) if path else SETTINGS_PATH
    s = UserSettings()
    if not path.exists():
        return s
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return s  # 损坏则回退默认
    for k, v in data.items():
        if k == 'thresholds' and isinstance(v, dict):
            s.thresholds = Thresholds(**{kk: vv for kk, vv in v.items()
                                         if kk in Thresholds.__dataclass_fields__})
        elif k == 'overlay' and isinstance(v, dict):
            s.overlay = OverlayConfig(**{kk: vv for kk, vv in v.items()
                                         if kk in OverlayConfig.__dataclass_fields__})
        elif hasattr(s, k):
            setattr(s, k, v)
    return s


def save_settings(s: UserSettings, path: Path | None = None) -> None:
    path = Path(path) if path else SETTINGS_PATH
    path.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=2),
                    encoding='utf-8')


def find_tracker(settings: UserSettings, extra_candidates: Optional[list[str]] = None) -> Optional[str]:
    """返回可用的 Tracker 路径：设置优先，其次常见安装位置。"""
    from .defaults import TRACKER_COMMON_PATHS
    cands = ([settings.tracker_path] if settings.tracker_path else []) \
        + list(TRACKER_COMMON_PATHS) + list(extra_candidates or [])
    for p in cands:
        if p and Path(p).is_file() and p.lower().endswith('.exe'):
            return p
    return None
