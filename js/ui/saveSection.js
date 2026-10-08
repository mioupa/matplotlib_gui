// 保存セクション: DPI（プリセット / 任意）。値は state の save.dpi（数値）に書き込む。
import { getSettings, setPath } from "../state.js";
import { readNumber } from "./forms.js";

const byId = (id) => document.getElementById(id);
const PRESET_DPI = [72, 150, 300, 600];

let customMode = false;

// 任意の入力欄の表示と、セレクトの選択を、モードに合わせる
const paint = () => {
  const select = byId("saveDpi");
  const custom = byId("saveDpiCustom");
  const row = byId("saveDpiRow");
  if (select) select.value = customMode ? "custom" : String(getSettings().save.dpi);
  if (custom) custom.hidden = !customMode;
  if (row) row.classList.toggle("has-custom", customMode);
};

// state → 画面（初期表示。プリセットに無い値は「任意」で表示する）
export const syncSaveDpiView = () => {
  const dpi = getSettings().save.dpi;
  customMode = !PRESET_DPI.includes(dpi);
  const custom = byId("saveDpiCustom");
  if (custom && customMode) custom.value = dpi === null || dpi === undefined ? "" : String(dpi);
  paint();
};

export const bindSaveSection = () => {
  const select = byId("saveDpi");
  const custom = byId("saveDpiCustom");
  if (select) {
    select.addEventListener("change", () => {
      if (select.value === "custom") {
        customMode = true;
        if (custom) custom.value = String(getSettings().save.dpi ?? "");
        paint();
        if (custom) custom.focus();
      } else {
        customMode = false;
        setPath("save.dpi", Number(select.value));
        paint();
      }
    });
  }
  if (custom) {
    // input だけを購読する（blur 後の change で、プリセットに切り替えた値を古い入力で上書きしないため）
    custom.addEventListener("input", () => {
      if (customMode) setPath("save.dpi", readNumber(custom));
    });
  }
  syncSaveDpiView();
};
