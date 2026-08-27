"""小工具：断点下载权重文件。"""
from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path


def download_if_missing(path: Path, url: str, progress_cb=None) -> Path:
    """权重不存在时下载（curl 断点续传优先，回退 urllib）。"""
    path = Path(path)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.part')
    curl = shutil.which('curl')
    if curl:
        r = subprocess.run(
            [curl, '-L', '--retry', '5', '--retry-delay', '2', '-C', '-',
             '-o', str(tmp), url],
            capture_output=True, timeout=7200)
        if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(path)
            return path
    # 回退 urllib（无断点续传）
    print(f'下载 {url} -> {path}')
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, 'wb') as f:
        total = int(resp.headers.get('Content-Length', 0))
        done = 0
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress_cb and total:
                progress_cb(done / total)
    if tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(path)
        return path
    raise RuntimeError(f'下载失败: {url}')
