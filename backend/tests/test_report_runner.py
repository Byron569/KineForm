"""report_runner 单元测试（纯 pytest，不起 FastAPI）。

通过文件路径直接加载被测模块（纯标准库实现），不依赖 backend 包结构
与 tests/conftest.py，避免与并行开发的框架层相互干扰。
"""
from __future__ import annotations

import importlib.util
import json
import threading
from datetime import datetime
from pathlib import Path

import pytest

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / 'app' / 'services' / 'report_runner.py')


def _load_module():
    spec = importlib.util.spec_from_file_location(
        'report_runner_under_test', _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rr = _load_module()
ValidationError = rr.ValidationError
TaskCancelled = rr.TaskCancelled

VIDEO_ID = '2026-08-26_103000_test_running'
FPS = 30.0
TASK_ID = 't_20260826_110001'

# 每帧指标源数据（motion.json 的唯一事实来源）
FRAME_METRICS = [
    {'left_knee_angle': 150.0, 'right_knee_angle': 149.0, 'pose_quality': 0.95},
    {'left_knee_angle': 142.13, 'right_knee_angle': 138.7, 'pose_quality': 0.94},
    {'left_knee_angle': 138.7, 'right_knee_angle': 141.0, 'pose_quality': 0.93},
]


# ---------- 假项目目录构造 ----------

def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding='utf-8')


def _make_motion() -> dict:
    return {
        'schema_version': '1.0',
        'video_id': VIDEO_ID,
        'source_video': 'source_cfr.mp4',
        'fps': FPS,
        'frame_count': 3,
        'width': 1920,
        'height': 1080,
        'created_at': '2026-08-26T10:30:00',
        'frames': [
            {'frameIndex': i,
             'timestampMs': round(i * 1000.0 / FPS, 1),
             'metrics': dict(FRAME_METRICS[i])}
            for i in range(3)
        ],
    }


def _make_events() -> dict:
    """2 条 events（帧 0 / 帧 2）+ 完整 gait_summary 小样例。

    steps 区间设计：step1 = [0, 2)（td=0, next_td=2），step2 = [2, ∞)
    （td=2, next_td=None，末步）→ 帧 1 落 step1、帧 2 落 step2。
    """
    return {
        'schema_version': '1.0',
        'events': [
            {'type': 'left_touchdown', 'frame_index': 0, 'timestamp_ms': 0.0,
             'value': 12.5, 'unit': 'px', 'confidence': 0.9},
            {'type': 'right_touchdown', 'frame_index': 2, 'timestamp_ms': 66.7,
             'value': -8.3, 'unit': 'px', 'confidence': 0.88},
        ],
        'gait_summary': {
            'left': {
                'n_touchdowns': 1, 'n_toe_offs': 1,
                'contact_time_ms': {'mean': 200.0, 'std': 0.0,
                                    'min': 200.0, 'max': 200.0, 'count': 1},
                'flight_time_ms': None, 'stride_time_ms': None,
                'stance_ratio': None,
            },
            'right': {
                'n_touchdowns': 1, 'n_toe_offs': 1,
                'contact_time_ms': {'mean': 180.0, 'std': 0.0,
                                    'min': 180.0, 'max': 180.0, 'count': 1},
                'flight_time_ms': None, 'stride_time_ms': None,
                'stance_ratio': None,
            },
            'step_time_ms': {'mean': 350.0, 'std': 0.0,
                             'min': 350.0, 'max': 350.0, 'count': 1},
            'cadence_spm': 171.4,
            'body_scale': {'body_height_px': 720.0, 'leg_length_px': 340.0},
            'steps': [
                {
                    'side': 'left', 'td_frame': 0, 'to_frame': 1,
                    'next_td_frame': 2, 'contact_time_ms': 200.0,
                    'flight_time_ms': 100.0, 'stride_time_ms': 300.0,
                    'stance_ratio': 0.6667,
                    'touchdown': {'knee_angle': 150.0, 'foot_pelvis_dist_px': 12.5},
                    'midstance': {'frame': 1, 'knee_angle': 142.13},
                    'toe_off': {'knee_angle': 142.13},
                    'stance': {'min_knee_angle': 140.0, 'knee_collapse_deg': 10.0,
                               'knee_rom_deg': 12.0, 'ankle_rom_deg': 20.0,
                               'hip_rom_deg': 15.0},
                    'swing': {'min_knee_angle': 65.0, 'max_thigh_angle': 35.0},
                },
                {
                    'side': 'right', 'td_frame': 2, 'to_frame': 3,
                    'next_td_frame': None, 'contact_time_ms': 180.0,
                    'flight_time_ms': None, 'stride_time_ms': None,
                    'stance_ratio': None,
                    'touchdown': {'knee_angle': 141.0, 'foot_pelvis_dist_px': -8.3},
                    'midstance': None,
                    'toe_off': {'knee_angle': 138.7},
                    'stance': {'min_knee_angle': 137.0, 'knee_collapse_deg': 4.0,
                               'knee_rom_deg': 6.0, 'ankle_rom_deg': 18.0,
                               'hip_rom_deg': 12.0},
                    'swing': {'min_knee_angle': None, 'max_thigh_angle': None},
                },
            ],
            'reference_comparison': [
                {
                    'reference': 'sprint_max_v',
                    'source': 'Mattes 2021', 'sample': 'n=22',
                    'angle_definition': 'knee-ankle-toe',
                    'context': None, 'disclaimer': '2D 投影误差',
                    'skipped_metrics': {},
                    'steps': [{'td_frame': 0, 'side': 'left',
                               'metrics': {'touchdown.knee_angle': {
                                   'value': 150.0, 'ref_mean': 145.0,
                                   'ref_sd': 10.0, 'z': 0.5,
                                   'band': 'common'}}}],
                    'side_summary': {
                        'left': {'touchdown.knee_angle': {
                            'mean_z': 0.5, 'band': 'common', 'n': 1}},
                        'right': {'touchdown.knee_angle': {
                            'mean_z': -1.2, 'band': 'deviated', 'n': 1}},
                    },
                    'global': {},
                },
            ],
            'fatigue_trend': {
                'n_steps': 2, 'split_at': 1,
                'halves': {'first': {'contact_time_ms': 200.0},
                           'second': {'contact_time_ms': 180.0}},
                'delta': {'contact_time_ms': -20.0},
                'delta_pct': {'contact_time_ms': -10.0},
            },
            'takeoff_steps': [
                {'td_frame': 2, 'side': 'right', 'contact_time_ms': 180.0,
                 'contact_median_ms': 190.0, 'ratio': 0.947,
                 'confidence': 0.338, 'reason': '触地时间超过中位数 1.4 倍'},
            ],
        },
    }


def _make_project(tmp_path: Path, *, with_events: bool = True) -> Path:
    """构造假项目目录，返回 outputs_dir（项目目录的父目录）。"""
    outputs_dir = tmp_path / 'projects'
    project_dir = outputs_dir / VIDEO_ID
    project_dir.mkdir(parents=True)
    _write_json(project_dir / 'motion.json', _make_motion())
    if with_events:
        _write_json(project_dir / 'events.json', _make_events())
    return outputs_dir


def _marker(marker_id: str, frame_index: int, metrics: dict,
            label: str = '测试打点', comment: str = '备注') -> dict:
    return {
        'id': marker_id,
        'frameIndex': frame_index,
        'timestampMs': round(frame_index * 1000.0 / FPS, 1),
        'label': label,
        'comment': comment,
        'metrics': dict(metrics),
    }


def _payload(markers: list) -> dict:
    return {
        'video_id': VIDEO_ID,
        'fps': FPS,
        'frame_count': 3,               # 故意与服务端一致（服务端不信任此值）
        'markers': list(markers),
        'motion': {'source': f'projects/{VIDEO_ID}/motion.json',
                   'sha256': 'deadbeef'},
    }


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


# ---------- 用例 1：validate（三种 400 情形 + 边界合法） ----------

class TestValidate:

    def test_build_runner_factory(self):
        assert isinstance(rr.build_runner(), rr.Runner)

    def test_markers_missing(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        with pytest.raises(ValidationError) as ei:
            rr.Runner().validate({'video_id': VIDEO_ID}, outputs_dir)
        assert ei.value.code == 'markers_empty'
        assert '未包含任何打点标记' in ei.value.message

    def test_markers_empty_list(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        with pytest.raises(ValidationError) as ei:
            rr.Runner().validate({'video_id': VIDEO_ID, 'markers': []},
                                 outputs_dir)
        assert ei.value.code == 'markers_empty'

    def test_unknown_video_dir_missing(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        payload = _payload([_marker('m1', 0, {})])
        payload['video_id'] = 'no_such_project'
        with pytest.raises(ValidationError) as ei:
            rr.Runner().validate(payload, outputs_dir)
        assert ei.value.code == 'unknown_video'
        assert 'no_such_project' in ei.value.message

    def test_unknown_video_motion_missing(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        (outputs_dir / VIDEO_ID / 'motion.json').unlink()   # 目录在、motion 不在
        with pytest.raises(ValidationError) as ei:
            rr.Runner().validate(_payload([_marker('m1', 0, {})]), outputs_dir)
        assert ei.value.code == 'unknown_video'

    def test_frame_index_negative(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        with pytest.raises(ValidationError) as ei:
            rr.Runner().validate(
                _payload([_marker('m1', -1, {})]), outputs_dir)
        assert ei.value.code == 'frame_index_out_of_range'

    def test_frame_index_equal_to_frame_count(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        with pytest.raises(ValidationError) as ei:
            rr.Runner().validate(
                _payload([_marker('m1', 3, {})]), outputs_dir)   # frame_count=3
        assert ei.value.code == 'frame_index_out_of_range'

    def test_frame_index_last_frame_is_valid(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        rr.Runner().validate(
            _payload([_marker('m1', 2, {})]), outputs_dir)       # 2 == count-1

    def test_server_frame_count_prevails(self, tmp_path):
        """请求体 frame_count 篡改为 99，仍以服务端 motion.json 为准。"""
        outputs_dir = _make_project(tmp_path)
        payload = _payload([_marker('m1', 3, {})])
        payload['frame_count'] = 99
        with pytest.raises(ValidationError) as ei:
            rr.Runner().validate(payload, outputs_dir)
        assert ei.value.code == 'frame_index_out_of_range'


# ---------- 用例 2：run 成功（step 匹配 / event_context / summary / 返回值） ----------

class TestRunSuccess:

    def test_full_run(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        project_dir = outputs_dir / VIDEO_ID
        markers = [
            _marker('m_ok', 1, FRAME_METRICS[1]),               # 帧1：快照与源一致
            _marker('m_last', 2, FRAME_METRICS[2]),             # 帧2：末步区间
        ]
        calls = []

        result = rr.Runner().run(
            _payload(markers), outputs_dir,
            progress_cb=lambda stage, percent, detail:
                calls.append((stage, percent, detail)),
            cancel_event=None, task_id=TASK_ID)

        # 进度：校验0 → 持久化40 → 报告80 → 完成100
        assert [(s, p) for s, p, _ in calls] == [
            ('validate', 0), ('persist', 40), ('report', 80), ('done', 100)]

        # 返回值
        assert result['result_path'] == f'outputs/{VIDEO_ID}/score_report.json'
        assert result['markers_saved'] == 2
        assert result['report_path'] == str(
            (project_dir / 'score_report.json').resolve())
        assert Path(result['report_path']).is_file()

        # submitted_markers.json：最新快照（覆盖式）
        saved = _read(project_dir / 'submitted_markers.json')
        assert saved['schema_version'] == '1.0'
        assert saved['task_id'] == TASK_ID
        assert saved['video_id'] == VIDEO_ID
        assert saved['markers'] == markers
        assert saved['motion'] == _payload(markers)['motion']
        assert datetime.fromisoformat(saved['submitted_at']).tzinfo is not None

        # score_report.json：顶层
        report = _read(project_dir / 'score_report.json')
        assert report['schema_version'] == '1.0'
        assert report['task_id'] == TASK_ID
        assert report['video_id'] == VIDEO_ID
        assert datetime.fromisoformat(report['created_at']).tzinfo is not None

        m_ok, m_last = report['markers']
        # 帧 1：基础字段原样
        assert m_ok['id'] == 'm_ok'
        assert m_ok['frameIndex'] == 1
        assert m_ok['timestampMs'] == markers[0]['timestampMs']
        assert m_ok['label'] == '测试打点'
        assert m_ok['comment'] == '备注'
        assert m_ok['metrics'] == markers[0]['metrics']
        assert 'metrics_checked' not in m_ok          # 快照一致 → 省略
        # 帧 1 落在 step1 区间 [0, 2)：td_frame=0 的左侧完整步
        assert m_ok['step']['td_frame'] == 0
        assert m_ok['step']['side'] == 'left'
        assert m_ok['step']['next_td_frame'] == 2
        assert m_ok['step']['stance']['knee_collapse_deg'] == 10.0
        # 帧 1 命中两条邻近事件（帧0 delta=-1、帧2 delta=+1）
        assert m_ok['event_context'] == [
            {'type': 'left_touchdown', 'frame_index': 0,
             'timestamp_ms': 0.0, 'delta_frames': -1},
            {'type': 'right_touchdown', 'frame_index': 2,
             'timestamp_ms': 66.7, 'delta_frames': 1},
        ]
        # 帧 2 落在 step2 末步区间 [2, ∞)：td_frame 最大者
        assert m_last['step']['td_frame'] == 2
        assert m_last['step']['side'] == 'right'
        assert m_last['step']['next_td_frame'] is None

        # summary：gait 字段齐
        summary = report['summary']
        assert summary['n_markers'] == 2
        gait = summary['gait']
        assert gait['n_steps'] == 2
        assert gait['cadence_spm'] == 171.4
        assert gait['contact_time_ms_mean'] == 190.0    # (200.0+180.0)/2
        rc = gait['reference_comparison']
        assert rc[0]['reference'] == 'sprint_max_v'
        assert rc[0]['side_summary']['left'][
            'touchdown.knee_angle']['mean_z'] == 0.5
        assert summary['fatigue_trend'] == {
            'n_steps': 2, 'delta': {'contact_time_ms': -20.0}}
        assert summary['takeoff_steps'] == \
            _make_events()['gait_summary']['takeoff_steps']

    def test_run_revalidates_defensively(self, tmp_path):
        """run 内部重新 validate：坏 payload 直接抛 ValidationError。"""
        outputs_dir = _make_project(tmp_path)
        with pytest.raises(ValidationError):
            rr.Runner().run(_payload([]), outputs_dir,
                            None, None, TASK_ID)


# ---------- 用例 3：metrics 快照一致性校验 ----------

class TestMetricsChecked:

    def test_mismatch_and_consistent(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        project_dir = outputs_dir / VIDEO_ID
        markers = [
            _marker('m_bad', 1, {'left_knee_angle': 160.0,     # 源 142.13，差>0.01
                                 'right_knee_angle': 138.7}),   # 一致
            _marker('m_good', 0, FRAME_METRICS[0]),             # 全一致
        ]
        rr.Runner().run(_payload(markers), outputs_dir,
                        None, None, TASK_ID)
        report = _read(project_dir / 'score_report.json')
        m_bad, m_good = report['markers']

        assert m_bad['metrics_checked']['mismatches'] == {
            'left_knee_angle': {'submitted': 160.0, 'server': 142.13}}
        assert m_bad['metrics_checked']['metrics'] == FRAME_METRICS[1]
        assert 'metrics_checked' not in m_good

    def test_tolerance_boundary_exactly_0_01(self, tmp_path):
        """差恰好等于 0.01（不超过容差）→ 视为一致，省略 metrics_checked。"""
        outputs_dir = _make_project(tmp_path)
        project_dir = outputs_dir / VIDEO_ID
        markers = [_marker('m_tol', 0, {'left_knee_angle': 150.01})]  # 源 150.0
        rr.Runner().run(_payload(markers), outputs_dir,
                        None, None, TASK_ID)
        report = _read(project_dir / 'score_report.json')
        assert 'metrics_checked' not in report['markers'][0]


# ---------- 用例 4：取消 ----------

class TestCancel:

    def test_cancelled_before_start_writes_nothing(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        project_dir = outputs_dir / VIDEO_ID
        cancel_event = threading.Event()
        cancel_event.set()
        with pytest.raises(TaskCancelled):
            rr.Runner().run(_payload([_marker('m1', 1, {})]), outputs_dir,
                            None, cancel_event, TASK_ID)
        assert not (project_dir / 'submitted_markers.json').exists()
        assert not (project_dir / 'score_report.json').exists()


# ---------- 用例 5：metrics 为空 dict ----------

class TestEmptyMetrics:

    def test_empty_metrics_dict_still_produces_report(self, tmp_path):
        outputs_dir = _make_project(tmp_path)
        project_dir = outputs_dir / VIDEO_ID
        markers = [_marker('m_empty', 1, {})]
        result = rr.Runner().run(_payload(markers), outputs_dir,
                                 None, None, TASK_ID)
        report = _read(project_dir / 'score_report.json')
        entry = report['markers'][0]
        assert result['markers_saved'] == 1
        assert entry['metrics'] == {}
        assert 'metrics_checked' not in entry
        assert entry['step']['td_frame'] == 0          # step 匹配不依赖 metrics
        assert entry['event_context'] is not None


# ---------- 用例 6：项目目录只有 motion.json（无 events.json） ----------

class TestNoEventsFile:

    def test_motion_only_project(self, tmp_path):
        outputs_dir = _make_project(tmp_path, with_events=False)
        project_dir = outputs_dir / VIDEO_ID
        markers = [_marker('m1', 1, FRAME_METRICS[1])]
        result = rr.Runner().run(_payload(markers), outputs_dir,
                                 None, None, TASK_ID)
        assert result['markers_saved'] == 1

        report = _read(project_dir / 'score_report.json')
        entry = report['markers'][0]
        assert entry['step'] is None
        assert entry['event_context'] is None
        assert report['summary'] == {
            'n_markers': 1, 'gait': None,
            'fatigue_trend': None, 'takeoff_steps': None}
