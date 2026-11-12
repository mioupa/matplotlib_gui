// 系列ごとの色選択UI（オーバーレイパネル）。選んだ色は onChange(color) で呼び出し側（state）へ渡す。
import { getPalette } from "../palettes.js";
import { getSettings } from "../state.js";

const normalizeColor = (value) => String(value || "").trim().toUpperCase();

// 色の選択UIのマークアップ（系列カード以外の注釈・近似曲線カードでも使う。bindSeriesColorControls で結ぶ）。idBase は trigger の id に使う
export const colorPickerHtml = (idBase, color, extraClass = "") => `
  <div class="series-color-picker ${extraClass}">
    <button type="button" id="${idBase}-trigger" class="series-color-trigger">
      <span class="series-color-swatch-inline"></span>
      <span>色を選択</span>
    </button>
    <div class="series-color-panel hidden">
      <div class="series-color-grid"></div>
      <button type="button" class="small-btn ghost-btn series-color-custom-toggle">カスタム</button>
      <input class="series-color series-color-custom hidden" type="color" value="${String(color).replace(/"/g, "")}" aria-label="カスタム色" />
    </div>
  </div>
  <div class="color-value series-color-value">${String(color).replace(/[<>&"]/g, "")}</div>`;

const closeAllColorPanels = (exceptPanel = null) => {
  for (const p of document.querySelectorAll(".series-color-panel")) {
    if (exceptPanel && p === exceptPanel) continue;
    p.classList.add("hidden");
  }
};

export const bindSeriesColorControls = (item, onChange) => {
  const trigger = item.querySelector(".series-color-trigger");
  const panel = item.querySelector(".series-color-panel");
  const grid = item.querySelector(".series-color-grid");
  const customToggle = item.querySelector(".series-color-custom-toggle");
  const colorInput = item.querySelector(".series-color");
  const swatch = item.querySelector(".series-color-swatch-inline");
  const valueLabel = item.querySelector(".series-color-value");
  if (!trigger || !panel || !grid || !customToggle || !colorInput || !swatch || !valueLabel) return;

  const syncSeriesColorView = () => {
    const current = normalizeColor(colorInput.value);
    swatch.style.backgroundColor = current || "#000000";
    valueLabel.textContent = current || "#000000";

    const isPaletteColor = getPalette(getSettings().plot.palette).some((c) => normalizeColor(c) === current);
    colorInput.classList.toggle("hidden", isPaletteColor);
    for (const chip of grid.querySelectorAll(".series-color-chip")) {
      chip.classList.toggle("active", normalizeColor(chip.dataset.color) === current);
    }
  };

  grid.innerHTML = "";
  for (const color of getPalette(getSettings().plot.palette)) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "series-color-chip";
    chip.dataset.color = color;
    chip.style.backgroundColor = color;
    chip.title = color;
    chip.addEventListener("click", () => {
      colorInput.value = color;
      syncSeriesColorView();
      panel.classList.add("hidden");
      onChange(color);
    });
    grid.appendChild(chip);
  }

  trigger.addEventListener("click", () => {
    const willOpen = panel.classList.contains("hidden");
    closeAllColorPanels(panel);
    panel.classList.toggle("hidden", !willOpen);
  });

  customToggle.addEventListener("click", () => {
    colorInput.classList.remove("hidden");
    if (typeof colorInput.showPicker === "function") {
      colorInput.showPicker();
    } else {
      colorInput.click();
    }
  });

  colorInput.addEventListener("input", () => {
    syncSeriesColorView();
    onChange(colorInput.value);
  });

  syncSeriesColorView();
};

// パネル外クリックでオーバーレイを閉じる
export const bindColorPanelOutsideClick = () => {
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (target && target.closest(".series-color-picker")) return;
    for (const panel of document.querySelectorAll(".series-color-panel")) {
      panel.classList.add("hidden");
    }
  });
};
