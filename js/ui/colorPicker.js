// 系列ごとの色選択UI（オーバーレイパネル）。
import { scheduleRender } from "../bridge.js";

const seriesList = document.getElementById("seriesList");

export const SERIES_COLORS = [
  "#FF4B00",
  "#005AFF",
  "#03AF7A",
  "#4DC4FF",
  "#F6AA00",
  "#FFF100",
  "#990099",
  "#84919E",
  "#000000",
  "#804000",
  "#FF8082",
];

export const bindSeriesColorControls = (item) => {
  const trigger = item.querySelector(".series-color-trigger");
  const panel = item.querySelector(".series-color-panel");
  const grid = item.querySelector(".series-color-grid");
  const customToggle = item.querySelector(".series-color-custom-toggle");
  const colorInput = item.querySelector(".series-color");
  const swatch = item.querySelector(".series-color-swatch-inline");
  const valueLabel = item.querySelector(".series-color-value");
  if (!trigger || !panel || !grid || !customToggle || !colorInput || !swatch || !valueLabel) return;

  const closeAllColorPanels = (exceptPanel = null) => {
    if (!seriesList) return;
    const panels = seriesList.querySelectorAll(".series-color-panel");
    for (const p of panels) {
      if (exceptPanel && p === exceptPanel) continue;
      p.classList.add("hidden");
    }
  };

  const normalizeColor = (value) => String(value || "").trim().toUpperCase();

  const syncSeriesColorView = () => {
    const current = normalizeColor(colorInput.value);
    swatch.style.backgroundColor = current || "#000000";
    valueLabel.textContent = current || "#000000";

    const isPaletteColor = SERIES_COLORS.some((c) => normalizeColor(c) === current);
    colorInput.classList.toggle("hidden", isPaletteColor);
    const chips = grid.querySelectorAll(".series-color-chip");
    for (const chip of chips) {
      const chipColor = normalizeColor(chip.dataset.color);
      chip.classList.toggle("active", chipColor === current);
    }
  };

  grid.innerHTML = "";
  for (const color of SERIES_COLORS) {
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
      scheduleRender();
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
  });

  syncSeriesColorView();
};

// パネル外クリックでオーバーレイを閉じる
export const bindColorPanelOutsideClick = () => {
  document.addEventListener("click", (event) => {
    if (!seriesList) return;
    const target = event.target;
    if (target && target.closest(".series-color-picker")) return;
    const panels = seriesList.querySelectorAll(".series-color-panel");
    for (const panel of panels) {
      panel.classList.add("hidden");
    }
  });
};
