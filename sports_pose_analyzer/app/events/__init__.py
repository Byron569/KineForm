"""关键事件检测。"""

from .detector import (
    ACTION_TEMPLATES,
    EVENT_DETECTORS,
    detect_events,
    register_event_detector,
)
from . import gait  # noqa: F401  触发步态检测器注册

__all__ = [
    'EVENT_DETECTORS',
    'ACTION_TEMPLATES',
    'register_event_detector',
    'detect_events',
]
