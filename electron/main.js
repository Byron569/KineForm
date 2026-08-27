'use strict';

// KineForm Electron 壳主进程
// 范式参考：nirs4all-webapp BackendManager
// 流程：探测空闲端口 -> spawn 后端子进程 -> /api/health 轮询就绪 -> 打开窗口 -> 退出时杀后端进程树

const { app, BrowserWindow, dialog, ipcMain, Menu } = require('electron');
const { spawn, exec, execSync } = require('child_process');
const path = require('path');
const net = require('net');
const fs = require('fs');
const { pathToFileURL } = require('url');

// ---------- 路径（相对本文件解析，不写死盘符） ----------
const PROJECT_ROOT = path.join(__dirname, '..');
const BACKEND_DIR = path.join(PROJECT_ROOT, 'backend');
const PYTHON_EXE = path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe');
const UI_INDEX = path.join(PROJECT_ROOT, 'kineform UI', 'index.html');
// 应用图标（窗口/任务栏；多尺寸 ICO 由 kineform UI/assets/icons/kineform-mark.svg
// 经 Chromium 光栅化生成，放在 build/ 下，electron-builder 打包时同目录自动采用）
const APP_ICON = path.join(__dirname, 'build', 'icon.ico');

// ---------- 全局状态 ----------
const isDev = process.env.KINEFORM_DEV === '1';
let backendPort = null; // 窗口创建前即已确定，preload 可同步获取
let pyProc = null;      // 后端子进程
let logStream = null;   // backend.log 追加写流
let cleaned = false;    // before-quit 重复触发防护 / 有意退出标志
let win = null;         // 主窗口（提升为模块级：菜单回调与 IPC 需在窗口创建前/销毁后安全引用）

// 本机实测（2026-08）：Electron 33 在此机器上独立 GPU 子进程启动即失败
// （exit_code=0xC0000135 DLL 缺失，反复崩溃后主进程 FATAL "GPU process isn't usable"），
// 渲染进程在默认 sandbox 下同样崩溃。以下三开关为此机器实证必需的兼容组合：
//   disableHardwareAcceleration + in-process-gpu：GPU 软件渲染且不 spawn GPU 子进程；
//   no-sandbox：渲染进程默认 sandbox 下无法启动。
// KineForm 为本地表单类 UI、内容全部本地可信，此组合为成熟可接受做法。
app.disableHardwareAcceleration();
app.commandLine.appendSwitch('in-process-gpu');
app.commandLine.appendSwitch('no-sandbox');

// ---------- 日志：%APPDATA%/KineForm/logs/backend.log ----------
function initLog() {
  const dir = path.join(app.getPath('appData'), 'KineForm', 'logs');
  fs.mkdirSync(dir, { recursive: true });
  logStream = fs.createWriteStream(path.join(dir, 'backend.log'), { flags: 'a' });
}

function log(tag, text) {
  if (!logStream) return;
  const body = String(text).replace(/\s+$/, '');
  logStream.write(`[${new Date().toISOString()}] [${tag}] ${body}\n`);
}

// ---------- 探测空闲端口 ----------
function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
  });
}

// ---------- 等待后端就绪（100ms 间隔轮询） ----------
async function waitForHealth(port, timeoutMs = 30000) {
  const url = `http://127.0.0.1:${port}/api/health`;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url); // 内置 fetch（Node18+/Electron33+ 均支持）
      if (res.ok) return;
    } catch (_) {
      // 尚未就绪，继续轮询
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`后端健康检查超时（${timeoutMs}ms）：${url}`);
}

// ---------- 启动后端子进程 ----------
function startBackend(port) {
  const args = ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                '--port', String(port)];
  log('main', `spawn: ${PYTHON_EXE} ${args.join(' ')} (cwd=${BACKEND_DIR})`);
  pyProc = spawn(PYTHON_EXE, args, {
    cwd: BACKEND_DIR,
    windowsHide: true, // 隐藏 python 控制台窗口
    env: { ...process.env, PYTHONUNBUFFERED: '1' }, // 保证日志及时落盘
  });

  // 子进程输出转发到日志文件（附时间戳前缀）
  pyProc.stdout.on('data', (d) => log('stdout', d));
  pyProc.stderr.on('data', (d) => log('stderr', d));

  // 意外退出（非退出清理期）：提示用户并退出应用
  // P0 简单处理，后续可升级为自动重启
  pyProc.once('exit', (code, signal) => {
    log('main', `backend exited (code=${code}, signal=${signal})`);
    if (!cleaned) {
      dialog.showErrorBox('KineForm 后端已退出',
        `后端服务进程意外退出（code=${code}），应用即将关闭。`);
      app.exit(1);
    }
  });

  // spawn 失败（如 python.exe 不存在）
  pyProc.once('error', (err) => {
    log('main', `backend spawn error: ${err.message}`);
    if (!cleaned) {
      dialog.showErrorBox('KineForm 后端启动失败',
        `无法启动后端服务进程：\n${err.message}`);
      app.exit(1);
    }
  });
}

// 启动失败路径的同步清理（app.exit 不经过 before-quit，需主动杀子进程避免孤儿）
function killBackendNow() {
  if (!pyProc || !pyProc.pid) return;
  cleaned = true; // 标记为有意退出，抑制 exit 事件里的崩溃弹窗
  if (process.platform === 'win32') {
    try {
      execSync(`taskkill /PID ${pyProc.pid} /T /F`);
    } catch (_) { /* 进程可能已退出 */ }
  } else {
    try { pyProc.kill('SIGTERM'); } catch (_) { /* 已退出 */ }
  }
  pyProc = null;
}

// ---------- 应用生命周期 ----------
app.whenReady().then(async () => {
  initLog();
  log('main', `KineForm starting: mode=${isDev ? 'dev' : 'production'}, `
    + `electron=${process.versions.electron}, node=${process.versions.node}`);

  try {
    if (isDev) {
      // 开发模式：假定后端已手动启动在 8000 端口，不 spawn 子进程
      backendPort = 8000;
      log('main', 'KINEFORM_DEV=1: skip spawning backend, expect http://127.0.0.1:8000');
    } else {
      backendPort = await findFreePort();
      startBackend(backendPort);
    }
    await waitForHealth(backendPort);
    log('main', `backend ready at http://127.0.0.1:${backendPort}`);

    // 同步 IPC：端口此刻已确定，preload 可安全 sendSync 获取
    ipcMain.on('backend:getPort', (event) => {
      event.returnValue = backendPort;
    });

    // 原生文件选择对话框：渲染进程经 preload 的 KineFormDialog.openVideo 调用。
    // 这是 UI 能力桥（打开对话框/菜单事件），非数据通道——业务数据仍全走 HTTP（既有架构决策）。
    ipcMain.handle('dialog:openVideo', async () => {
      const result = await dialog.showOpenDialog(win, {
        title: '选择要分析的视频',
        properties: ['openFile'],
        filters: [
          { name: '视频文件', extensions: ['mp4', 'mov', 'avi', 'mkv', 'webm', 'm4v'] },
        ],
      });
      return {
        canceled: result.canceled,
        path: result.canceled ? null : (result.filePaths[0] || null),
      };
    });

    // 自定义应用菜单（替代默认菜单：默认 File 项无中文标签、无法打开文件）。
    // setApplicationMenu 为应用级设置，窗口创建前调用即对首窗口即时生效；
    // 菜单点击/快捷键在窗口创建前后都可能触发，回调内对模块级 win 做空值防护。
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      {
        label: '文件(&F)',
        submenu: [
          {
            label: '分析视频…',
            accelerator: 'CmdOrCtrl+O',
            click: () => {
              if (win) win.webContents.send('menu:analyze-video');
            },
          },
          { type: 'separator' },
          { label: '退出', click: () => app.quit() }, // 走 before-quit 退出清理链，与窗口关闭一致
        ],
      },
      {
        label: '视图(&V)',
        submenu: [
          { label: '重新加载', role: 'reload' },
          { label: '切换开发者工具', role: 'toggleDevTools' }, // 排查问题用
        ],
      },
    ]));

    win = new BrowserWindow({
      width: 1440,
      height: 900,
      icon: APP_ICON,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        preload: path.join(__dirname, 'preload.js'),
      },
    });
    // 注意：loadFile() 在此机器实测不可靠（ERR_FAILED），须用 loadURL + pathToFileURL
    // 显式编码路径（"kineform UI" 含空格，编码为 %20）。
    win.on('closed', () => { win = null; }); // 防止菜单/IPC 向已销毁窗口 send
    await win.loadURL(pathToFileURL(UI_INDEX).href);
  } catch (err) {
    const msg = String((err && err.message) || err);
    log('main', `startup failed: ${msg}`);
    killBackendNow();
    dialog.showErrorBox('KineForm 启动失败', msg);
    app.exit(1);
  }
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('before-quit', (e) => {
  if (cleaned) return; // 重复触发防护
  cleaned = true;
  e.preventDefault();

  if (process.platform === 'win32' && pyProc && pyProc.pid) {
    // Windows：taskkill /T 杀整个进程树，避免孤儿 uvicorn/python
    exec(`taskkill /PID ${pyProc.pid} /T /F`, (err) => {
      if (err) log('main', `taskkill failed: ${err.message}`);
      setTimeout(() => app.exit(0), 300);
    });
  } else if (pyProc) {
    // 非 win32：SIGTERM 优雅杀，5s 强杀兜底
    const finish = () => setTimeout(() => app.exit(0), 300);
    const force = setTimeout(() => {
      try { pyProc.kill('SIGKILL'); } catch (_) { /* 已退出 */ }
      finish();
    }, 5000);
    pyProc.once('exit', () => {
      clearTimeout(force);
      finish();
    });
    pyProc.kill('SIGTERM');
  } else {
    app.exit(0);
  }
});
