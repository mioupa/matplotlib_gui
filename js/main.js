// エントリ。DOM 構築後（module は defer）に UI を設定オブジェクトへ結び付ける。
//   画面の入力 → state.js（設定オブジェクト）→ bridge.js が JSON で Python を呼ぶ → 結果を ui/* が描く
import { subscribe } from "./state.js";
import { initBridge, saveNow, selectFile } from "./bridge.js";
import { bindColorPanelOutsideClick } from "./ui/colorPicker.js";
import { bindCodeTab } from "./ui/codeTab.js";
import { applyStateToForm, bindForms } from "./ui/forms.js";
import { bindSaveFormatEvents, syncSaveFormatOptions } from "./ui/saveFormat.js";
import { bindSaveSection } from "./ui/saveSection.js";
import { bindClipboard } from "./ui/clipboard.js";
import { bindSeriesEvents, renderSeriesList, setColumns, syncMarkerSizeDisplay, syncVisibility } from "./ui/series.js";
import { bindStyleSection } from "./ui/styleSection.js";
import { initPanelSections } from "./ui/panelSections.js";
import { bindTabs } from "./ui/tabs.js";

const fileInput = document.getElementById("fileInput");
if (fileInput) {
  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    selectFile(file); // File は bridge.js が保持する（再読込用）
    fileInput.value = ""; // 空に戻すので、同じファイルをもう一度選んでも change が起きて再読込される
  });
}
const savePlotBtn = document.getElementById("savePlotBtn");
if (savePlotBtn) savePlotBtn.addEventListener("click", () => saveNow());

initPanelSections();
bindTabs();
bindForms();
bindSeriesEvents();
bindSaveFormatEvents();
bindSaveSection();
bindClipboard();
bindCodeTab();
bindColorPanelOutsideClick();
bindStyleSection();

// state の変更に応じた画面の更新（再描画・読込の予約は bridge.js が購読して行う）
subscribe((_settings, change) => {
  if (change.kind === "series-list") {
    renderSeriesList();
  } else if (change.kind === "path" && change.path === "plot.palette") {
    renderSeriesList(); // 色の選択肢と各系列の色を、新しいパレットで描き直す
  } else {
    syncVisibility();
    if (change.kind === "path" && change.path === "plot.type") syncMarkerSizeDisplay();
  }
});

applyStateToForm();
setColumns([]);
syncSaveFormatOptions();
initBridge();
