// データ読み込み区分: シートの選択（#sheetGroup / #sheetSelect。.xlsx のときだけ表示）。
// 選んだシートは設定の load.files に書く（読み直しは bridge.js が load.files の変更を購読して行う）。
import { setFileSheet } from "../state.js";

const SOURCE_ID = "d1";

// sheets: シート名の配列（xlsx 以外は空）、sheet: 読んだシート名
export const showSheets = (sheets, sheet) => {
  const group = document.getElementById("sheetGroup");
  const select = document.getElementById("sheetSelect");
  if (!group || !select) return;
  const names = Array.isArray(sheets) ? sheets : [];
  group.hidden = names.length === 0;
  select.replaceChildren(
    ...names.map((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      return option;
    }),
  );
  if (names.length > 0) select.value = names.includes(sheet) ? sheet : names[0];
};

export const bindLoadSection = () => {
  const select = document.getElementById("sheetSelect");
  if (select) select.addEventListener("change", () => setFileSheet(SOURCE_ID, select.value));
};
