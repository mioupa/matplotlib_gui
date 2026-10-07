// エントリ。DOM 構築後（module は defer）に UI を設定オブジェクトへ結び付ける。
//   画面の入力 → state.js（設定オブジェクト）→ bridge.js が JSON で Python を呼ぶ → 結果を ui/* が描く
import { subscribe } from "./state.js";
import { getDefaultCustomCode, initBridge, onPythonReady, saveNow, selectFile } from "./bridge.js";
import { bindColorPanelOutsideClick } from "./ui/colorPicker.js";
import { bindCustomCodeEvents, initDefaultCode } from "./ui/customCode.js";
import { applyStateToForm, bindForms } from "./ui/forms.js";
import { bindSaveFormatEvents, syncSaveFormatOptions } from "./ui/saveFormat.js";
import { bindSeriesEvents, renderSeriesList, setColumns, syncMarkerSizeDisplay, syncVisibility } from "./ui/series.js";
import { bindTabs } from "./ui/tabs.js";

const fileInput = document.getElementById("fileInput");
if (fileInput) {
  fileInput.addEventListener("change", () => selectFile(fileInput.files && fileInput.files[0]));
}
const savePlotBtn = document.getElementById("savePlotBtn");
if (savePlotBtn) savePlotBtn.addEventListener("click", () => saveNow());

bindTabs();
bindForms();
bindSeriesEvents();
bindSaveFormatEvents();
bindCustomCodeEvents();
bindColorPanelOutsideClick();

// state の変更に応じた画面の更新（再描画・読込の予約は bridge.js が購読して行う）
subscribe((_settings, change) => {
  if (change.kind === "series-list") {
    renderSeriesList();
  } else {
    syncVisibility();
    if (change.kind === "path" && change.path === "plot.type") syncMarkerSizeDisplay();
  }
});

applyStateToForm();
setColumns([]);
syncSaveFormatOptions();
initBridge();
onPythonReady(() => initDefaultCode(getDefaultCustomCode()));
