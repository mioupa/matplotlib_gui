// 系列カード（追加・削除・列セレクト・種別/第2軸に応じた表示切替）。カードは state の系列リストから描く。
import { addSeries, getSettings, hasSecondaryAxis, removeSeries, updateSeries, setPath } from "../state.js";
import { bindSeriesColorControls } from "./colorPicker.js";
import { readNumber } from "./forms.js";

// データ元（ファイル id）ごとの列の選択肢: [{value: "__idx__0", label: "時間 [0]", kind: "number"}]（読込のたびに更新。kind: datetime / number / text）
const columnsById = new Map();

const loadedFiles = () => getSettings().load.files;
const sourceIdOf = (series) => series.source || (loadedFiles()[0] ? loadedFiles()[0].id : "d1"); // "" は先頭のファイル
const columnsOf = (series) => columnsById.get(sourceIdOf(series)) || [];
const hasManySources = () => loadedFiles().length >= 2;

const isDatetimeColumn = (columns, value) => !!value && columns.some((c) => c.value === value && c.kind === "datetime");

// X に日時の列を使っているか（line / scatter はどれかの系列の X（その系列のデータ元の列）、bar は X列（系列1のデータ元））
export const usesDatetimeX = () => {
  const { plot, series } = getSettings();
  if (plot.type === "bar") return series.length > 0 && isDatetimeColumn(columnsOf(series[0]), plot.xColumn);
  return series.some((s) => isDatetimeColumn(columnsOf(s), s.x));
};

const esc = (text) =>
  String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const defaultMarkerSize = (plotType) => (plotType === "line" ? 0 : 24);
const displayMarkerSize = (series, plotType) => (series.markerSize === null ? defaultMarkerSize(plotType) : series.markerSize);

const fillSelect = (selectEl, options, selected) => {
  selectEl.innerHTML = "";
  for (const opt of options) {
    const o = document.createElement("option");
    o.value = opt.value;
    o.textContent = opt.label;
    selectEl.appendChild(o);
  }
  selectEl.value = options.some((o) => o.value === selected) ? selected : "";
};

const xOptions = (columns) => [{ value: "", label: "(index)" }, ...columns];
const yOptions = (columns) => [{ value: "", label: "(自動)" }, ...columns];
const sourceOptions = () => loadedFiles().map((f, i) => ({ value: f.id, label: `データ${i + 1}: ${f.name}` }));

const cardHtml = (series, plotType) => {
  const id = (name) => `series-${series.id}-${name}`;
  return `
    <div class="series-item-header">
      <div class="series-item-title">系列</div>
      <button type="button" id="${id("remove")}" class="small-btn ghost-btn remove-series">削除</button>
    </div>
    <div class="group series-source-wrap">
      <label for="${id("source")}">データ元</label>
      <select id="${id("source")}" class="series-source"></select>
    </div>
    <div class="row group">
      <div class="series-x-wrap">
        <label for="${id("x")}">X列</label>
        <select id="${id("x")}" class="series-x"></select>
      </div>
      <div>
        <label for="${id("y")}">Y列</label>
        <select id="${id("y")}" class="series-y"></select>
      </div>
    </div>
    <div class="row group">
      <div>
        <label for="${id("color-trigger")}">色</label>
        <div class="series-color-picker">
          <button type="button" id="${id("color-trigger")}" class="series-color-trigger">
            <span class="series-color-swatch-inline"></span>
            <span>色を選択</span>
          </button>
          <div class="series-color-panel hidden">
            <div class="series-color-grid"></div>
            <button type="button" class="small-btn ghost-btn series-color-custom-toggle">カスタム</button>
            <input class="series-color series-color-custom hidden" type="color" value="${esc(series.color)}" aria-label="カスタム色" />
          </div>
        </div>
        <div class="color-value series-color-value">${esc(series.color)}</div>
      </div>
      <div>
        <label for="${id("line-width")}">線幅</label>
        <input id="${id("line-width")}" class="series-line-width" type="number" step="0.1" value="${esc(series.lineWidth ?? "")}" />
      </div>
    </div>
    <div class="row group">
      <div>
        <label for="${id("line-style")}">線種</label>
        <select id="${id("line-style")}" class="series-line-style">
          <option value="solid">solid</option>
          <option value="dashed">dashed</option>
          <option value="dashdot">dashdot</option>
          <option value="dotted">dotted</option>
        </select>
      </div>
      <div>
        <label for="${id("marker-size")}">点サイズ</label>
        <input id="${id("marker-size")}" class="series-marker-size" type="number" step="1" value="${esc(displayMarkerSize(series, plotType))}" />
      </div>
    </div>
    <div class="group">
      <label for="${id("legend-name")}">凡例名（任意）</label>
      <input id="${id("legend-name")}" class="series-legend-name" type="text" value="${esc(series.label)}" placeholder="自動" />
    </div>
    <div class="group">
      <label class="inline check-label">
        <input id="${id("use-y2")}" class="series-use-y2" type="checkbox" ${series.secondaryAxis ? "checked" : ""} />
        <span>第2軸を使用</span>
      </label>
    </div>
  `;
};

const buildCard = (series, plotType) => {
  const item = document.createElement("div");
  item.className = "series-item";
  item.dataset.seriesId = series.id;
  item.innerHTML = cardHtml(series, plotType);
  const columns = columnsOf(series);
  fillSelect(item.querySelector(".series-x"), xOptions(columns), series.x);
  fillSelect(item.querySelector(".series-y"), yOptions(columns), series.y);
  fillSelect(item.querySelector(".series-source"), sourceOptions(), sourceIdOf(series));
  item.querySelector(".series-source-wrap").hidden = !hasManySources();
  item.querySelector(".series-line-style").value = series.lineStyle;
  bindSeriesColorControls(item, (color) => updateSeries(series.id, { color }));
  item.querySelector(".remove-series").addEventListener("click", () => removeSeries(series.id));
  return item;
};

export const syncVisibility = () => {
  const settings = getSettings();
  const usePerSeriesX = settings.plot.type !== "bar";
  const globalX = document.getElementById("globalXGroup");
  if (globalX) globalX.style.display = usePerSeriesX ? "none" : "";
  for (const group of document.querySelectorAll("#seriesList .series-x-wrap")) {
    group.style.display = usePerSeriesX ? "block" : "none";
  }
  for (const wrap of document.querySelectorAll("#seriesList .series-source-wrap")) wrap.hidden = !hasManySources();
  const dateGroup = document.getElementById("xDateFormatGroup");
  if (dateGroup) dateGroup.hidden = !usesDatetimeX();
  const hasY2 = hasSecondaryAxis();
  for (const id of ["y2LabelGroup", "y2AxisSettingsGroup"]) {
    const el = document.getElementById(id);
    if (el) el.style.display = hasY2 ? "" : "none";
  }
};

// 点サイズが自動（null）の系列は、プロット種別に応じた値を表示する（ユーザーが入力した値は変えない）
export const syncMarkerSizeDisplay = () => {
  const { plot, series } = getSettings();
  for (const item of document.querySelectorAll("#seriesList .series-item")) {
    const s = series.find((x) => x.id === item.dataset.seriesId);
    const input = item.querySelector(".series-marker-size");
    if (s && input && s.markerSize === null && document.activeElement !== input) {
      input.value = String(defaultMarkerSize(plot.type));
    }
  }
};

// カードを描いたときの、データ元と列の選択肢の状態（読込が終わったとき、変わっていなければ描き直さない）
let renderedStructure = "";
const structureOf = () => {
  const { series, plot } = getSettings();
  return JSON.stringify([
    loadedFiles().map((f) => [f.id, f.name]),
    series.map((s) => [s.id, sourceIdOf(s), columnsOf(s)]),
    plot.type,
    plot.xColumn,
  ]);
};

// 表示中のカードの選択が、設定と同じか（違えば描き直す）
const cardsMatchSettings = () => {
  const list = document.getElementById("seriesList");
  if (!list) return false;
  const { series } = getSettings();
  const items = list.querySelectorAll(".series-item");
  if (items.length !== series.length) return false;
  return series.every((s, i) => {
    const item = items[i];
    return (
      item.dataset.seriesId === s.id &&
      item.querySelector(".series-x")?.value === s.x &&
      item.querySelector(".series-y")?.value === s.y &&
      item.querySelector(".series-source")?.value === sourceIdOf(s)
    );
  });
};

export const renderSeriesList = () => {
  const list = document.getElementById("seriesList");
  if (!list) return;
  renderedStructure = structureOf();
  const { series, plot } = getSettings();
  list.replaceChildren(...series.map((s) => buildCard(s, plot.type)));
  const items = list.querySelectorAll(".series-item");
  items.forEach((item, idx) => {
    item.querySelector(".series-item-title").textContent = `系列 ${idx + 1}`;
    const removeBtn = item.querySelector(".remove-series");
    const disable = items.length <= 1;
    removeBtn.disabled = disable;
    removeBtn.setAttribute("aria-label", `系列 ${idx + 1} を削除`);
    removeBtn.style.opacity = disable ? "0.5" : "1";
    removeBtn.style.cursor = disable ? "not-allowed" : "pointer";
  });
  syncVisibility();
};

const refreshXColumnSelect = () => {
  const select = document.getElementById("xColumn");
  const { series, plot } = getSettings();
  if (select) fillSelect(select, xOptions(series[0] ? columnsOf(series[0]) : []), plot.xColumn); // 棒グラフの X は系列1のデータ元の列
};

// ファイルの追加・削除などで、データ元の選択肢と各系列の列の選択肢を描き直す
export const refreshSources = () => {
  refreshXColumnSelect();
  // データ元と列の選択肢が変わっていなければ、カードは描き直さない（入力中の欄や開いている選択肢を保つ）
  if (renderedStructure === structureOf() && cardsMatchSettings()) return;
  renderSeriesList();
};

// 1つのデータ元の列の選択肢を更新する（読込のたびに呼ぶ）。
export const setSourceColumns = (id, newColumns) => {
  columnsById.set(id, newColumns);
};

export const dropSourceColumns = (keepIds) => {
  const keep = new Set(keepIds);
  for (const id of Array.from(columnsById.keys())) if (!keep.has(id)) columnsById.delete(id);
};

// 読込後の整合: もう存在しない列の選択は解除する（再描画は呼び出し側が行う）。列の選択肢が分かっているデータ元の系列だけを見る。
export const reconcileColumns = () => {
  const settings = getSettings();
  const first = settings.series[0];
  const firstColumns = first ? columnsById.get(sourceIdOf(first)) : null;
  if (settings.plot.xColumn && firstColumns && !firstColumns.some((c) => c.value === settings.plot.xColumn)) {
    setPath("plot.xColumn", "", "reconcile");
  }
  for (const s of settings.series) {
    const known = columnsById.get(sourceIdOf(s));
    if (!known) continue;
    const valid = new Set(known.map((c) => c.value));
    const patch = {};
    if (s.x && !valid.has(s.x)) patch.x = "";
    if (s.y && !valid.has(s.y)) patch.y = "";
    if (Object.keys(patch).length) updateSeries(s.id, patch, "reconcile");
  }
  refreshSources();
};

const FIELD_BY_CLASS = [
  ["series-x", "x", "text"],
  ["series-y", "y", "text"],
  ["series-line-width", "lineWidth", "number"],
  ["series-line-style", "lineStyle", "text"],
  ["series-marker-size", "markerSize", "number"],
  ["series-legend-name", "label", "text"],
  ["series-use-y2", "secondaryAxis", "checkbox"],
];

// データ元を替えたら、X / Y は自動に戻す（別のファイルの列番号は意味が変わる）。系列1なら棒グラフの X列も戻す
const onSourceChange = (seriesId, source) => {
  const { series, plot } = getSettings();
  const current = series.find((s) => s.id === seriesId);
  if (!current || sourceIdOf(current) === source) return;
  if (series[0] && series[0].id === seriesId && plot.xColumn) setPath("plot.xColumn", "");
  updateSeries(seriesId, { source, x: "", y: "" });
  refreshSources();
};

const onSeriesInput = (event) => {
  const target = event.target;
  if (!target || !target.matches || !target.matches("input, select")) return;
  const item = target.closest(".series-item");
  if (!item) return;
  if (target.classList.contains("series-source")) {
    onSourceChange(item.dataset.seriesId, target.value);
    return;
  }
  const entry = FIELD_BY_CLASS.find(([cls]) => target.classList.contains(cls));
  if (!entry) return;
  const [, field, kind] = entry;
  const value = kind === "checkbox" ? target.checked : kind === "number" ? readNumber(target) : target.value;
  updateSeries(item.dataset.seriesId, { [field]: value });
};

export const bindSeriesEvents = () => {
  const list = document.getElementById("seriesList");
  const addBtn = document.getElementById("addSeriesBtn");
  if (addBtn) addBtn.addEventListener("click", () => addSeries());
  if (list) {
    list.addEventListener("input", onSeriesInput);
    list.addEventListener("change", onSeriesInput);
  }
};
