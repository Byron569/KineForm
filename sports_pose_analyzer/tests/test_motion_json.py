"""motion.json 导出契约测试（自研标注客户端的数据源，仅依赖 numpy）。

覆盖：
- 顶层元信息（video_id / fps / frame_count / 分辨率 / frames 长度）
- 单帧 metrics 键齐全（8 关节角 + 8 角速度 + 躯干倾角 + 轨迹 + 速度 + 质量）
- NaN 指标 → null（JSON 不允许 NaN）
- 数值精度（角度/轨迹 2 位、质量 4 位、timestampMs 1 位）
"""
import json

import numpy as np

from app.biomechanics.metrics import compute_metrics
from app.common.data_models import ProjectManifest, SCHEMA_VERSION
from app.exporters.writers import export_motion_json

FPS = 29.97


def _manifest(fps: float = FPS) -> ProjectManifest:
    return ProjectManifest(
        source_video='source_cfr.mp4',
        fps=fps,
        frame_count=3,
        width=1920,
        height=1080,
        pose_model='RTMPose-m Halpe26',
        pose_input_size=[288, 384],
        detector='RTMDet-m',
        created_at='2026-08-26T10:00:00',
    )


def _metrics():
    """3 帧指标：帧 0/1 有效，帧 2 全部 NaN（模拟姿态丢失）。"""
    rng = np.random.default_rng(7)
    kpts = rng.uniform(100.0, 900.0, size=(3, 26, 3))
    kpts[:, :, 2] = 0.9
    kpts[2, :, 0] = np.nan
    kpts[2, :, 1] = np.nan
    ts = np.array([0.0, 1000.0 / FPS, 2000.0 / FPS])
    quality = np.array([0.95, 0.90, 0.0])
    return compute_metrics(
        kpts, FPS,
        frame_indices=np.arange(3), timestamps_ms=ts,
        pose_quality=quality, valid_ratio=np.ones(3),
        missing_ratio=np.array([0.0, 0.0, 1.0]))


def test_motion_json_top_level_fields(tmp_path):
    """顶层元信息完整，frames 与 frame_count 一致。"""
    out = tmp_path / 'motion.json'
    export_motion_json(out, _manifest(), _metrics(), video_id='proj_x')

    d = json.loads(out.read_text(encoding='utf-8'))
    assert d['schema_version'] == SCHEMA_VERSION
    assert d['video_id'] == 'proj_x'
    assert d['source_video'] == 'source_cfr.mp4'
    assert d['fps'] == round(FPS, 3)
    assert d['frame_count'] == 3
    assert d['width'] == 1920 and d['height'] == 1080
    assert d['created_at'] == '2026-08-26T10:00:00'
    assert len(d['frames']) == 3


def test_motion_json_frame_metrics_keys(tmp_path):
    """帧 0 的 metrics 键齐全（打点客户端按此契约取数）。"""
    out = tmp_path / 'motion.json'
    export_motion_json(out, _manifest(), _metrics(), video_id='proj_x')

    d = json.loads(out.read_text(encoding='utf-8'))
    f0 = d['frames'][0]
    assert f0['frameIndex'] == 0
    assert f0['timestampMs'] == 0.0

    m = f0['metrics']
    expected = (
        [f'{s}_{j}_angle' for s in ('left', 'right')
         for j in ('knee', 'hip', 'ankle', 'elbow')]
        + [f'{s}_{j}_angvel' for s in ('left', 'right')
           for j in ('knee', 'hip', 'ankle', 'elbow')]
        + ['torso_lean_angle',
           'left_thigh_angle', 'right_thigh_angle',
           'left_shank_angle', 'right_shank_angle',
           'left_shoulder_angle', 'right_shoulder_angle',
           'pelvis_x', 'pelvis_y', 'pelvis_speed_px_s',
           'head_x', 'head_y',
           'left_heel_x', 'left_heel_y', 'right_heel_x', 'right_heel_y',
           'pose_quality', 'valid_ratio'])
    assert set(m.keys()) == set(expected)
    # 有效帧全部为数值
    assert all(v is not None for v in m.values())


def test_motion_json_nan_frame_is_null(tmp_path):
    """姿态丢失帧（帧 2）全部指标为 null，不产生非法 JSON。"""
    out = tmp_path / 'motion.json'
    export_motion_json(out, _manifest(), _metrics(), video_id='proj_x')

    d = json.loads(out.read_text(encoding='utf-8'))
    f2 = d['frames'][2]
    assert f2['frameIndex'] == 2
    assert f2['timestampMs'] == round(2000.0 / FPS, 1)
    # 角度/轨迹/角速度全部无效
    assert f2['metrics']['left_knee_angle'] is None
    assert f2['metrics']['pelvis_x'] is None
    assert f2['metrics']['left_knee_angvel'] is None
    # pose_quality 是显式给出的 0.0，仍保留数值
    assert f2['metrics']['pose_quality'] == 0.0


def test_motion_json_value_precision(tmp_path):
    """数值精度：角度 2 位、质量 4 位、timestampMs 1 位。"""
    out = tmp_path / 'motion.json'
    export_motion_json(out, _manifest(), _metrics(), video_id='proj_x')

    d = json.loads(out.read_text(encoding='utf-8'))
    f1 = d['frames'][1]
    assert f1['timestampMs'] == round(1000.0 / FPS, 1)
    assert f1['metrics']['pose_quality'] == 0.9
    # 角度值经过 round(…, 2)
    v = f1['metrics']['left_knee_angle']
    assert v == pytest_approx(v, 2)


def pytest_approx(v, nd):
    """round 后的值与自身一致（避免引入 pytest.approx 的导入位置问题）。"""
    return round(v, nd)


def test_motion_json_large_fps_fractional(tmp_path):
    """29.97（30000/1001 类）fps 原样传递，前端按 timestampMs 查表对齐。"""
    out = tmp_path / 'motion.json'
    export_motion_json(out, _manifest(fps=29.9700299), _metrics(),
                       video_id='proj_x')
    d = json.loads(out.read_text(encoding='utf-8'))
    assert d['fps'] == 29.97
    assert d['frames'][1]['timestampMs'] == round(1000.0 / FPS, 1)
