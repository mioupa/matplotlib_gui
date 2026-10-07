// Python 側（PyScript）との橋渡し。Python は window 上の関数を直接呼ぶため window に公開する。
window.__matplotDataReady = false;
window.setMatplotDataReady = (ready) => {
  window.__matplotDataReady = !!ready;
};
window.downloadDataUri = (filename, dataUri) => {
  if (!filename || !dataUri) return;
  const link = document.createElement("a");
  link.href = dataUri;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
};

let renderTimer = null;
let loadTimer = null;


export const hasSelectedFile = () => {
  const fileInput = document.getElementById("fileInput");
  return !!(fileInput && fileInput.files && fileInput.files.length > 0);
};
export const canAutoRender = () => !!window.__matplotDataReady;
export const runPyAction = (name) => {
  const fn = window[name];
  if (typeof fn === "function") {
    fn();
    return true;
  }
  return false;
};

export const scheduleRender = (delay = 250) => {
  if (renderTimer) window.clearTimeout(renderTimer);
  renderTimer = window.setTimeout(() => {
    renderTimer = null;
    if (canAutoRender()) {
      runPyAction("requestRender");
    }
  }, delay);
};

export const scheduleLoad = (delay = 350) => {
  if (!hasSelectedFile()) return;
  if (loadTimer) window.clearTimeout(loadTimer);
  loadTimer = window.setTimeout(() => {
    loadTimer = null;
    window.setMatplotDataReady(false);
    runPyAction("requestLoadColumns");
  }, delay);
};
