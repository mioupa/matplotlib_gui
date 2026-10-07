// エントリ。DOM 構築後（module は defer）に UI を初期化する。
// notify.js は parentNode 系例外のハンドラを登録するため、必ず最初に import する。
import "./ui/notify.js";
import { scheduleLoad, scheduleRender } from "./bridge.js";
import { bindColorPanelOutsideClick } from "./ui/colorPicker.js";
import { bindCustomCodeEvents } from "./ui/customCode.js";
import { syncSaveFormatOptions, bindSaveFormatEvents } from "./ui/saveFormat.js";
import {
  bindSeriesEvents,
  syncMarkerSizeForPlotType,
  syncPlotTypeUI,
  syncY2LabelUI,
} from "./ui/series.js";
// series.js は window.ensureSeriesItems / window.refreshSeriesColumnOptions を公開する。
// bridge.js は window.setMatplotDataReady / window.downloadDataUri / window.__matplotDataReady を公開する。
// Python 側が登録する window.requestRender / window.requestLoadColumns は bridge.js から呼ぶ。

const fileInput = document.getElementById("fileInput");
const delimiterInput = document.getElementById("delimiter");
const hasHeaderInput = document.getElementById("hasHeader");

if (fileInput) {
  fileInput.addEventListener("change", () => scheduleLoad(0));
}
if (delimiterInput) {
  delimiterInput.addEventListener("input", () => scheduleLoad(450));
}
if (hasHeaderInput) {
  hasHeaderInput.addEventListener("change", () => scheduleLoad(0));
}

bindSeriesEvents();
bindSaveFormatEvents();
bindCustomCodeEvents();
bindColorPanelOutsideClick();

const autoRenderIds = [
  "xColumn",
  "title",
  "xLabel",
  "yLabel",
  "y2Label",
  "xScale",
  "yScale",
  "xMin",
  "xMax",
  "yMin",
  "yMax",
  "y2Scale",
  "y2Min",
  "y2Max",
  "fontSize",
  "showMajorGrid",
  "showMinorGrid",
  "legendLocation",
  "figWidth",
  "figHeight",
  "subplotLeft",
  "subplotRight",
  "subplotBottom",
  "subplotTop",
  "skipRows",
];
for (const id of autoRenderIds) {
  const el = document.getElementById(id);
  if (!el) continue;
  el.addEventListener("input", () => scheduleRender());
  el.addEventListener("change", () => scheduleRender());
}

window.ensureSeriesItems();
syncPlotTypeUI();
syncMarkerSizeForPlotType();
syncY2LabelUI();
syncSaveFormatOptions();
