// Python（window.mplgui）との唯一の窓口。設定は JSON 文字列で渡し、結果の JSON を UI へ反映する。
// - 再描画は設定変更の 250ms 後（デバウンス）、読込はファイル/ヘッダ 0ms・区切り文字 450ms。保存設定の変更では再描画しない。
// - 描画の要求はすべてここを通る（世代番号・合体・起動待ちキューは Step 5 でここに足す）。
import { subscribe, toJson, getSettings } from "./state.js";
import { setStatus } from "./ui/notify.js";
import { showPlot } from "./ui/plotView.js";
import { showPreview } from "./ui/dataPreview.js";
import { setColumns } from "./ui/series.js";

const RENDER_DELAY_MS = 250;
const LOAD_DELAY_MS = { file: 0, header: 0, delimiter: 450 };
const JP_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@Sans2.004/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf";

const root = document.documentElement;
let api = null; // window.mplgui（Python 側が登録）
let selectedFile = null;
let dataReady = false;
let renderTimer = null;
let loadTimer = null;
let renderGeneration = 0;
let loadGeneration = 0;
let customCodeProvider = () => null; // 有効なカスタムコードの文字列、無効なら null
let readyCallbacks = [];
let fontPromise = null;

const setDataState = (state) => {
  dataReady = state === "ready";
  root.dataset.dataState = state; // none | loading | ready | error
};
const setRenderState = (state) => {
  root.dataset.renderState = state; // idle | pending | rendering
};

export const isPythonReady = () => api !== null;
export const canAutoRender = () => dataReady;
export const setCustomCodeProvider = (fn) => {
  customCodeProvider = fn;
};

const callPython = (name, ...args) => JSON.parse(api[name](...args));

const reportError = (error) => {
  setStatus(error.message, true, error.detail || "");
};
const reportException = (err, context) => {
  const detail = `context: ${context}\n${err && err.stack ? err.stack : String(err)}`;
  setStatus("内部エラーが発生しました。もう一度操作してください。", true, detail);
};

// 日本語フォントは初回の描画前に1回だけ取得する。失敗しても描画は継続する（A6 で font-cache.js に置き換える）。
const ensureFont = () => {
  if (!fontPromise) {
    fontPromise = (async () => {
      try {
        const response = await fetch(JP_FONT_URL);
        if (!response.ok) return;
        const bytes = new Uint8Array(await response.arrayBuffer());
        api.registerFont(bytes);
      } catch (_) {
        // フォールバックフォントで継続する
      }
    })();
  }
  return fontPromise;
};

const doRender = async () => {
  if (!api) return;
  const generation = ++renderGeneration;
  root.dataset.renderGeneration = String(generation);
  setRenderState("rendering");
  try {
    await ensureFont();
    if (generation !== renderGeneration) return; // 新しい要求が出ている
    const result = callPython("render", toJson(), customCodeProvider());
    if (generation !== renderGeneration) return;
    if (result.ok) {
      showPlot(result.image, generation);
      setStatus(`描画に成功しました（${result.seriesCount}系列、スキップ${result.skipRows}行）。`);
    } else {
      reportError(result.error);
    }
  } catch (err) {
    if (generation === renderGeneration) reportException(err, "render");
  } finally {
    if (generation === renderGeneration) setRenderState("idle");
  }
};

const doLoad = async () => {
  if (!api || !selectedFile) return;
  const generation = ++loadGeneration;
  setDataState("loading");
  try {
    const bytes = new Uint8Array(await selectedFile.arrayBuffer());
    if (generation !== loadGeneration) return;
    const loadJson = JSON.stringify({ version: getSettings().version, load: getSettings().load });
    const result = callPython("loadFile", selectedFile.name, bytes, loadJson);
    if (generation !== loadGeneration) return;
    if (!result.ok) {
      setDataState("error");
      reportError(result.error);
      return;
    }
    setColumns(result.columns);
    showPreview(result.preview);
    setDataState("ready");
    setStatus("");
    await doRender();
  } catch (err) {
    if (generation === loadGeneration) {
      setDataState("error");
      reportException(err, "loadFile");
    }
  }
};

export const scheduleRender = (delay = RENDER_DELAY_MS) => {
  if (renderTimer) window.clearTimeout(renderTimer);
  setRenderState("pending");
  renderTimer = window.setTimeout(() => {
    renderTimer = null;
    if (api && canAutoRender()) {
      doRender();
    } else {
      setRenderState("idle");
    }
  }, delay);
};

export const scheduleLoad = (delay = LOAD_DELAY_MS.file) => {
  if (!selectedFile) return;
  setDataState("loading"); // 読込が済むまで自動再描画は止める
  if (loadTimer) window.clearTimeout(loadTimer);
  loadTimer = window.setTimeout(() => {
    loadTimer = null;
    doLoad();
  }, delay);
};

export const renderNow = () => {
  if (api && canAutoRender()) doRender();
};

export const selectFile = (file) => {
  selectedFile = file || null;
  scheduleLoad(LOAD_DELAY_MS.file);
};

const downloadDataUri = (filename, dataUri) => {
  if (!filename || !dataUri) return;
  const link = document.createElement("a");
  link.href = dataUri;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
};

export const saveNow = async () => {
  if (!api) return;
  try {
    await ensureFont();
    const result = callPython("save", toJson(), customCodeProvider());
    if (!result.ok) {
      reportError(result.error);
      return;
    }
    downloadDataUri(result.filename, result.dataUri);
    setStatus(`描画データを保存しました: ${result.filename}`);
  } catch (err) {
    reportException(err, "save");
  }
};

export const getDefaultCustomCode = () => (api ? api.defaultCustomCode() : "");
export const onPythonReady = (fn) => {
  if (api) fn();
  else readyCallbacks.push(fn);
};

const handlePythonReady = () => {
  if (api || !window.mplgui) return;
  api = window.mplgui;
  root.dataset.appState = "ready";
  const callbacks = readyCallbacks;
  readyCallbacks = [];
  for (const fn of callbacks) fn();
  scheduleLoad(LOAD_DELAY_MS.file); // 起動前に選ばれたファイルがあれば読み込む
};

// 設定の変更を、読込・再描画・無視のどれにするか振り分ける
const routeChange = (_settings, change) => {
  if (change.origin !== "user") return;
  const path = change.kind === "path" ? change.path : "series";
  if (path.startsWith("load.")) {
    scheduleLoad(path === "load.delimiter" ? LOAD_DELAY_MS.delimiter : LOAD_DELAY_MS.header);
  } else if (!path.startsWith("save.")) {
    scheduleRender();
  }
};

export const initBridge = () => {
  root.dataset.appState = root.dataset.appState || "starting";
  setDataState("none");
  setRenderState("idle");
  subscribe(routeChange);
  if (window.mplgui) handlePythonReady();
  else window.addEventListener("mplgui-ready", handlePythonReady, { once: true });
};
