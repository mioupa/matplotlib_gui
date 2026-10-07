// 系列カード（追加・削除・列セレクト・種別/第2軸に応じた表示切替）。
import { scheduleRender } from "../bridge.js";
import { SERIES_COLORS, bindSeriesColorControls } from "./colorPicker.js";

const seriesList = document.getElementById("seriesList");
const addSeriesBtn = document.getElementById("addSeriesBtn");
const plotTypeSelect = document.getElementById("plotType");
const globalXGroup = document.getElementById("globalXGroup");
const xColumnSelect = document.getElementById("xColumn");
const y2LabelGroup = document.getElementById("y2LabelGroup");
const y2AxisSettingsGroup = document.getElementById("y2AxisSettingsGroup");
let lastPlotType = plotTypeSelect ? plotTypeSelect.value : "line";

const getColumnOptions = (includeIndex = false) => {
  const xColumn = document.getElementById("xColumn");
  if (!xColumn) return [];
  const options = [];
  for (const opt of xColumn.options) {
    if (!includeIndex && !opt.value) continue;
    options.push({ value: opt.value, label: opt.textContent || opt.value });
  }
  return options;
};

const fillSeriesYSelect = (selectEl, selectedValue = "") => {
  if (!selectEl) return;
  const columns = getColumnOptions(false);
  selectEl.innerHTML = "";

  const autoOption = document.createElement("option");
  autoOption.value = "";
  autoOption.textContent = "(自動)";
  selectEl.appendChild(autoOption);

  for (const col of columns) {
    const opt = document.createElement("option");
    opt.value = col.value;
    opt.textContent = col.label;
    selectEl.appendChild(opt);
  }

  if (selectedValue && Array.from(selectEl.options).some((opt) => opt.value === selectedValue)) {
    selectEl.value = selectedValue;
  }
};

const fillSeriesXSelect = (selectEl, selectedValue = "") => {
  if (!selectEl) return;
  const columns = getColumnOptions(true);
  selectEl.innerHTML = "";
  for (const col of columns) {
    const opt = document.createElement("option");
    opt.value = col.value;
    opt.textContent = col.label;
    selectEl.appendChild(opt);
  }
  if (Array.from(selectEl.options).some((opt) => opt.value === selectedValue)) {
    selectEl.value = selectedValue;
  } else {
    selectEl.value = "";
  }
};

export const syncPlotTypeUI = () => {
  const type = plotTypeSelect ? plotTypeSelect.value : "line";
  const usePerSeriesX = type === "line" || type === "scatter";
  if (globalXGroup) {
    globalXGroup.style.display = usePerSeriesX ? "none" : "";
  }
  if (!seriesList) return;
  const xGroups = seriesList.querySelectorAll(".series-x-wrap");
  for (const group of xGroups) {
    group.style.display = usePerSeriesX ? "block" : "none";
  }
};

export const syncMarkerSizeForPlotType = () => {
  if (!seriesList || !plotTypeSelect) return;
  const currentType = plotTypeSelect.value;
  const markerInputs = seriesList.querySelectorAll(".series-marker-size");
  if (currentType === "scatter") {
    for (const input of markerInputs) {
      const current = Number(input.value);
      if (!Number.isFinite(current) || current <= 0) {
        input.value = "24";
      }
    }
  } else if (currentType === "line" && lastPlotType === "scatter") {
    for (const input of markerInputs) {
      const current = Number(input.value);
      if (Number.isFinite(current) && current === 24) {
        input.value = "0";
      }
    }
  }
  lastPlotType = currentType;
};

export const syncY2LabelUI = () => {
  if (!seriesList) return;
  const hasSecondary = !!seriesList.querySelector(".series-use-y2:checked");
  if (y2LabelGroup) {
    y2LabelGroup.style.display = hasSecondary ? "" : "none";
  }
  if (y2AxisSettingsGroup) {
    y2AxisSettingsGroup.style.display = hasSecondary ? "" : "none";
  }
};

const renumberSeries = () => {
  if (!seriesList) return;
  const items = Array.from(seriesList.querySelectorAll(".series-item"));
  items.forEach((item, idx) => {
    const title = item.querySelector(".series-item-title");
    if (title) title.textContent = `系列 ${idx + 1}`;
  });
  const disableRemove = items.length <= 1;
  items.forEach((item) => {
    const removeBtn = item.querySelector(".remove-series");
    if (removeBtn) {
      removeBtn.disabled = disableRemove;
      removeBtn.style.opacity = disableRemove ? "0.5" : "1";
      removeBtn.style.cursor = disableRemove ? "not-allowed" : "pointer";
    }
  });
};

const addSeriesItem = (preset = {}) => {
  if (!seriesList) return;
  const item = document.createElement("div");
  item.className = "series-item";
  const color = preset.color || SERIES_COLORS[seriesList.children.length % SERIES_COLORS.length];
  const defaultMarkerSize = Object.prototype.hasOwnProperty.call(preset, "markerSize")
    ? preset.markerSize
    : plotTypeSelect && plotTypeSelect.value === "line"
      ? 0
      : 24;
  item.innerHTML = `
    <div class="series-item-header">
      <div class="series-item-title">系列</div>
      <button type="button" class="small-btn ghost-btn remove-series">削除</button>
    </div>
    <div class="row group">
      <div class="series-x-wrap">
        <label>X列</label>
        <select class="series-x"></select>
      </div>
      <div>
        <label>Y列</label>
        <select class="series-y"></select>
      </div>
    </div>
    <div class="row group">
      <div>
        <label>色</label>
        <div class="series-color-picker">
          <button type="button" class="series-color-trigger">
            <span class="series-color-swatch-inline"></span>
            <span>色を選択</span>
          </button>
          <div class="series-color-panel hidden">
            <div class="series-color-grid"></div>
            <button type="button" class="small-btn ghost-btn series-color-custom-toggle">カスタム</button>
            <input class="series-color series-color-custom hidden" type="color" value="${color}" />
          </div>
        </div>
        <div class="color-value series-color-value">${color}</div>
      </div>
      <div>
        <label>線幅</label>
        <input class="series-line-width" type="number" step="0.1" value="${preset.lineWidth || 2.0}" />
      </div>
    </div>
    <div class="row group">
      <div>
        <label>線種</label>
        <select class="series-line-style">
          <option value="solid">solid</option>
          <option value="dashed">dashed</option>
          <option value="dashdot">dashdot</option>
          <option value="dotted">dotted</option>
        </select>
      </div>
      <div>
        <label>点サイズ</label>
        <input class="series-marker-size" type="number" step="1" value="${defaultMarkerSize}" />
      </div>
    </div>
    <div class="group">
      <label>凡例名（任意）</label>
      <input class="series-legend-name" type="text" value="${preset.legendName || ""}" placeholder="自動" />
    </div>
    <div class="group">
      <label class="inline check-label">
        <input class="series-use-y2" type="checkbox" ${preset.useSecondaryAxis ? "checked" : ""} />
        <span>第2軸を使用</span>
      </label>
    </div>
  `;

  seriesList.appendChild(item);
  const ySelect = item.querySelector(".series-y");
  fillSeriesYSelect(ySelect, preset.yRequest || "");
  const xSelect = item.querySelector(".series-x");
  fillSeriesXSelect(xSelect, preset.xRequest || (xColumnSelect ? xColumnSelect.value : ""));
  bindSeriesColorControls(item);

  const lineStyleSelect = item.querySelector(".series-line-style");
  if (lineStyleSelect) {
    lineStyleSelect.value = preset.lineStyle || "solid";
  }

  const removeBtn = item.querySelector(".remove-series");
  if (removeBtn) {
    removeBtn.addEventListener("click", () => {
      if (seriesList.children.length <= 1) return;
      item.remove();
      renumberSeries();
      syncY2LabelUI();
      scheduleRender();
    });
  }

  syncPlotTypeUI();
  syncY2LabelUI();
  renumberSeries();
};

window.refreshSeriesColumnOptions = () => {
  if (!seriesList) return;
  const ySelects = seriesList.querySelectorAll(".series-y");
  for (const selectEl of ySelects) {
    fillSeriesYSelect(selectEl, selectEl.value);
  }
  const xSelects = seriesList.querySelectorAll(".series-x");
  for (const selectEl of xSelects) {
    fillSeriesXSelect(selectEl, selectEl.value);
  }
};

window.ensureSeriesItems = () => {
  if (!seriesList) return;
  if (seriesList.children.length === 0) {
    addSeriesItem();
  } else {
    renumberSeries();
  }
  syncPlotTypeUI();
  syncY2LabelUI();
};

export const bindSeriesEvents = () => {
  if (addSeriesBtn) {
    addSeriesBtn.addEventListener("click", () => {
      addSeriesItem();
      scheduleRender();
    });
  }
  if (plotTypeSelect) {
    plotTypeSelect.addEventListener("change", () => {
      syncPlotTypeUI();
      syncMarkerSizeForPlotType();
      scheduleRender();
    });
  }
  if (seriesList) {
    const onSeriesInput = (event) => {
      const target = event.target;
      if (!target) return;
      if (target.matches("input, select")) {
        if (target.matches(".series-use-y2")) {
          syncY2LabelUI();
        }
        scheduleRender();
      }
    };
    seriesList.addEventListener("input", onSeriesInput);
    seriesList.addEventListener("change", onSeriesInput);
  }
};
