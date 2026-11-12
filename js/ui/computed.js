// 計算した列（G6）のカード。カードは state の computed から描く。
// 名前・式を入力中の欄は作り直さない（syncComputed は表示だけを同期する。annotations.js と同じ）。
import { addComputed, getSettings, MAX_COMPUTED, updateComputed } from "../state.js";
import { changeComputedSource, computedIndex, removeComputedColumn, resolveSource } from "../computed-refs.js";
import { fileColumnCount, renderSeriesList } from "./series.js";

const esc = (text) =>
  String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const TEMPLATES = {
  normalize: (n) => `[${n}] / max([${n}])`,
  offset: (n) => `[${n}] - first([${n}])`,
  rolling: (n) => `rolling_mean([${n}], 5)`,
};

// 雛形の N: 系列1のデータ元が同じで、Y が（計算した列でない）ファイルの列ならその番号。無ければ 1
const templateColumn = (c) => {
  const first = getSettings().series[0];
  if (!first || resolveSource(first.source) !== resolveSource(c.source)) return 1;
  const m = /^__idx__(\d+)$/.exec(first.y || "");
  const f = fileColumnCount(resolveSource(c.source));
  return m && f !== undefined && Number(m[1]) < f ? Number(m[1]) : 1;
};

const cardHtml = (c, index) => {
  const id = (name) => `computed-${c.id}-${name}`;
  return `
    <div class="series-item-header">
      <div class="series-item-title">計算した列 ${index + 1}</div>
      <button type="button" id="${id("remove")}" class="small-btn ghost-btn computed-remove">削除</button>
    </div>
    <div class="group computed-source-wrap" hidden>
      <label for="${id("source")}">データ元</label>
      <select id="${id("source")}"></select>
    </div>
    <div class="group">
      <label for="${id("name")}">名前</label>
      <input id="${id("name")}" type="text" maxlength="50" value="${esc(c.name)}" placeholder="計算${index + 1}" />
    </div>
    <div class="group">
      <label for="${id("expr")}">式</label>
      <input id="${id("expr")}" type="text" maxlength="200" value="${esc(c.expr)}" placeholder="[1] / max([1])" autocomplete="off" spellcheck="false" />
    </div>
    <div class="computed-templates group">
      <button type="button" id="${id("tpl-normalize")}" class="small-btn ghost-btn" data-tpl="normalize">正規化</button>
      <button type="button" id="${id("tpl-offset")}" class="small-btn ghost-btn" data-tpl="offset">オフセット</button>
      <button type="button" id="${id("tpl-rolling")}" class="small-btn ghost-btn" data-tpl="rolling">移動平均</button>
    </div>
    <div id="${id("index")}" class="help-text computed-index"></div>`;
};

const buildCard = (c, index) => {
  const item = document.createElement("div");
  item.className = "series-item computed-item";
  item.id = `computed-${c.id}`;
  item.dataset.computedId = c.id;
  item.innerHTML = cardHtml(c, index);
  item.querySelector(".computed-remove").addEventListener("click", () => removeComputedColumn(c.id));
  for (const button of item.querySelectorAll("[data-tpl]")) {
    button.addEventListener("click", () => {
      const current = getSettings().computed.find((x) => x.id === c.id);
      if (!current) return;
      const expr = TEMPLATES[button.dataset.tpl](templateColumn(current));
      item.querySelector(`#computed-${c.id}-expr`).value = expr;
      updateComputed(c.id, "expr", expr);
    });
  }
  return item;
};

// 表示の同期（入力中の欄を作り直さない。データ元・列の読込・カードの増減のたびに呼ぶ）
export const syncComputed = () => {
  const { computed, load } = getSettings();
  const add = document.getElementById("addComputedBtn");
  if (add) add.disabled = computed.length >= MAX_COMPUTED;
  const options = JSON.stringify(load.files.map((f) => [f.id, f.name]));
  computed.forEach((c, i) => {
    const item = document.getElementById(`computed-${c.id}`);
    if (!item) return;
    item.querySelector(".series-item-title").textContent = `計算した列 ${i + 1}`;
    item.querySelector(".computed-remove").setAttribute("aria-label", `計算した列 ${i + 1} を削除`);
    item.querySelector(`#computed-${c.id}-name`).placeholder = `計算${i + 1}`;
    const wrap = item.querySelector(".computed-source-wrap");
    wrap.hidden = load.files.length < 2;
    const select = item.querySelector(`#computed-${c.id}-source`);
    if (select.dataset.options !== options) {
      select.replaceChildren(
        ...load.files.map((f, n) => {
          const o = document.createElement("option");
          o.value = f.id;
          o.textContent = `データ${n + 1}: ${f.name}`;
          return o;
        }),
      );
      select.dataset.options = options;
    }
    select.value = resolveSource(c.source);
    const k = computedIndex(c.id);
    const line = item.querySelector(".computed-index");
    line.textContent = k === null ? "（ファイルを読み込むと番号が決まります）" : `列 [${k}] として使えます`;
  });
};

export const renderComputedList = () => {
  const list = document.getElementById("computedList");
  if (!list) return;
  list.replaceChildren(...getSettings().computed.map((c, i) => buildCard(c, i)));
  syncComputed();
};

const onInput = (event) => {
  const target = event.target;
  if (!target || !target.matches || !target.matches("input, select")) return;
  const item = target.closest(".computed-item");
  if (!item) return;
  const id = item.dataset.computedId;
  const name = target.id.replace(`computed-${id}-`, "");
  if (name === "name") updateComputed(id, "name", target.value);
  else if (name === "expr") updateComputed(id, "expr", target.value);
  else if (name === "source") {
    changeComputedSource(id, target.value);
    renderSeriesList(); // 参照を付け替えた系列のカードを描き直す
  }
};

export const bindComputed = () => {
  const list = document.getElementById("computedList");
  const add = document.getElementById("addComputedBtn");
  if (add) add.addEventListener("click", () => addComputed());
  if (list) {
    list.addEventListener("input", onInput);
    list.addEventListener("change", onInput);
  }
  renderComputedList();
};
