// 軸・目盛区分: X 軸の日時の表示書式（プリセット / 任意）。値は state の axes.x.dateFormat（文字列、"" = 自動）に書き込む。
// 表示・非表示（#xDateFormatGroup）は、X に日時の列を使っているかで series.js の syncVisibility が決める。
import { getSettings, setPath } from "../state.js";

const byId = (id) => document.getElementById(id);
const PRESETS = ["", "%Y-%m-%d", "%Y/%m/%d", "%m/%d", "%m月%d日", "%H:%M", "%m/%d %H:%M"];
const PATH = "axes.x.dateFormat";

let customMode = false;

const paint = () => {
  const select = byId("xDateFormat");
  const custom = byId("xDateFormatCustom");
  const row = byId("xDateFormatRow");
  if (select) select.value = customMode ? "custom" : getSettings().axes.x.dateFormat || "";
  if (custom) custom.hidden = !customMode;
  if (row) row.classList.toggle("has-custom", customMode);
};

// state → 画面（プリセットに無い書式は「任意」で表示する）
export const syncDateFormatView = () => {
  const value = getSettings().axes.x.dateFormat || "";
  customMode = !PRESETS.includes(value);
  const custom = byId("xDateFormatCustom");
  if (custom && customMode) custom.value = value;
  paint();
};

export const bindDateFormat = () => {
  const select = byId("xDateFormat");
  const custom = byId("xDateFormatCustom");
  if (select) {
    select.addEventListener("change", () => {
      if (select.value === "custom") {
        customMode = true;
        if (custom) custom.value = getSettings().axes.x.dateFormat || "";
        paint();
        if (custom) custom.focus();
      } else {
        customMode = false;
        setPath(PATH, select.value);
        paint();
      }
    });
  }
  if (custom) {
    // input だけを購読する（プリセットに切り替えた値を、古い入力で上書きしないため）
    custom.addEventListener("input", () => {
      if (customMode) setPath(PATH, custom.value);
    });
  }
  syncDateFormatView();
};
