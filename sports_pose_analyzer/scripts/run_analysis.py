"""命令行分析入口（无 GUI，用于批处理与冒烟测试）。

用法:
    python scripts/run_analysis.py <video_path> [--model KEY] [--device cuda:0]
                                   [--no-fp16] [--projects-root DIR]
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

# 允许从项目根目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.defaults import MODEL_REGISTRY  # noqa: E402
from app.config.settings import UserSettings, load_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='离线单人运动姿态分析（CLI）')
    parser.add_argument('video', help='输入视频路径')
    parser.add_argument('--model', default=None,
                        choices=list(MODEL_REGISTRY.keys()),
                        help='姿态模型 key')
    parser.add_argument('--device', default=None, help='如 cuda:0 / cpu')
    parser.add_argument('--no-fp16', action='store_true', help='禁用 FP16')
    parser.add_argument('--projects-root', default=None,
                        help='项目输出根目录')
    parser.add_argument('--height', type=float, default=None,
                        help='运动员真实身高（米），启用像素→米换算')
    args = parser.parse_args()

    settings = load_settings()
    if args.model:
        settings.model_key = args.model
    if args.device:
        settings.device = args.device
    if args.no_fp16:
        settings.fp16 = False
    if args.projects_root:
        settings.projects_root = args.projects_root
    if args.height:
        settings.athlete_height_m = args.height

    from app.pipeline.orchestrator import AnalysisPipeline
    from app.pipeline.errors import PipelineCancelled

    cancel = threading.Event()
    pipeline = AnalysisPipeline(settings)

    def progress(stage: str, pct: int, detail: str):
        print(f'\r[{pct:3d}%] {stage} {detail}'.ljust(78), end='',
              flush=True)

    print(f'视频: {args.video}')
    print(f'模型: {settings.model_key} | 设备: {settings.device} | '
          f'FP16: {settings.fp16}')
    try:
        result = pipeline.run(args.video, progress_cb=progress,
                              cancel_event=cancel)
    except PipelineCancelled:
        print('\n已取消')
        return 130
    except Exception as e:
        print(f'\n失败: {e}')
        raise

    print('\n' + '=' * 60)
    print('分析完成')
    print('=' * 60)
    s = result.summary
    m = result.manifest
    print(f'项目目录   : {result.project_dir}')
    print(f'总帧数     : {s.total_frames}')
    print(f'有效姿态帧 : {s.valid_frames} ({s.valid_ratio * 100:.1f}%)')
    print(f'平均质量   : {s.avg_pose_quality:.3f}')
    print(f'推理耗时   : {m.inference_ms_per_frame:.1f} ms/帧')
    for name, st in s.angle_stats.items():
        print(f'  {name:<12} min={st["min"]:6.1f}  max={st["max"]:6.1f}  '
              f'mean={st["mean"]:6.1f}')
    print(f'事件数     : {len(s.events)}')
    for w in s.warnings:
        print(f'警告: {w}')
    print('\n产物:')
    for k, p in result.paths.items():
        print(f'  {k:<18} {p}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
