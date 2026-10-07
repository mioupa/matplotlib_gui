// 保存形式セレクトの選択肢（背景透過時は png / svg のみ）。
const saveFormatSelect = document.getElementById("saveFormat");
const saveTransparentInput = document.getElementById("saveTransparent");

const SAVE_FORMATS_ALL = ["png", "jpg", "svg", "pdf"];
const SAVE_FORMATS_TRANSPARENT = ["png", "svg"];
export const syncSaveFormatOptions = () => {
  if (!saveFormatSelect) return;
  const allowTransparentOnly = !!(saveTransparentInput && saveTransparentInput.checked);
  const formats = allowTransparentOnly ? SAVE_FORMATS_TRANSPARENT : SAVE_FORMATS_ALL;
  const currentValue = (saveFormatSelect.value || "").toLowerCase();

  saveFormatSelect.innerHTML = "";
  for (const fmt of formats) {
    const opt = document.createElement("option");
    opt.value = fmt;
    opt.textContent = fmt;
    saveFormatSelect.appendChild(opt);
  }

  if (formats.includes(currentValue)) {
    saveFormatSelect.value = currentValue;
  } else {
    saveFormatSelect.value = formats[0];
  }
};

export const bindSaveFormatEvents = () => {
  if (saveTransparentInput) {
    saveTransparentInput.addEventListener("change", () => {
      syncSaveFormatOptions();
    });
  }
};
