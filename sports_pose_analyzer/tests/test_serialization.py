"""序列化契约测试（仅依赖 numpy，无 GPU / 无 mmpose / 无 torch）。

覆盖：
- FrameRecord.from_arrays + to_dict 往返（NaN→None、bbox 四元组、status 保留）
- Event.to_dict 数值精度
- ProjectManifest.to_dict 含规范必填字段
- write_json 把 NaN/Inf 序列化为 null
"""
import json

import numpy as np
import pytest

from app.common.data_models import (
    Event, FrameRecord, KeypointRecord, ProjectManifest, write_json)
from app.common.halpe26 import KEYPOINT_NAMES, NUM_KEYPOINTS


def _sample_kpts(n_nan: int = 0) -> np.ndarray:
    """构造 (26,3) 关键点数组；前 n_nan 个点置为无效（x/y=NaN）。"""
    rng = np.random.default_rng(42)
    arr = rng.uniform(0.0, 639.0, size=(NUM_KEYPOINTS, 3))
    arr[:, 2] = rng.uniform(0.50, 0.99, size=NUM_KEYPOINTS)   # score 通道
    for i in range(n_nan):
        arr[i, 0] = np.nan
        arr[i, 1] = np.nan
    return arr


def _frame_record_from_dict(d: dict) -> FrameRecord:
    """把 to_dict 的结果重建为 FrameRecord（往返用）。"""
    def to_kpts(items):
        return [KeypointRecord(k['name'], k['x'], k['y'], k['score'])
                for k in items]
    return FrameRecord(
        frame_index=d['frame_index'],
        timestamp_ms=d['timestamp_ms'],
        status=d['status'],
        person_bbox_xyxy=d['person_bbox_xyxy'],
        detection_score=d['detection_score'],
        pose_quality=d['pose_quality'],
        raw_keypoints=to_kpts(d['raw_keypoints']),
        filtered_keypoints=to_kpts(d['filtered_keypoints']))


def test_frame_record_roundtrip_nan_bbox_status():
    """from_arrays → to_dict 往返：NaN 变 None、bbox 四元组保留、status 保留。"""
    raw = _sample_kpts(n_nan=3)        # 前 3 个点无效
    filtered = _sample_kpts(n_nan=1)   # 前 1 个点无效
    bbox = np.array([10.0, 20.0, 300.0, 450.5])
    rec = FrameRecord.from_arrays(
        frame_index=17, timestamp_ms=566.666,
        status='person_not_found',
        bbox=bbox, det_score=0.9123, pose_quality=0.55,
        raw=raw, filtered=filtered)
    d = rec.to_dict()

    # 基本字段
    assert d['frame_index'] == 17
    assert d['timestamp_ms'] == 566.67          # 2 位小数
    assert d['status'] == 'person_not_found'    # status 原样保留
    assert d['detection_score'] == 0.9123
    assert d['pose_quality'] == 0.55

    # bbox 四元组（round 1）
    assert d['person_bbox_xyxy'] == [10.0, 20.0, 300.0, 450.5]

    # 点数量与名称顺序
    assert len(d['raw_keypoints']) == NUM_KEYPOINTS
    assert [k['name'] for k in d['raw_keypoints']] == list(KEYPOINT_NAMES)

    # 无效点 NaN → None（x/y），score 仍保留原始值
    for i in range(3):
        assert d['raw_keypoints'][i]['x'] is None
        assert d['raw_keypoints'][i]['y'] is None
        assert d['raw_keypoints'][i]['score'] == pytest.approx(
            raw[i, 2], abs=1e-4)
    assert d['filtered_keypoints'][0]['x'] is None
    assert d['filtered_keypoints'][0]['y'] is None

    # 有效点数值保留（round 2）
    assert d['raw_keypoints'][3]['x'] == pytest.approx(raw[3, 0], abs=1e-2)
    assert d['raw_keypoints'][10]['y'] == pytest.approx(raw[10, 1], abs=1e-2)

    # dict → FrameRecord → dict 幂等往返
    assert _frame_record_from_dict(d).to_dict() == d


def test_frame_record_none_fields():
    """raw/filtered/bbox 为 None 时导出 null。"""
    rec = FrameRecord.from_arrays(
        frame_index=0, timestamp_ms=0.0, status='ok',
        bbox=None, det_score=None, pose_quality=None,
        raw=None, filtered=None)
    d = rec.to_dict()
    assert d['status'] == 'ok'
    assert d['person_bbox_xyxy'] is None
    assert d['detection_score'] is None
    assert d['pose_quality'] is None
    assert d['raw_keypoints'] is None
    assert d['filtered_keypoints'] is None


def test_event_to_dict_precision():
    """Event.to_dict：时间 1 位、数值 2 位、置信度 3 位小数。"""
    e = Event(type='min_left_knee_angle', frame_index=132,
              timestamp_ms=4400.5678, value=83.45678,
              unit='deg', confidence=0.87654)
    d = e.to_dict()
    assert d['type'] == 'min_left_knee_angle'
    assert d['frame_index'] == 132
    assert d['timestamp_ms'] == 4400.6     # round 1
    assert d['value'] == 83.46             # round 2
    assert d['unit'] == 'deg'
    assert d['confidence'] == 0.877        # round 3


def test_project_manifest_required_fields():
    """ProjectManifest.to_dict 含全部规范必填字段。"""
    m = ProjectManifest(
        source_video='projects/demo/source_cfr.mp4', fps=29.97,
        frame_count=450, width=1920, height=1080,
        pose_model='rtmpose-m-halpe26-256x192',
        pose_input_size=[192, 256],
        detector='RTMDet-m (COCO/Objects365 person)',
        created_at='2026-08-25T10:30:00')
    d = m.to_dict()

    required = ['schema_version', 'source_video', 'fps', 'frame_count',
                'width', 'height', 'pose_model', 'pose_input_size',
                'detector', 'created_at', 'analysis_status']
    for k in required:
        assert k in d, f'缺少规范必填字段: {k}'

    assert d['schema_version'] == '1.0'
    assert d['analysis_status'] == 'completed'    # 默认值
    assert d['pose_input_size'] == [192, 256]
    assert d['fps'] == 29.97 and d['frame_count'] == 450

    # 规范必填字段应排在附加统计字段之前（字段顺序按 dataclass 定义序）
    keys = list(d.keys())
    assert keys.index('analysis_status') < keys.index('valid_frames')
    assert keys[0] == 'source_video'


def test_write_json_nan_serialized_as_null(tmp_path):
    """write_json 把 NaN/Inf 序列化为 null，且不产生非标准 JSON 字面量。"""
    payload = {
        'nan': float('nan'),
        'np_nan': np.float64('nan'),
        'inf': float('inf'),
        'nested': {'list': [1.0, float('nan'), None]},
        'ok': 3.14,
        '中文': '姿态丢失',
    }
    p = tmp_path / 'out' / 'data.json'   # 顺带验证父目录自动创建
    write_json(p, payload)

    text = p.read_text(encoding='utf-8')
    assert 'NaN' not in text
    assert 'Infinity' not in text

    data = json.loads(text)
    assert data['nan'] is None
    assert data['np_nan'] is None
    assert data['inf'] is None
    assert data['nested']['list'][1] is None
    assert data['ok'] == 3.14
    assert data['中文'] == '姿态丢失'    # ensure_ascii=False：中文原样输出
