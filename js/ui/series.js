// 系列カード（追加・削除・列セレクト・種別/第2軸に応じた表示切替）。カードは state の系列リストから描く。
import { addSeries, duplicateSeries, getSettings, hasSecondaryAxis, moveSeries, removeSeries, updateSeries, setPath } from "../state.js";
import { addNote } from "../bridge.js";
import { bindSeriesColorControls } from "./colorPicker.js";
import { syncAxisTicks } from "./axisTicks.js";
import { readNumber } from "./forms.js";
import { computedOfSource, shiftForFileColumnChange } from "../computed-refs.js";
import {
  isLineLike,
  usesColorColumn,
  usesFill as typeUsesFill,
  usesGlobalX,
  usesHist,
  usesMarker,
  usesSeriesX,
  usesStep,
  usesXErrors,
  usesY2,
  usesYErrors,
} from "../chart-types.js";

// データ元（ファイル id）ごとの列の選択肢: [{value: "__idx__0", label: "時間 [0]", kind: "number"}]（読込のたびに更新。kind: datetime / number / text）
const columnsById = new Map();

const loadedFiles = () => getSettings().load.files;
const sourceIdOf = (series) => series.source || (loadedFiles()[0] ? loadedFiles()[0].id : "d1"); // "" は先頭のファイル
// データ元のファイルの列数（読み込んでいなければ undefined）
export const fileColumnCount = (id) => {
  const columns = columnsById.get(id);
  return columns ? columns.length : undefined;
};

// 計算した列（G6）の選択肢: ファイルの列の後ろに、カードの順で並ぶ（番号 = ファイルの列数 + 位置）。データ確認の表には出さない
const computedOptions = (sourceId, fileCount) => {
  const all = getSettings().computed;
  return computedOfSource(sourceId).map((c, pos) => {
    const n = all.indexOf(c) + 1;
    const k = fileCount + pos;
    return { value: `__idx__${k}`, label: `${c.name.trim() || `計算${n}`} [${k}]（計算）`, kind: "number", numericLike: true };
  });
};

// 系列のデータ元の列の選択肢（ファイルの列 + 計算した列）。列の選択肢を作る・検証するのはここだけ
const columnsOf = (series) => {
  const sid = sourceIdOf(series);
  const file = columnsById.get(sid);
  return file ? [...file, ...computedOptions(sid, file.length)] : [];
};
const hasManySources = () => loadedFiles().length >= 2;

const isDatetimeColumn = (columns, value) => !!value && columns.some((c) => c.value === value && c.kind === "datetime");

// X に日時の列を使っているか（line / scatter はどれかの系列の X（その系列のデータ元の列）、bar は X列（系列1のデータ元））
export const usesDatetimeX = () => {
  const { plot, series } = getSettings();
  if (usesHist(plot.type)) return false;
  if (usesGlobalX(plot.type)) return series.length > 0 && isDatetimeColumn(columnsOf(series[0]), plot.xColumn);
  return series.some((s) => isDatetimeColumn(columnsOf(s), s.x));
};

// 棒グラフのカテゴリ側の軸の種類。系列が複数、または X 列が数値でない（日時を含む）ならカテゴリ。X 列なし・数値なら numeric
const barCategoryKind = (numeric) => {
  const { plot, series } = getSettings();
  if (series.length > 1) return "category";
  const col = series[0] && plot.xColumn ? columnsOf(series[0]).find((c) => c.value === plot.xColumn) : undefined;
  return col && col.kind !== "number" ? "category" : numeric;
};

// X 軸の種類（Python の dataprep と同じ規則。number / log / datetime / category）
//  bar: 系列が複数、または X 列が数値でない（日時を含む）ならカテゴリ。X 列なし・数値なら数値
//  step / scatterColor: line / scatter と同じ
//  barStacked: 常にカテゴリ。barh: 横軸（X 軸の設定）は値なので数値 / 対数（縦軸は yAxisKind）。hist: 横軸は値（数値 / 対数）
//  line / scatter: どれかの系列の X が日時なら日時、数値でない文字列の列（numericLike でない）ならカテゴリ。X 列なし（行番号）は数値
export const xAxisKind = () => {
  const { plot, series, axes } = getSettings();
  const numeric = axes.x.scale === "log" ? "log" : "number";
  const find = (columns, value) => (value ? columns.find((c) => c.value === value) : undefined);
  if (plot.type === "barStacked") return "category";
  if (plot.type === "barh" || usesHist(plot.type)) return numeric;
  if (plot.type === "bar") return barCategoryKind(numeric);
  const cols = series.map((s) => find(columnsOf(s), s.x));
  if (cols.some((c) => c && c.kind === "datetime")) return "datetime";
  if (cols.some((c) => c && c.kind === "text" && c.numericLike === false)) return "category";
  return numeric;
};

// Y 軸の種類（number / log / category）。横棒（barh）の縦軸はカテゴリ（bar の X と同じ規則。1系列で X 列が数値なら number。対数にはならない）。
// それ以外は Y のスケールで決める
export const yAxisKind = () => {
  const { plot, axes } = getSettings();
  if (plot.type === "barh") return barCategoryKind("number");
  return axes.y.scale === "log" ? "log" : "number";
};

// 系列の表示名（凡例名があればそれ、無ければ Y 列の表示）。近似曲線の系列の選択肢に使う
export const seriesDisplayName = (series) => {
  if (series.label) return series.label;
  const col = columnsOf(series).find((c) => c.value === series.y);
  return col ? col.label : "";
};

// 画面の同期（syncVisibility）の最後に呼ぶ関数を足す（注釈・近似曲線のカード。series.js から循環して import しないため）
const visibilityHooks = [];
export const addVisibilityHook = (fn) => visibilityHooks.push(fn);

const esc = (text) =>
  String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const defaultMarkerSize = (plotType) => (isLineLike(plotType) ? 0 : 24);
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

const colorColumnOptions = (columns) => [{ value: "", label: "（選択してください）" }, ...columns];
const xOptions = (columns) => [{ value: "", label: "(index)" }, ...columns];
const yOptions = (columns) => [{ value: "", label: "(自動)" }, ...columns];
const sourceOptions = () => loadedFiles().map((f, i) => ({ value: f.id, label: `データ${i + 1}: ${f.name}` }));

// エラーバーの折りたたみの開閉（系列 id ごと。セッション中だけ覚え、カードを作り直しても保つ）
// 覚えていない系列は、エラーバーを使っていれば開いて作る
const openErrorBars = new Map();
const errorBarsOpen = (series) => (openErrorBars.has(series.id) ? openErrorBars.get(series.id) : usesErrorBars(series));
const usesErrorBars = (series) => !!series.errorBars && ["y", "x"].some((d) => series.errorBars[d].mode !== "none");

const errorBlockHtml = (series, dir) => {
  const id = (name) => `series-${series.id}-${dir}err-${name}`;
  const title = dir === "y" ? "Y方向" : "X方向";
  const sameLabel = dir === "y" ? "上下で同じ値" : "左右で同じ値";
  return `
    <div class="err-block err-${dir}" data-err-dir="${dir}">
      <div class="group">
        <label for="${id("mode")}">${title}</label>
        <select id="${id("mode")}" data-err="${dir}.mode">
          <option value="none">なし</option>
          <option value="fixed">固定値</option>
          <option value="column">列で指定</option>
        </select>
      </div>
      <div class="group err-symmetric-wrap">
        <label class="inline check-label">
          <input id="${id("symmetric")}" type="checkbox" data-err="${dir}.symmetric" />
          <span>${sameLabel}</span>
        </label>
      </div>
      <div class="row group err-fixed-wrap">
        <div>
          <label for="${id("value")}" class="err-value-label"></label>
          <input id="${id("value")}" type="number" min="0" step="any" data-err="${dir}.value" />
        </div>
        <div class="err-minus-wrap">
          <label for="${id("value-minus")}">${dir === "y" ? "下（−）" : "左（−）"}</label>
          <input id="${id("value-minus")}" type="number" min="0" step="any" data-err="${dir}.valueMinus" />
        </div>
      </div>
      <div class="row group err-column-wrap">
        <div>
          <label for="${id("column")}" class="err-column-label"></label>
          <select id="${id("column")}" data-err="${dir}.column"></select>
        </div>
        <div class="err-minus-wrap">
          <label for="${id("column-minus")}">${dir === "y" ? "下（−）" : "左（−）"}</label>
          <select id="${id("column-minus")}" data-err="${dir}.columnMinus"></select>
        </div>
      </div>
    </div>`;
};

const cardHtml = (series, plotType) => {
  const id = (name) => `series-${series.id}-${name}`;
  return `
    <div class="series-item-header">
      <div class="series-item-title">系列</div>
      <div class="series-item-actions">
        <button type="button" id="${id("up")}" class="small-btn ghost-btn move-series-up">↑</button>
        <button type="button" id="${id("down")}" class="small-btn ghost-btn move-series-down">↓</button>
        <button type="button" id="${id("duplicate")}" class="small-btn ghost-btn duplicate-series">複製</button>
        <button type="button" id="${id("remove")}" class="small-btn ghost-btn remove-series">削除</button>
      </div>
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
      <div class="series-marker-size-wrap">
        <label for="${id("marker-size")}">点サイズ</label>
        <input id="${id("marker-size")}" class="series-marker-size" type="number" step="1" value="${esc(displayMarkerSize(series, plotType))}" />
      </div>
    </div>
    <div class="row group">
      <div class="series-marker-wrap">
        <label for="${id("marker")}">点の形</label>
        <select id="${id("marker")}" class="series-marker">
          <option value="auto">自動</option>
          <option value="none">なし</option>
          <option value="o">丸</option>
          <option value="s">四角</option>
          <option value="^">上三角</option>
          <option value="v">下三角</option>
          <option value="D">ひし形</option>
          <option value="x">×</option>
          <option value="+">+</option>
          <option value="*">星</option>
        </select>
      </div>
      <div>
        <label for="${id("alpha")}">不透明度</label>
        <input id="${id("alpha")}" class="series-alpha" type="number" min="0" max="1" step="0.1" value="${esc(series.alpha ?? "")}" />
      </div>
    </div>
    <div class="group">
      <label for="${id("legend-name")}">凡例名（任意）</label>
      <input id="${id("legend-name")}" class="series-legend-name" type="text" value="${esc(series.label)}" placeholder="自動" />
    </div>
    <div class="group series-color-column-wrap" hidden>
      <label for="${id("color-column")}">色分けの列</label>
      <select id="${id("color-column")}" class="series-color-column"></select>
    </div>
    <div class="group series-y2-wrap">
      <label class="inline check-label">
        <input id="${id("use-y2")}" class="series-use-y2" type="checkbox" ${series.secondaryAxis ? "checked" : ""} />
        <span>第2軸を使用</span>
      </label>
    </div>
    <details class="series-errorbars" id="${id("errorbars")}" ${errorBarsOpen(series) ? "open" : ""}>
      <summary class="series-errorbars-summary">エラーバー</summary>
      <div class="series-errorbars-body">
        ${errorBlockHtml(series, "y")}
        <div class="err-x-wrap">${errorBlockHtml(series, "x")}</div>
        <div class="group err-capsize-wrap">
          <label for="${id("err-capsize")}">端の長さ（pt）</label>
          <input id="${id("err-capsize")}" type="number" min="0" max="50" step="0.5" data-err="capSize" />
        </div>
      </div>
    </details>
    <details class="series-fill" id="${id("fill")}" ${fillOpen(series) ? "open" : ""}>
      <summary class="series-errorbars-summary">塗りつぶし帯</summary>
      <div class="series-errorbars-body">
        <div class="help-text group">下端と上端の列の間を塗ります（値そのもの。誤差の大きさではありません）。</div>
        <div class="row group">
          <div>
            <label for="${id("fill-lower")}">下端の列</label>
            <select id="${id("fill-lower")}" data-fill="lower"></select>
          </div>
          <div>
            <label for="${id("fill-upper")}">上端の列</label>
            <select id="${id("fill-upper")}" data-fill="upper"></select>
          </div>
        </div>
        <div class="group">
          <label for="${id("fill-alpha")}">帯の不透明度（0〜1）</label>
          <input id="${id("fill-alpha")}" type="number" min="0" max="1" step="0.05" data-fill="alpha" />
        </div>
      </div>
    </details>
  `;
};

// 塗りつぶし帯の折りたたみの開閉（エラーバーと同じ。系列 id ごとにセッション中だけ覚える）
const openFill = new Map();
const usesFill = (series) => !!series.fill && !!(series.fill.lower || series.fill.upper);
const fillOpen = (series) => (openFill.has(series.id) ? openFill.get(series.id) : usesFill(series));
const fillColumnOptions = (columns) => [{ value: "", label: "（なし）" }, ...columns];

const errorColumnOptions = (columns) => [{ value: "", label: "（列を選択）" }, ...columns];

// エラーバーの入力欄に設定の値を入れる（カードを作るとき）
const fillErrorControls = (item, series, columns) => {
  const eb = series.errorBars;
  const set = (sel, value) => {
    const el = item.querySelector(sel);
    if (el.type === "checkbox") el.checked = !!value;
    else el.value = value === null || value === undefined ? "" : String(value);
  };
  for (const dir of ["y", "x"]) {
    const spec = eb[dir];
    const get = (key) => item.querySelector(`[data-err="${dir}.${key}"]`);
    fillSelect(get("column"), errorColumnOptions(columns), spec.column);
    fillSelect(get("columnMinus"), errorColumnOptions(columns), spec.columnMinus);
    get("mode").value = spec.mode;
    get("symmetric").checked = !!spec.symmetric;
    get("value").value = spec.value === null ? "" : String(spec.value);
    get("valueMinus").value = spec.valueMinus === null ? "" : String(spec.valueMinus);
  }
  set('[data-err="capSize"]', eb.capSize);
};

// エラーバーの欄の表示（カードを作り直さない。入力中の欄のフォーカスを保つ）
const syncErrorVisibility = (item, series, plotType) => {
  if (!series || !series.errorBars) return;
  const eb = series.errorBars;
  for (const dir of ["y", "x"]) {
    const spec = eb[dir];
    const block = item.querySelector(`.err-block[data-err-dir="${dir}"]`);
    if (!block) continue;
    const on = spec.mode !== "none";
    const sym = spec.symmetric;
    const plus = dir === "y" ? "上（+）" : "右（+）";
    block.querySelector(".err-symmetric-wrap").hidden = !on;
    const fixed = block.querySelector(".err-fixed-wrap");
    const column = block.querySelector(".err-column-wrap");
    fixed.hidden = spec.mode !== "fixed";
    column.hidden = spec.mode !== "column";
    fixed.querySelector(".err-minus-wrap").hidden = sym;
    column.querySelector(".err-minus-wrap").hidden = sym;
    fixed.querySelector(".err-value-label").textContent = sym ? "値" : plus;
    column.querySelector(".err-column-label").textContent = sym ? "列" : plus;
  }
  const xWrap = item.querySelector(".err-x-wrap");
  if (xWrap) xWrap.hidden = !usesXErrors(plotType);
  const details = item.querySelector(".series-errorbars");
  if (details) details.hidden = !usesYErrors(plotType); // 積み上げ棒・ヒストグラムはエラーバーを使わない
  const cap = item.querySelector(".err-capsize-wrap");
  if (cap) cap.hidden = !usesErrorBars(series);
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
  fillSelect(item.querySelector(".series-color-column"), colorColumnOptions(columns), series.colorColumn);
  item.querySelector(".series-source-wrap").hidden = !hasManySources();
  item.querySelector(".series-line-style").value = series.lineStyle;
  fillErrorControls(item, series, columns);
  item.querySelector(".series-marker").value = series.marker;
  fillSelect(item.querySelector('[data-fill="lower"]'), fillColumnOptions(columns), series.fill.lower);
  fillSelect(item.querySelector('[data-fill="upper"]'), fillColumnOptions(columns), series.fill.upper);
  item.querySelector('[data-fill="alpha"]').value = series.fill.alpha === null ? "" : String(series.fill.alpha);
  const details = item.querySelector(".series-errorbars");
  details.addEventListener("toggle", () => {
    openErrorBars.set(series.id, details.open);
  });
  const fillDetails = item.querySelector(".series-fill");
  fillDetails.addEventListener("toggle", () => {
    openFill.set(series.id, fillDetails.open);
  });
  bindSeriesColorControls(item, (color) => updateSeries(series.id, { color }));
  item.querySelector(".remove-series").addEventListener("click", () => {
    const index = getSettings().series.findIndex((x) => x.id === series.id);
    const removedFits = removeSeries(series.id);
    if (removedFits > 0) addNote(`系列${index + 1}を削除したため、その系列の近似曲線${removedFits}本も削除しました。`);
  });
  item.querySelector(".move-series-up").addEventListener("click", () => moveSeries(series.id, -1));
  item.querySelector(".move-series-down").addEventListener("click", () => moveSeries(series.id, 1));
  item.querySelector(".duplicate-series").addEventListener("click", () => duplicateSeries(series.id));
  return item;
};

// 種類ごとの欄の出し分け（規則は chart-types.js。Python と同じ。値は消さない）
const setHidden = (id, hidden) => {
  const el = document.getElementById(id);
  if (el) el.hidden = hidden;
};

export const syncVisibility = () => {
  const settings = getSettings();
  const type = settings.plot.type;
  setHidden("stepGroup", !usesStep(type));
  setHidden("histGroup", !usesHist(type));
  setHidden("colorMapGroup", !usesColorColumn(type));
  setHidden("yScaleGroup", type === "barh"); // 横棒の縦軸はカテゴリ（Y のスケールは使わない）
  const globalX = document.getElementById("globalXGroup");
  if (globalX) globalX.style.display = usesGlobalX(type) ? "" : "none";
  for (const group of document.querySelectorAll("#seriesList .series-x-wrap")) {
    group.style.display = usesSeriesX(type) ? "block" : "none";
  }
  for (const wrap of document.querySelectorAll("#seriesList .series-source-wrap")) wrap.hidden = !hasManySources();
  for (const item of document.querySelectorAll("#seriesList .series-item")) {
    const s = settings.series.find((x) => x.id === item.dataset.seriesId);
    syncErrorVisibility(item, s, type);
    const set = (selector, hidden) => {
      const el = item.querySelector(selector);
      if (el) el.hidden = hidden;
    };
    set(".series-marker-wrap", !usesMarker(type));
    set(".series-marker-size-wrap", !usesMarker(type));
    set(".series-fill", !typeUsesFill(type));
    set(".series-y2-wrap", !usesY2(type));
    set(".series-color-column-wrap", !usesColorColumn(type));
    // 点の形が「なし」の折れ線（line / step）は点サイズを使わない
    const size = item.querySelector(".series-marker-size");
    if (size && s) size.disabled = isLineLike(type) && s.marker === "none";
  }
  const dateGroup = document.getElementById("xDateFormatGroup");
  if (dateGroup) dateGroup.hidden = !usesDatetimeX();
  syncAxisTicks(xAxisKind(), yAxisKind());
  const hasY2 = hasSecondaryAxis();
  for (const id of ["y2LabelGroup", "y2AxisSettingsGroup"]) {
    const el = document.getElementById(id);
    if (el) el.style.display = hasY2 ? "" : "none";
  }
  for (const hook of visibilityHooks) hook();
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
    const up = item.querySelector(".move-series-up");
    const down = item.querySelector(".move-series-down");
    up.disabled = idx === 0;
    down.disabled = idx === items.length - 1;
    up.setAttribute("aria-label", `系列 ${idx + 1} を上へ`);
    down.setAttribute("aria-label", `系列 ${idx + 1} を下へ`);
    item.querySelector(".duplicate-series").setAttribute("aria-label", `系列 ${idx + 1} を複製`);
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
  syncAxisTicks(xAxisKind(), yAxisKind());
  // データ元と列の選択肢が変わっていなければ、カードは描き直さない（入力中の欄や開いている選択肢を保つ）
  if (renderedStructure === structureOf() && cardsMatchSettings()) {
    for (const hook of visibilityHooks) hook(); // 計算した列の番号の表示など
    return;
  }
  renderSeriesList();
};

// 1つのデータ元の列の選択肢を更新する（読込のたびに呼ぶ）。
export const setSourceColumns = (id, newColumns) => {
  const old = columnsById.get(id);
  columnsById.set(id, newColumns);
  // ファイルの列数が変わったら、計算した列を指す参照を同じだけずらす（reconcileColumns より前）
  if (old && old.length !== newColumns.length) shiftForFileColumnChange(id, old.length, newColumns.length);
};

export const dropSourceColumns = (keepIds) => {
  const keep = new Set(keepIds);
  for (const id of Array.from(columnsById.keys())) if (!keep.has(id)) columnsById.delete(id);
};

// 読込後の整合: もう存在しない列の選択は解除する（再描画は呼び出し側が行う）。列の選択肢が分かっているデータ元の系列だけを見る。
export const reconcileColumns = () => {
  const settings = getSettings();
  const first = settings.series[0];
  const firstColumns = first && columnsById.get(sourceIdOf(first)) ? columnsOf(first) : null;
  if (settings.plot.xColumn && firstColumns && !firstColumns.some((c) => c.value === settings.plot.xColumn)) {
    setPath("plot.xColumn", "", "reconcile");
  }
  for (const s of settings.series) {
    const known = columnsById.get(sourceIdOf(s));
    if (!known) continue;
    const valid = new Set(columnsOf(s).map((c) => c.value));
    const patch = {};
    if (s.x && !valid.has(s.x)) patch.x = "";
    if (s.y && !valid.has(s.y)) patch.y = "";
    // 誤差の列も、もう無い列なら解除する（方式は残し、Python が列を選ぶよう案内する）
    if (s.errorBars) {
      let next = null;
      for (const dir of ["y", "x"]) {
        for (const key of ["column", "columnMinus"]) {
          const v = s.errorBars[dir][key];
          if (v && !valid.has(v)) {
            next = next || cloneErrorBars(s.errorBars);
            next[dir][key] = "";
          }
        }
      }
      if (next) patch.errorBars = next;
    }
    if (s.colorColumn && !valid.has(s.colorColumn)) patch.colorColumn = ""; // 色分けの列も同じ（Python が列を選ぶよう案内する）
    // 塗りつぶし帯の列も同じ（もう無い列なら解除し、帯が消えることを知らせる）
    if (s.fill && ["lower", "upper"].some((k) => s.fill[k] && !valid.has(s.fill[k]))) {
      const fill = { ...s.fill };
      for (const k of ["lower", "upper"]) if (fill[k] && !valid.has(fill[k])) fill[k] = "";
      patch.fill = fill;
      addNote(`系列${settings.series.indexOf(s) + 1}: 塗りつぶし帯の列が無くなったため、帯の列を空に戻しました。`);
    }
    if (Object.keys(patch).length) updateSeries(s.id, patch, "reconcile");
  }
  refreshSources();
};

const cloneErrorBars = (eb) => JSON.parse(JSON.stringify(eb));

const FIELD_BY_CLASS = [
  ["series-x", "x", "text"],
  ["series-y", "y", "text"],
  ["series-line-width", "lineWidth", "number"],
  ["series-line-style", "lineStyle", "text"],
  ["series-marker-size", "markerSize", "number"],
  ["series-marker", "marker", "text"],
  ["series-alpha", "alpha", "number"],
  ["series-color-column", "colorColumn", "text"],
  ["series-legend-name", "label", "text"],
  ["series-use-y2", "secondaryAxis", "checkbox"],
];

// データ元を替えたら、X / Y は自動に戻す（別のファイルの列番号は意味が変わる）。系列1なら棒グラフの X列も戻す
const onSourceChange = (seriesId, source) => {
  const { series, plot } = getSettings();
  const current = series.find((s) => s.id === seriesId);
  if (!current || sourceIdOf(current) === source) return;
  if (series[0] && series[0].id === seriesId && plot.xColumn) setPath("plot.xColumn", "");
  const errorBars = cloneErrorBars(current.errorBars);
  for (const dir of ["y", "x"]) Object.assign(errorBars[dir], { column: "", columnMinus: "" });
  const patch = { source, x: "", y: "", errorBars, colorColumn: "" };
  if (usesFill(current)) {
    patch.fill = { ...current.fill, lower: "", upper: "" };
    addNote(`系列${series.indexOf(current) + 1}: データ元を替えたため、塗りつぶし帯の列を空に戻しました（帯は描きません）。`);
  }
  updateSeries(seriesId, patch);
  refreshSources();
};

// エラーバーの欄の変更: 現在の errorBars を複製して1項目を書き換える
const onErrorInput = (seriesId, target) => {
  const current = getSettings().series.find((s) => s.id === seriesId);
  if (!current) return;
  const next = cloneErrorBars(current.errorBars);
  const [first, key] = target.dataset.err.split(".");
  if (first === "capSize") {
    next.capSize = readNumber(target);
  } else {
    const kind = target.type === "checkbox" ? "checkbox" : target.type === "number" ? "number" : "text";
    next[first][key] = kind === "checkbox" ? target.checked : kind === "number" ? readNumber(target) : target.value;
  }
  updateSeries(seriesId, { errorBars: next });
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
  if (target.dataset.err) {
    onErrorInput(item.dataset.seriesId, target);
    return;
  }
  if (target.dataset.fill) {
    const current = getSettings().series.find((x) => x.id === item.dataset.seriesId);
    if (current) updateSeries(current.id, { fill: { ...current.fill, [target.dataset.fill]: target.dataset.fill === "alpha" ? readNumber(target) : target.value } });
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
