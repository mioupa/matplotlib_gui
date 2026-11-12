// 近似曲線のカード。カードは state の fits から描く。系列の選択肢は系列の変更のたびに同期する。
import { addFit, getSettings, removeFit, updateFit } from "../state.js";
import { bindSeriesColorControls, colorPickerHtml } from "./colorPicker.js";
import { readNumber } from "./forms.js";
import { usesFits } from "../chart-types.js";
import { seriesDisplayName } from "./series.js";

const MAX_FITS = 20;
const esc = (text) =>
  String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const PARAM_NAMES = ["a", "b", "c", "d", "e"];

// 式の中で使っているパラメータ（単独の a〜e）。exp・abs・cos や 1e3 の中の e は数えない
export const usedParams = (expr) => {
  const found = new Set(String(expr || "").match(/(?<![A-Za-z0-9_.])[a-e](?![A-Za-z0-9_])/g) || []);
  return PARAM_NAMES.filter((p) => found.has(p));
};

const initialHtml = (f, id) =>
  PARAM_NAMES.map(
    (p) => `
      <div class="fit-initial-item" data-param="${p}" hidden>
        <label for="${id(`initial-${p}`)}">${p}</label>
        <input id="${id(`initial-${p}`)}" type="number" step="any" value="${esc((f.initial || {})[p] ?? "")}" />
      </div>`,
  ).join("");

const seriesOptions = () =>
  getSettings().series.map((s, i) => {
    const name = seriesDisplayName(s);
    return { value: s.id, label: name ? `系列${i + 1}（${name}）` : `系列${i + 1}` };
  });

const fillSeriesSelect = (select, selected) => {
  const options = seriesOptions();
  select.innerHTML = "";
  for (const opt of options) {
    const o = document.createElement("option");
    o.value = opt.value;
    o.textContent = opt.label;
    select.appendChild(o);
  }
  select.value = options.some((o) => o.value === selected) ? selected : "";
};

const cardHtml = (f, index) => {
  const id = (name) => `fit-${f.id}-${name}`;
  return `
    <div class="series-item-header">
      <div class="series-item-title">近似曲線 ${index + 1}</div>
      <button type="button" id="${id("remove")}" class="small-btn ghost-btn" aria-label="近似曲線 ${index + 1} を削除">削除</button>
    </div>
    <div class="group">
      <label for="${id("series")}">系列</label>
      <select id="${id("series")}"></select>
    </div>
    <div class="row group">
      <div>
        <label for="${id("model")}">種類</label>
        <select id="${id("model")}">
          <option value="linear">1次式（直線）</option>
          <option value="poly">多項式</option>
          <option value="custom">任意の式</option>
        </select>
      </div>
      <div class="fit-degree-wrap">
        <label for="${id("degree")}">次数（2〜6）</label>
        <input id="${id("degree")}" type="number" min="2" max="6" step="1" value="${esc(f.degree ?? "")}" />
      </div>
    </div>
    <div class="group fit-custom-wrap" hidden>
      <label for="${id("expr")}">式（y = ）</label>
      <input id="${id("expr")}" type="text" maxlength="200" value="${esc(f.expr)}" placeholder="例: a*exp(-b*x) + c" autocomplete="off" spellcheck="false" />
      <div id="${id("expr-help")}" class="help-text">変数は x、パラメータは a〜e です。使える関数: abs sqrt exp log log10 sin cos tan。べき乗は ^ か ** で書きます。</div>
      <div class="fit-initial-label help-text">パラメータの初期値（収束しないときは変えてみてください）</div>
      <div class="fit-initial-row">${initialHtml(f, id)}</div>
    </div>
    <div class="group">
      <label for="${id("show")}">式と R² の表示</label>
      <select id="${id("show")}">
        <option value="legend">凡例</option>
        <option value="text">図の中（左上）</option>
        <option value="none">出さない（線だけ）</option>
      </select>
    </div>
    <div class="row group">
      <div>
        <label for="${id("color")}">線の色</label>
        <select id="${id("color")}">
          <option value="">系列の色</option>
          <option value="custom">色を選ぶ</option>
        </select>
        <div class="fit-color-picker-wrap">${colorPickerHtml(id("color-picker"), f.color || "#000000")}</div>
      </div>
      <div>
        <label for="${id("line-style")}">線種</label>
        <select id="${id("line-style")}">
          <option value="solid">solid</option>
          <option value="dashed">dashed</option>
          <option value="dashdot">dashdot</option>
          <option value="dotted">dotted</option>
        </select>
      </div>
    </div>`;
};

const seriesColorOf = (seriesId) => {
  const s = getSettings().series.find((x) => x.id === seriesId);
  return s ? s.color : "#000000";
};

const buildCard = (f, index) => {
  const item = document.createElement("div");
  item.className = "series-item fit-item";
  item.id = `fit-${f.id}`;
  item.dataset.fitId = f.id;
  item.innerHTML = cardHtml(f, index);
  const get = (name) => item.querySelector(`#fit-${f.id}-${name}`);
  fillSeriesSelect(get("series"), f.series);
  get("series").dataset.options = JSON.stringify(seriesOptions());
  get("model").value = f.model;
  get("show").value = f.show;
  get("line-style").value = f.lineStyle;
  get("color").value = f.color ? "custom" : "";
  // 色を選ぶときの初めの色: 系列の色（設定の color は選んだ時点で書く）
  const picker = item.querySelector(".series-color");
  if (!f.color) picker.value = seriesColorOf(f.series);
  bindSeriesColorControls(item, (color) => updateFit(f.id, { color }));
  get("remove").addEventListener("click", () => removeFit(f.id));
  return item;
};

const syncCard = (item, f) => {
  item.querySelector(".fit-degree-wrap").hidden = f.model !== "poly";
  item.querySelector(".fit-custom-wrap").hidden = f.model !== "custom";
  const used = usedParams(f.expr);
  for (const wrap of item.querySelectorAll(".fit-initial-item")) wrap.hidden = !used.includes(wrap.dataset.param);
  item.querySelector(".fit-color-picker-wrap").hidden = !f.color;
  // 系列の選択肢（系列の追加・削除・並べ替え・名前の変更に追従する）
  const select = item.querySelector(`#fit-${f.id}-series`);
  const options = JSON.stringify(seriesOptions());
  if (select.dataset.options !== options) {
    fillSeriesSelect(select, f.series);
    select.dataset.options = options;
  }
};

export const syncFits = () => {
  const { fits, plot } = getSettings();
  const isBar = !usesFits(plot.type); // 棒グラフ・ヒストグラムでは使わない（一覧と追加ボタンを隠す）
  const list = document.getElementById("fitList");
  const add = document.getElementById("addFitBtn");
  const note = document.getElementById("fitBarNote");
  if (list) list.hidden = isBar;
  if (add) {
    add.hidden = isBar;
    add.disabled = fits.length >= MAX_FITS;
  }
  if (note) note.hidden = !isBar;
  const addAnn = document.getElementById("addAnnotationBtn");
  if (addAnn) addAnn.disabled = getSettings().annotations.length >= 50;
  for (const item of document.querySelectorAll("#fitList .fit-item")) {
    const f = fits.find((x) => x.id === item.dataset.fitId);
    if (f) syncCard(item, f);
  }
};

export const renderFitList = () => {
  const list = document.getElementById("fitList");
  if (!list) return;
  list.replaceChildren(...getSettings().fits.map((f, i) => buildCard(f, i)));
  syncFits();
};

const onInput = (event) => {
  const target = event.target;
  if (!target || !target.matches || !target.matches("input, select")) return;
  const item = target.closest(".fit-item");
  if (!item) return;
  const id = item.dataset.fitId;
  const name = target.id.replace(`fit-${id}-`, "");
  if (name === "series") updateFit(id, { series: target.value });
  else if (name === "model") updateFit(id, { model: target.value });
  else if (name === "expr") updateFit(id, { expr: target.value });
  else if (name.startsWith("initial-")) {
    const f = getSettings().fits.find((x) => x.id === id);
    if (f) updateFit(id, { initial: { ...(f.initial || {}), [name.slice(8)]: readNumber(target) } });
  } else if (name === "degree") updateFit(id, { degree: readNumber(target) });
  else if (name === "show") updateFit(id, { show: target.value });
  else if (name === "line-style") updateFit(id, { lineStyle: target.value });
  else if (name === "color") {
    if (target.value === "") updateFit(id, { color: "" });
    else {
      const f = getSettings().fits.find((x) => x.id === id);
      const current = item.querySelector(".series-color").value;
      updateFit(id, { color: current || (f ? seriesColorOf(f.series) : "#000000") });
    }
  }
};

export const bindFits = () => {
  const list = document.getElementById("fitList");
  const add = document.getElementById("addFitBtn");
  if (add) add.addEventListener("click", () => addFit());
  if (list) {
    list.addEventListener("input", onInput);
    list.addEventListener("change", onInput);
  }
  renderFitList();
};
