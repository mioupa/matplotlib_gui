// 注釈（文字・水平線・垂直線・横の帯・縦の帯）のカード。カードは state の annotations から描く。
// 入力欄の出し分けは Python（settings / dataprep）と同じ規則: 使わない項目は隠し、値は残す（要件 §2.2）。
import { addAnnotation, getSettings, hasSecondaryAxis, removeAnnotation, updateAnnotation } from "../state.js";
import { bindSeriesColorControls, colorPickerHtml } from "./colorPicker.js";
import { readNumber } from "./forms.js";
import { xAxisKind } from "./series.js";

const esc = (text) =>
  String(text ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const KINDS = [
  ["text", "文字"],
  ["hline", "水平線"],
  ["vline", "垂直線"],
  ["hspan", "横の帯（Yの範囲）"],
  ["vspan", "縦の帯（Xの範囲）"],
];

// 要素 id の末尾 → 設定のキー（種別: text / number）
const FIELD_KEYS = {
  kind: ["kind", "text"],
  text: ["text", "text"],
  coords: ["coords", "text"],
  x: ["x", "text"],
  y: ["y", "text"],
  start: ["start", "text"],
  end: ["end", "text"],
  axis: ["axis", "text"],
  "line-style": ["lineStyle", "text"],
  "line-width": ["lineWidth", "number"],
  alpha: ["alpha", "number"],
  "font-size": ["fontSize", "number"],
  label: ["label", "text"],
};

const X_EXAMPLE = {
  number: "例 1.5",
  log: "例 1.5",
  datetime: "例 2026-01-31 12:00",
  category: "何番目か（0 始まり）",
};
const X_HELP = {
  number: "X 軸の値（数）です。",
  log: "X 軸の値（数）です。対数軸では 0 より大きい値にしてください。",
  datetime: "年が先頭の日付・日時です（例 2026-01-31 12:00）。",
  category: "何番目のカテゴリか（0 始まりの数）です。1.5 なら 2 つ目と 3 つ目の間です。",
};

const cardHtml = (a, index) => {
  const id = (name) => `annotation-${a.id}-${name}`;
  const text = (name, label, extra = "") => `
    <div class="group ann-field" data-ann-field="${name}">
      <label for="${id(name)}">${label}</label>
      <input id="${id(name)}" type="text" value="${esc(a[FIELD_KEYS[name][0]])}" ${extra} />
      <div class="help-text ann-help" hidden></div>
    </div>`;
  return `
    <div class="series-item-header">
      <div class="series-item-title">注釈 ${index + 1}</div>
      <button type="button" id="${id("remove")}" class="small-btn ghost-btn" aria-label="注釈 ${index + 1} を削除">削除</button>
    </div>
    <div class="group">
      <label for="${id("kind")}">種類</label>
      <select id="${id("kind")}">${KINDS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
    </div>
    <div class="group ann-field" data-ann-field="text">
      <label for="${id("text")}">文字（数式は $...$ で書けます）</label>
      <input id="${id("text")}" type="text" maxlength="200" value="${esc(a.text)}" />
    </div>
    <div class="group ann-field" data-ann-field="coords">
      <label for="${id("coords")}">位置の指定</label>
      <select id="${id("coords")}">
        <option value="data">データの座標</option>
        <option value="axes">図の中の割合（0〜1）</option>
      </select>
    </div>
    ${text("x", "X")}
    ${text("y", "Y")}
    ${text("start", "開始")}
    ${text("end", "終了")}
    <div class="group ann-field" data-ann-field="axis">
      <label for="${id("axis")}">Y 軸</label>
      <select id="${id("axis")}">
        <option value="y">左（第1Y軸）</option>
        <option value="y2">右（第2Y軸）</option>
      </select>
    </div>
    <div class="row group">
      <div>
        <label for="${id("color-trigger")}">色</label>
        ${colorPickerHtml(id("color"), a.color)}
      </div>
      <div class="ann-field" data-ann-field="alpha">
        <label for="${id("alpha")}">不透明度</label>
        <input id="${id("alpha")}" type="number" min="0" max="1" step="0.1" value="${esc(a.alpha ?? "")}" placeholder="自動" />
      </div>
    </div>
    <div class="row group ann-field" data-ann-field="line">
      <div>
        <label for="${id("line-style")}">線種</label>
        <select id="${id("line-style")}">
          <option value="solid">solid</option>
          <option value="dashed">dashed</option>
          <option value="dashdot">dashdot</option>
          <option value="dotted">dotted</option>
        </select>
      </div>
      <div>
        <label for="${id("line-width")}">線幅</label>
        <input id="${id("line-width")}" type="number" min="0" step="0.1" value="${esc(a.lineWidth ?? "")}" />
      </div>
    </div>
    <div class="group ann-field" data-ann-field="font-size">
      <label for="${id("font-size")}">文字の大きさ（pt）</label>
      <input id="${id("font-size")}" type="number" min="1" step="1" value="${esc(a.fontSize ?? "")}" placeholder="図と同じ" />
    </div>
    <div class="group ann-field" data-ann-field="label">
      <label for="${id("label")}">凡例名（任意）</label>
      <input id="${id("label")}" type="text" value="${esc(a.label)}" placeholder="空なら凡例に出さない" />
    </div>`;
};

const buildCard = (a, index) => {
  const item = document.createElement("div");
  item.className = "series-item annotation-item";
  item.id = `annotation-${a.id}`;
  item.dataset.annId = a.id;
  item.innerHTML = cardHtml(a, index);
  item.querySelector(`#annotation-${a.id}-kind`).value = a.kind;
  item.querySelector(`#annotation-${a.id}-coords`).value = a.coords;
  item.querySelector(`#annotation-${a.id}-axis`).value = a.axis;
  item.querySelector(`#annotation-${a.id}-line-style`).value = a.lineStyle;
  bindSeriesColorControls(item, (color) => updateAnnotation(a.id, { color }));
  item.querySelector(`#annotation-${a.id}-remove`).addEventListener("click", () => removeAnnotation(a.id));
  return item;
};

// 種類ごとの表示（Python の使う項目と同じ）
const SHOWN = {
  text: ["text", "coords", "x", "y", "font-size"],
  hline: ["y", "line", "label"],
  vline: ["x", "line", "label"],
  hspan: ["start", "end", "label"],
  vspan: ["start", "end", "label"],
};

const syncCard = (item, a, xKind, hasY2) => {
  const shown = new Set(SHOWN[a.kind] || []);
  shown.add("alpha");
  const dataY = a.kind === "hline" || a.kind === "hspan" || (a.kind === "text" && a.coords === "data");
  if (hasY2 && dataY) shown.add("axis");
  for (const el of item.querySelectorAll(".ann-field")) el.hidden = !shown.has(el.dataset.annField);
  const id = (name) => `annotation-${a.id}-${name}`;
  const label = (name, text) => {
    const el = item.querySelector(`label[for="${id(name)}"]`);
    if (el) el.textContent = text;
  };
  const note = (name, example, help) => {
    const input = item.querySelector(`#${id(name)}`);
    input.placeholder = example;
    const helpEl = input.closest(".ann-field").querySelector(".ann-help");
    helpEl.textContent = help;
    helpEl.hidden = !help;
  };
  const axesCoords = a.kind === "text" && a.coords === "axes";
  const yExample = ["例 1.5", "Y 軸の値（数）です。"];
  if (a.kind === "text") {
    label("x", "X");
    label("y", "Y");
    if (axesCoords) {
      note("x", "0〜1", "図の左端が 0、右端が 1 です。");
      note("y", "0〜1", "図の下端が 0、上端が 1 です。");
    } else {
      note("x", X_EXAMPLE[xKind], X_HELP[xKind]);
      note("y", ...yExample);
    }
  } else if (a.kind === "hline") {
    label("y", "Y");
    note("y", ...yExample);
  } else if (a.kind === "vline") {
    label("x", "X");
    note("x", X_EXAMPLE[xKind], X_HELP[xKind]);
  } else if (a.kind === "hspan") {
    label("start", "開始（Y）");
    label("end", "終了（Y）");
    note("start", ...yExample);
    note("end", ...yExample);
  } else if (a.kind === "vspan") {
    label("start", "開始（X）");
    label("end", "終了（X）");
    note("start", X_EXAMPLE[xKind], X_HELP[xKind]);
    note("end", X_EXAMPLE[xKind], X_HELP[xKind]);
  }
};

// 表示の同期（入力中の欄を作り直さない。系列・軸・データの変更のたびに呼ぶ）
export const syncAnnotations = () => {
  const { annotations } = getSettings();
  const xKind = xAxisKind();
  const hasY2 = hasSecondaryAxis();
  for (const item of document.querySelectorAll("#annotationList .annotation-item")) {
    const a = annotations.find((x) => x.id === item.dataset.annId);
    if (a) syncCard(item, a, xKind, hasY2);
  }
};

export const renderAnnotationList = () => {
  const list = document.getElementById("annotationList");
  if (!list) return;
  const { annotations } = getSettings();
  list.replaceChildren(...annotations.map((a, i) => buildCard(a, i)));
  syncAnnotations();
};

const onInput = (event) => {
  const target = event.target;
  if (!target || !target.matches || !target.matches("input, select")) return;
  const item = target.closest(".annotation-item");
  if (!item) return;
  const name = target.id.replace(`annotation-${item.dataset.annId}-`, "");
  const entry = FIELD_KEYS[name];
  if (!entry) return;
  const [key, kind] = entry;
  updateAnnotation(item.dataset.annId, { [key]: kind === "number" ? readNumber(target) : target.value });
};

export const bindAnnotations = () => {
  const list = document.getElementById("annotationList");
  const add = document.getElementById("addAnnotationBtn");
  if (add) add.addEventListener("click", () => addAnnotation());
  if (list) {
    list.addEventListener("input", onInput);
    list.addEventListener("change", onInput);
  }
  renderAnnotationList();
};
