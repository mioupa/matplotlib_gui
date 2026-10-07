// 選択中のファイル名と検出した文字コードの表示（#fileNameLabel / #encodingLabel）。
const ENCODING_NAMES = {
  "utf-8": "UTF-8",
  "utf-8-sig": "UTF-8（BOM付き）",
  cp932: "Shift_JIS（CP932）",
  "euc-jp": "EUC-JP",
};

export const encodingDisplayName = (encoding) => (encoding === null || encoding === undefined ? "Excel" : ENCODING_NAMES[encoding] || String(encoding));

export const showFileName = (name) => {
  const label = document.getElementById("fileNameLabel");
  if (label) label.textContent = name ? `選択中: ${name}` : "";
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
