'use strict';

// 为什么用 sendSync 而不是 invoke：
// contextBridge.exposeInMainWorld 暴露的对象须被页面同步读取
// （静态原型 app.js 同步读 window.KineFormConfig.apiBaseUrl），
// 而 ipcRenderer.invoke 返回 Promise，无法在 preload 里同步解析出端口值。
// 端口在主进程 loadFile 之前已经确定，因此这里一次性 sendSync 取值是最简成熟做法：
// 仅 preload 阶段发生一次同步往返，开销可忽略，且无死锁风险（主进程并未阻塞等待渲染进程）。
const { contextBridge, ipcRenderer } = require('electron');

const backendPort = ipcRenderer.sendSync('backend:getPort');

contextBridge.exposeInMainWorld('KineFormConfig', {
  apiBaseUrl: 'http://127.0.0.1:' + backendPort,
});

// ---------- UI 能力桥（非数据通道） ----------
// KineFormDialog / KineFormEvents 暴露的是主进程的 UI 能力：
//   KineFormDialog.openVideo     —— 原生文件选择对话框（对应 main.js 的 ipcMain.handle('dialog:openVideo')）；
//   KineFormEvents.onAnalyzeVideo —— 应用菜单「分析视频…」(Ctrl+O) 事件订阅。
// 这不是新的数据通道——业务数据仍全部走 HTTP（上方 KineFormConfig.apiBaseUrl），
// 保持既有前后端解耦架构（渲染进程 <-> FastAPI 直连）不变。
contextBridge.exposeInMainWorld('KineFormDialog', {
  openVideo: () => ipcRenderer.invoke('dialog:openVideo'),
});

contextBridge.exposeInMainWorld('KineFormEvents', {
  // 返回解绑函数：页面卸载前可调用以移除监听，避免重复订阅；
  // 页面重载（视图->重新加载）后 preload 会重新执行，页面侧需重新订阅。
  onAnalyzeVideo: (callback) => {
    const listener = () => callback();
    ipcRenderer.on('menu:analyze-video', listener);
    return () => ipcRenderer.removeListener('menu:analyze-video', listener);
  },
});
