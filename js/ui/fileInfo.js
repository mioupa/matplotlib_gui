// 選択中のファイル名と検出した文字コードの表示（#fileNameLabel / #encodingLabel）。
// #fileNameLabel はファイル選択ボックス（.file-picker）内の表示。input は選択のたびに空に戻すので、
// ブラウザ標準の「選択されていません」には頼らず、JS がファイル名（未選択時は既定文言）を出す。
const ENCODING_NAMES = {
  "utf-8": "UTF-8",
  "utf-8-sig": "UTF-8（BOM付き）",
  cp932: "Shift_JIS（CP932）",
  "euc-jp": "EUC-JP",
};

export const encodingDisplayName = (encoding) => (encoding === null || encoding === undefined ? "Excel" : ENCODING_NAMES[encoding] || String(encoding));

const NO_FILE_TEXT = "選択されていません";

export const showFileName = (name) => {
  const label = document.getElementById("fileNameLabel");
  if (label) {
    label.textContent = name || NO_FILE_TEXT;
    label.title = name || "";
    label.dataset.selected = name ? "true" : "false";
  }
  showEncoding(undefined);
};

// encoding: undefined = 非表示（未読込）、null = xlsx
export const showEncoding = (encoding) => {
  const label = document.getElementById("encodingLabel");
  if (!label) return;
  if (encoding === undefined) {
    label.textContent = "";
    label.dataset.encoding = "";
    return;
  }
  const name = encodingDisplayName(encoding);
  label.textContent = encoding === null ? `形式: ${name}` : `文字コード: ${name}`;
  label.dataset.encoding = encoding === null ? "excel" : String(encoding);
};
