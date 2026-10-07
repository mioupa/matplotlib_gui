// 保存形式セレクトの選択肢（背景透過時は png / svg のみ）。選択肢が変わったら state の保存形式も追従させる。
import { getSettings, setPath } from "../state.js";

const SAVE_FORMATS_ALL = ["png", "jpg", "svg", "pdf"];
const SAVE_FORMATS_TRANSPARENT = ["png", "svg"];

// 実効の保存形式（セレクトの値）に合わせて、svg / pdf だけの項目を出し分ける
export const syncSaveFormatVisibility = () => {
  const format = document.getElementById("saveFormat")?.value;
  const svg = document.getElementById("svgTextGroup");
  const pdf = document.getElementById("pdfHelp");
  if (svg) svg.hidden = format !== "svg";
  if (pdf) pdf.hidden = format !== "pdf";
};

export const syncSaveFormatOptions = () => {
  const select = document.getElementById("saveFormat");
  if (!select) return;
  const formats = getSettings().save.transparent ? SAVE_FORMATS_TRANSPARENT : SAVE_FORMATS_ALL;
  const current = String(getSettings().save.format || select.value || "").toLowerCase();

  select.innerHTML = "";
  for (const fmt of formats) {
    const opt = document.createElement("option");
    opt.value = fmt;
    opt.textContent = fmt;
    select.appendChild(opt);
  }
  select.value = formats.includes(current) ? current : formats[0];
  setPath("save.format", select.value);
  syncSaveFormatVisibility();
};

export const bindSaveFormatEvents = () => {
  document.getElementById("saveFormat")?.addEventListener("change", syncSaveFormatVisibility);
  const transparent = document.getElementById("saveTransparent");
  if (transparent) {
    // forms.js の入力ハンドラ（state 更新）より後に走るよう、change を購読する
    transparent.addEventListener("change", syncSaveFormatOptions);
  }
};
