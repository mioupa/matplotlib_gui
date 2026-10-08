// エントリ。DOM 構築後（module は defer）に UI を設定オブジェクトへ結び付ける。
//   画面の入力 → state.js（設定オブジェクト）→ bridge.js が JSON で Python を呼ぶ → 結果を ui/* が描く
import { subscribe } from "./state.js";
import { initBridge, saveNow, selectFiles } from "./bridge.js";
import { bindColorPanelOutsideClick } from "./ui/colorPicker.js";
import { bindCodeTab } from "./ui/codeTab.js";
import { applyStateToForm, bindForms } from "./ui/forms.js";
import { bindSaveFormatEvents, syncSaveFormatOptions } from "./ui/saveFormat.js";
import { bindDropPaste } from "./ui/dropPaste.js";
import { bindLoadSection } from "./ui/loadSection.js";
import { bindSaveSection } from "./ui/saveSection.js";
import { bindDateFormat } from "./ui/dateFormat.js";
import { bindClipboard } from "./ui/clipboard.js";
import { bindSeriesEvents, refreshSources, renderSeriesList, syncMarkerSizeDisplay, syncVisibility } from "./ui/series.js";
import { bindStyleSection } from "./ui/styleSection.js";
import { initPanelSections } from "./ui/panelSections.js";
import { bindTabs } from "./ui/tabs.js";

// 「ファイルを選択」は選んだファイルですべてを置き換え、「+ ファイルを追加」は追加する（どちらも複数選択できる）
const bindFileInput = (inputId, mode) => {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.addEventListener("change", () => {
    selectFiles(Array.from(input.files || []), { mode }); // File は bridge.js が保持する（再読込用）
    input.value = ""; // 空に戻すので、同じファイルをもう一度選んでも change が起きて再読込される
  });
};
bindFileInput("fileInput", "replace");
bindFileInput("addFileInput", "add");
const addFileBtn = document.getElementById("addFileBtn");
if (addFileBtn) addFileBtn.addEventListener("click", () => document.getElementById("addFileInput").click());
const savePlotBtn = document.getElementById("savePlotBtn");
if (savePlotBtn) savePlotBtn.addEventListener("click", () => saveNow());

initPanelSections();
bindTabs();
bindForms();
bindSeriesEvents();
bindSaveFormatEvents();
bindLoadSection();
bindDropPaste();
bindSaveSection();
bindDateFormat();
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
refreshSources();
syncSaveFormatOptions();
initBridge();
