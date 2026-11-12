// 計算した列の番号（列 [k]）が変わったときの、列の参照の付け替え。
// 列の参照は、系列の x / y / エラーバーの列 / 帯の列 / 色分けの列と、棒グラフの plot.xColumn（系列1のデータ元）。
// 参照が属するデータ元は、系列の source（"" は先頭のファイル）で決まる。
import { getSettings, removeComputed, setPath, updateComputed, updateSeries } from "./state.js";
import { addNote } from "./bridge.js";
import { fileColumnCount } from "./ui/series.js";

const IDX = /^__idx__(\d+)$/;
const firstFileId = () => (getSettings().load.files[0] ? getSettings().load.files[0].id : "d1");
export const resolveSource = (source) => source || firstFileId();

// そのデータ元の計算した列（カードの順）
export const computedOfSource = (sourceId) => getSettings().computed.filter((c) => resolveSource(c.source) === sourceId);

// 計算した列の番号 k（データ元のファイルの列数 + そのデータ元の計算した列の中での位置）。ファイルが未読込なら null
export const computedIndex = (id) => {
  const c = getSettings().computed.find((x) => x.id === id);
  if (!c) return null;
  const sid = resolveSource(c.source);
  const f = fileColumnCount(sid);
  if (f === undefined) return null;
  return f + computedOfSource(sid).findIndex((x) => x.id === id);
};

export const computedName = (id) => {
  const list = getSettings().computed;
  const i = list.findIndex((x) => x.id === id);
  return i < 0 ? "" : list[i].name.trim() || `計算${i + 1}`;
};

const mapRef = (value, fn) => {
  const m = IDX.exec(value || "");
  if (!m) return value;
  const k = Number(m[1]);
  const next = fn(k);
  return next === null ? "" : next === k ? value : `__idx__${next}`;
};

// データ元 sourceId の列の参照をすべて fn(k) → 新しい k（null は空に戻す）で付け替える。空に戻した系列の番号（1 始まり）の配列を返す。
// 設定の変更は origin "reconcile"（再描画の予約はしない。呼び出し側が行う）
export const remapReferences = (sourceId, fn) => {
  const { series } = getSettings();
  const reset = [];
  series.forEach((s, i) => {
    if (resolveSource(s.source) !== sourceId) return;
    const patch = {};
    let wasReset = false;
    const apply = (value) => {
      const next = mapRef(value, fn);
      if (next !== value && next === "") wasReset = true;
      return next;
    };
    for (const key of ["x", "y", "colorColumn"]) {
      const next = apply(s[key]);
      if (next !== s[key]) patch[key] = next;
    }
    const eb = JSON.parse(JSON.stringify(s.errorBars));
    let ebChanged = false;
    for (const dir of ["y", "x"]) {
      for (const key of ["column", "columnMinus"]) {
        const next = apply(eb[dir][key]);
        if (next !== eb[dir][key]) {
          eb[dir][key] = next;
          ebChanged = true;
        }
      }
    }
    if (ebChanged) patch.errorBars = eb;
    const fill = { ...s.fill };
    let fillChanged = false;
    for (const key of ["lower", "upper"]) {
      const next = apply(fill[key]);
      if (next !== fill[key]) {
        fill[key] = next;
        fillChanged = true;
      }
    }
    if (fillChanged) patch.fill = fill;
    if (Object.keys(patch).length) updateSeries(s.id, patch, "reconcile");
    if (wasReset) reset.push(i + 1);
    if (i === 0) {
      const next = apply(getSettings().plot.xColumn);
      if (next !== getSettings().plot.xColumn) setPath("plot.xColumn", next, "reconcile");
    }
  });
  return reset;
};

const noteReset = (indices, name) => {
  for (const n of indices) addNote(`系列${n}: 計算した列「${name}」を削除したため、その列を使っていた設定を空に戻しました。`);
};

// データ元 S から計算した列（番号 k、S の計算した列は count 個）を取り除いたときの付け替え
const detach = (sourceId, k, count, name) => {
  const f = fileColumnCount(sourceId);
  if (f === undefined) return;
  const reset = remapReferences(sourceId, (i) => (i === k ? null : i > k && i < f + count ? i - 1 : i));
  noteReset(reset, name);
};

// 計算した列を削除する（その列を使っていた設定は空に戻し、後ろの計算した列の参照は詰める）
export const removeComputedColumn = (id) => {
  const k = computedIndex(id);
  const c = getSettings().computed.find((x) => x.id === id);
  if (!c) return;
  if (k !== null) {
    const sid = resolveSource(c.source);
    detach(sid, k, computedOfSource(sid).length, computedName(id));
  }
  removeComputed(id);
};

// 計算した列のデータ元を変える（元のデータ元からは削除と同じ付け替え、新しいデータ元では後ろの参照を +1）
export const changeComputedSource = (id, newSource) => {
  const c = getSettings().computed.find((x) => x.id === id);
  if (!c || resolveSource(c.source) === resolveSource(newSource)) return;
  const oldSid = resolveSource(c.source);
  const k = computedIndex(id);
  if (k !== null) detach(oldSid, k, computedOfSource(oldSid).length, computedName(id));
  updateComputed(id, { source: newSource });
  const newK = computedIndex(id);
  if (newK !== null) remapReferences(resolveSource(newSource), (i) => (i >= newK ? i + 1 : i));
};

// 読み直しでファイルの列数が oldF → newF になったとき、計算した列を指す参照（[oldF, oldF + 個数)）を同じだけずらす
export const shiftForFileColumnChange = (sourceId, oldF, newF) => {
  const count = computedOfSource(sourceId).length;
  if (count === 0) return;
  remapReferences(sourceId, (i) => (i >= oldF && i < oldF + count ? i + (newF - oldF) : i));
};

// ファイルを外した・置き換えたとき、そのファイルをデータ元にしていた計算した列を先頭のファイルに戻す。
// isGone(source, positionOfSource) が真の計算した列が対象。注意の文の配列を返す
export const releaseComputedSources = (isGone) => {
  const notes = [];
  getSettings().computed.forEach((c, i) => {
    if (!isGone(c.source)) return;
    updateComputed(c.id, { source: "" }, "reconcile");
    notes.push(`計算した列${i + 1}: データ元のファイルを外したため、データ元を先頭のファイルに戻しました。`);
  });
  return notes;
};
