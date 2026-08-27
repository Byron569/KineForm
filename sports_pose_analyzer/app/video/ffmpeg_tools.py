"""ffmpeg/ffprobe 工具：探测、CFR 标准化、H.264 转码与音频合成。

无系统 ffprobe 时降级为 OpenCV + ffmpeg stderr 解析，
无法确凿证明 CFR 的一律按 VFR 处理（安全转 CFR）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import cv2

from ..common.data_models import VideoInfo

_FFMPEG_ENV = 'SPORTS_POSE_FFMPEG'
_ffmpeg_cache: str | None = None


def find_ffmpeg() -> str:
    """ffmpeg 可执行文件路径：环境变量 > PATH > imageio-ffmpeg 内置。"""
    global _ffmpeg_cache
    if _ffmpeg_cache:
        return _ffmpeg_cache
    env = os.environ.get(_FFMPEG_ENV)
    if env and Path(env).is_file():
        _ffmpeg_cache = env
        return env
    which = shutil.which('ffmpeg')
    if which:
        _ffmpeg_cache = which
        return which
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            _ffmpeg_cache = exe
            return exe
    except Exception:
        pass
    raise RuntimeError(
        '未找到 ffmpeg。请安装 ffmpeg 并加入 PATH，或 pip install imageio-ffmpeg，'
        f'或设置环境变量 {_FFMPEG_ENV} 指向 ffmpeg 可执行文件。')


def find_ffprobe() -> str | None:
    which = shutil.which('ffprobe')
    return which


def _run(cmd: list[str], timeout: int = 7200) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


# ---------------- 探测 ----------------
def _parse_duration(text: str) -> float | None:
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', text)
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def _parse_video_stream(text: str) -> tuple[str | None, tuple[int, int] | None,
                                            float | None, float | None, bool]:
    """从 ffmpeg -i stderr 解析视频流: (codec, (w,h), fps, tbr, has_fps_token)。"""
    for line in text.splitlines():
        if 'Stream #' in line and 'Video:' in line:
            codec = line.split('Video:')[1].split(',')[0].strip()
            size = re.search(r'(\d{2,5})x(\d{2,5})', line)
            wh = (int(size.group(1)), int(size.group(2))) if size else None
            fps = re.search(r'([\d.]+)\s*fps', line)
            tbr = re.search(r'([\d.]+)\s*tbr', line)
            has_fps = fps is not None
            f = float(fps.group(1)) if fps else None
            t = float(tbr.group(1)) if tbr else None
            return codec, wh, f, t, has_fps
    return None, None, None, None, False


def _has_audio_stream(text: str) -> bool:
    return any('Stream #' in l and 'Audio:' in l for l in text.splitlines())


def _probe_with_ffprobe(path: Path, ffprobe: str) -> VideoInfo | None:
    """ffprobe JSON 精确探测（可用时）。"""
    try:
        r = _run([ffprobe, '-v', 'quiet', '-print_format', 'json',
                  '-show_format', '-show_streams', str(path)], timeout=120)
        if r.returncode != 0:
            return None
        import json
        data = json.loads(r.stdout)
        vstream = next((s for s in data.get('streams', [])
                        if s.get('codec_type') == 'video'), None)
        if vstream is None:
            return None
        astream = next((s for s in data.get('streams', [])
                        if s.get('codec_type') == 'audio'), None)
        w, h = int(vstream['width']), int(vstream['height'])

        def rate(x: str | None) -> float | None:
            if not x:
                return None
            num, den = x.split('/')
            den = float(den or 1)
            return float(num) / den if den else None

        r_fps = rate(vstream.get('r_frame_rate'))
        avg_fps = rate(vstream.get('avg_frame_rate'))
        fps = avg_fps or r_fps or 0.0
        dur = float(data.get('format', {}).get('duration', 0) or 0)
        nb = vstream.get('nb_frames')
        frames = int(nb) if nb and str(nb).isdigit() else int(round(fps * dur))
        vfr = None
        if r_fps and avg_fps:
            vfr = abs(r_fps - avg_fps) / max(r_fps, 1e-6) > 0.01
        return VideoInfo(
            path=str(path), width=w, height=h, fps=fps, frame_count=frames,
            duration_s=dur, vfr=vfr, has_audio=astream is not None,
            video_codec=vstream.get('codec_name', ''), probe_method='ffprobe')
    except Exception:
        return None


def probe_video(path: str | Path) -> VideoInfo:
    """探测视频信息。优先 ffprobe，降级 OpenCV+ffmpeg stderr。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f'视频不存在: {path}')
    ffprobe = find_ffprobe()
    if ffprobe:
        info = _probe_with_ffprobe(path, ffprobe)
        if info is not None:
            return info

    # 降级方案：cv2 基础信息 + ffmpeg stderr 补充
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f'无法打开视频: {path}')
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    duration, codec, has_audio, fps_tok, tbr, has_fps_token = 0.0, '', False, None, None, False
    try:
        r = _run([find_ffmpeg(), '-hide_banner', '-i', str(path)], timeout=120)
        err = r.stderr or ''
        duration = _parse_duration(err) or 0.0
        codec, _, fps_tok, tbr, has_fps_token = _parse_video_stream(err)
        has_audio = _has_audio_stream(err)
    except Exception:
        pass

    if fps <= 0:
        fps = fps_tok or (frames / duration if duration > 0 else 0) or 30.0

    # VFR 启发式判断（缺 fps token / fps≠tbr / 帧数与 fps×时长不符）
    suspects = []
    if not has_fps_token:
        suspects.append('视频流未报告恒定 fps')
    if fps_tok and tbr and abs(fps_tok - tbr) / max(fps_tok, 1e-6) > 0.01:
        suspects.append(f'fps({fps_tok}) 与 tbr({tbr}) 不一致')
    if duration > 0 and frames > 0:
        expect = fps * duration
        if abs(frames - expect) / max(expect, 1) > 0.02:
            suspects.append(f'帧数({frames}) 与 fps×时长({expect:.0f}) 不符')
    vfr = True if suspects else False  # 无法确凿证明 → 保守按 VFR
    return VideoInfo(
        path=str(path), width=w, height=h, fps=fps, frame_count=frames,
        duration_s=duration, vfr=vfr, has_audio=has_audio,
        video_codec=codec or '', probe_method='opencv+ffmpeg')


def count_frames_exact(path: str | Path) -> int:
    """完整解码统计真实帧数（供校验用，较慢）。"""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f'无法打开视频: {path}')
    n = 0
    while cap.read()[0]:
        n += 1
    cap.release()
    return n


# ---------------- CFR 标准化 ----------------
def ensure_cfr(src: str | Path, dst: Path, info: VideoInfo | None = None,
               progress_cb=None) -> VideoInfo:
    """确保输出为 CFR 视频到 dst；已确认 CFR 则直接复制，否则 ffmpeg 转换。

    返回 dst 的权威 VideoInfo（重新探测）。
    """
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if info is None:
        info = probe_video(src)

    if info.vfr is False:
        shutil.copyfile(src, dst)
    else:
        fps = round(info.fps, 3)
        if not (0 < fps <= 240):
            fps = 30.0
        cmd = [find_ffmpeg(), '-y', '-i', str(src),
               '-map', '0:v:0', '-map', '0:a:0?',
               '-r', str(fps), '-fps_mode', 'cfr',
               '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
               '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '192k',
               '-movflags', '+faststart', str(dst)]
        r = _run(cmd)
        if r.returncode != 0:
            # 旧版 ffmpeg 兼容：-vsync cfr
            cmd = [c if c != '-fps_mode' else '-vsync' for c in cmd]
            r = _run(cmd)
            if r.returncode != 0:
                tail = (r.stderr or '')[-1500:]
                raise RuntimeError(f'CFR 转换失败:\n{tail}')
        if progress_cb:
            progress_cb(1.0)
    return probe_video(dst)


# ---------------- 转码/封装 ----------------
def transcode_h264(video_in: Path, dst: Path, audio_source: Path | None = None,
                   crf: int = 18, preset: str = 'medium') -> bool:
    """将 OpenCV 写出的中间视频转码为 H.264 yuv420p；可选合成外部音频。成功返回 True。"""
    video_in, dst = Path(video_in), Path(dst)
    cmd = [find_ffmpeg(), '-y', '-i', str(video_in)]
    if audio_source is not None:
        cmd += ['-i', str(audio_source),
                '-map', '0:v:0', '-map', '1:a:0?']
    else:
        cmd += ['-map', '0:v:0']
    cmd += ['-c:v', 'libx264', '-preset', preset, '-crf', str(crf),
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
            '-shortest', '-movflags', '+faststart', str(dst)]
    try:
        r = _run(cmd)
        ok = r.returncode == 0 and dst.exists() and dst.stat().st_size > 0
        if not ok:
            print((r.stderr or '')[-1000:])
        return ok
    except Exception as e:
        print(f'transcode_h264 失败: {e}')
        return False
