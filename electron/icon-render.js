'use strict';

// 图标再生成管线（第一步）：用 Chromium canvas 把 kineform-mark.svg 光栅化为
// 多尺寸 PNG。用法（cwd=electron）：npx electron icon-render.js
// 第二步：D:\KineForm\.venv\Scripts\python.exe _build_ico.py
//   （PNG→icon.ico 多尺寸合成 + 像素校验 + 清理中间产物）
// 图标源文件变更后跑这两步即可，main.js 与打包配置无需改动
// （electron-builder 约定自动采用 build/icon.ico）。
// 与主进程 main.js 保持同一 GPU 兼容三开关（本机 Electron 33 实证必需）。
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');

const SVG_PATH = path.join(__dirname, '..', 'kineform UI', 'assets', 'icons',
                           'kineform-mark.svg');
const OUT_DIR = path.join(__dirname, 'build');
const SIZES = [16, 24, 32, 48, 64, 128, 256];

app.disableHardwareAcceleration();
app.commandLine.appendSwitch('in-process-gpu');
app.commandLine.appendSwitch('no-sandbox');

app.whenReady().then(async () => {
  try {
    const svg = fs.readFileSync(SVG_PATH, 'utf8');
    fs.mkdirSync(OUT_DIR, { recursive: true });

    // data: URL 页面内联渲染函数：SVG(矢量) → 指定尺寸 canvas → PNG dataURL。
    // data URL 图片不污染 canvas，toDataURL 可用；Chromium 按目标尺寸矢量光栅化。
    const html = `<!DOCTYPE html><html><body><canvas id="c"></canvas><script>
      window.render = (size) => new Promise((resolve, reject) => {
        const img = new Image();
        img.onerror = () => reject(new Error('SVG load failed'));
        img.onload = () => {
          const c = document.getElementById('c');
          c.width = size; c.height = size;
          const ctx = c.getContext('2d');
          ctx.clearRect(0, 0, size, size);
          ctx.drawImage(img, 0, 0, size, size);
          resolve(c.toDataURL('image/png'));
        };
        img.src = 'data:image/svg+xml;base64,' + btoa(${JSON.stringify(svg)});
      });
    </script></body></html>`;

    const win = new BrowserWindow({
      show: false,
      webPreferences: { offscreen: true },
    });
    await win.loadURL('data:text/html;charset=utf-8,'
                      + encodeURIComponent(html));

    for (const s of SIZES) {
      const dataUrl = await win.webContents.executeJavaScript(
        `window.render(${s})`);
      const buf = Buffer.from(dataUrl.split(',')[1], 'base64');
      fs.writeFileSync(path.join(OUT_DIR, `icon-${s}.png`), buf);
      console.log(`rendered icon-${s}.png (${buf.length} bytes)`);
    }
    win.destroy();
    app.exit(0);
  } catch (err) {
    console.error('icon-render failed:', err && err.message);
    app.exit(1);
  }
});
