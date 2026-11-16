// 設定の保存・読込（R1）の純粋な部分。DOM にも state にも触れない。
//   serializeSettings: 設定オブジェクト → 保存用のラッパー（データ元の id は位置の番号にそろえる）
//   parseSettingsFile: JSON 文字列 → 検査・移行・既定値での補完をした設定
//   mapPositionalSources: 位置の番号（dN）のデータ元を、今読み込んでいるファイルの id に付け替える
//   settingsFilename: 設定ファイルの名前（保存ファイル名の規則は Python の formats.build_filename と同じ）
import { DEFAULT_ANNOTATION, DEFAULT_COMPUTED, DEFAULT_FIT, DEFAULT_SERIES, DEFAULT_SETTINGS, SCHEMA_VERSION } from "./defaults.js";

export const SETTINGS_FORMAT = "matplotlib-gui-settings";
export const MAX_SETTINGS_BYTES = 1024 * 1024; // 設定ファイルの上限（1 MB）

const clone = (value) => JSON.parse(JSON.stringify(value));
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

// 配列の要素の既定値（キーは設定のパス）
const DEFAULT_PANEL = { title: "", xLabel: "", yLabel: "", y2Label: "" };
const DEFAULT_FILE = { id: "", name: "", sheet: "" };
const ARRAY_ELEMENTS = {
  series: DEFAULT_SERIES,
  annotations: DEFAULT_ANNOTATION,
  fits: DEFAULT_FIT,
  computed: DEFAULT_COMPUTED,
  "plot.panels": DEFAULT_PANEL,
  "load.files": DEFAULT_FILE,
};
const ID_PREFIX = { series: "s", annotations: "a", fits: "f", computed: "c" };

// ---- 保存 ----

const positionalMap = (files) => new Map(files.map((f, i) => [f.id, `d${i + 1}`]));

// filesInfo: 読み込み中のファイルごとの {name, sheet, columns}（load.files と同じ並び。columns は不明なら null）
// names: false なら、ファイル名・シート名を含めない（localStorage 用）
export const serializeSettings = (settings, filesInfo = [], { names = true, savedAt = new Date().toISOString() } = {}) => {
  const copy = clone(settings);
  const map = positionalMap(copy.load.files);
  const remap = (source) => (source === "" ? "" : map.get(source) ?? source);
  copy.load.files = names ? copy.load.files.map((f, i) => ({ ...f, id: `d${i + 1}` })) : [];
  for (const s of copy.series) s.source = remap(s.source);
  for (const c of copy.computed) c.source = remap(c.source);
  const files = (Array.isArray(filesInfo) ? filesInfo : []).map((f) => {
    const info = f || {};
    const columns = Number.isInteger(info.columns) && info.columns >= 0 ? info.columns : null;
    return names ? { name: String(info.name ?? ""), sheet: String(info.sheet ?? ""), columns } : { columns };
  });
  return { format: SETTINGS_FORMAT, savedAt, files, settings: copy };
};

// ---- 読込 ----

export class SettingsFileError extends Error {}

const fail = (message) => {
  throw new SettingsFileError(message);
};

// Python の settings.migrate_settings と同じ規則（引数は変更しない）。version が無ければ現在のバージョン扱い
const migrate = (raw) => {
  const out = clone(raw);
  const version = "version" in raw ? raw.version : SCHEMA_VERSION;
  if (version === 1) {
    if (!isObject(out.save)) out.save = {};
    if (!("dpi" in out.save)) out.save.dpi = 120;
  }
  if (version === 1 || version === 2) {
    if (!isObject(out.load)) out.load = {};
    if (!("parseDates" in out.load)) out.load.parseDates = false;
  }
  out.version = SCHEMA_VERSION;
  return out;
};

// 既定値の形に合わせて補う。知らないキーは捨てる。形（オブジェクト・配列・値）が違うものは既定値にする。
// 値そのものの正しさは検査しない（描画のときに Python が日本語のエラーにする）。配列は path の要素の既定値で要素ごとに補う
const fillFrom = (def, val, path) => {
  if (Array.isArray(def)) {
    const element = ARRAY_ELEMENTS[path];
    if (!Array.isArray(val) || !element) return clone(def);
    return val.map((item) => {
      const filled = fillFrom(element, item, `${path}[]`);
      // id が無い要素は、既定値の id（s1 など）を借りずに空にする（あとで assignIds が新しい id を振る）
      if ("id" in filled && !(isObject(item) && typeof item.id === "string" && item.id !== "")) filled.id = "";
      return filled;
    });
  }
  if (isObject(def)) {
    if (!isObject(val)) return clone(def);
    const out = {};
    for (const key of Object.keys(def)) {
      const childPath = path === "" ? key : `${path}.${key}`;
      out[key] = key in val ? fillFrom(def[key], val[key], childPath) : clone(def[key]);
    }
    return out;
  }
  if (val === undefined || isObject(val) || Array.isArray(val)) return def;
  return val;
};

const numericSuffix = (id, prefix) => {
  const m = new RegExp(`^${prefix}(\\d+)$`).exec(typeof id === "string" ? id : "");
  return m ? Number(m[1]) : 0;
};

export const maxIdNumber = (items, prefix) => items.reduce((max, item) => Math.max(max, numericSuffix(item && item.id, prefix)), 0);

// id が「prefix + 数字」の形でない・重複している要素に、新しい id（prefix + 連番。既存の最大の番号から続ける）を振る。
// id は画面の要素の id と HTML にそのまま入るので、形を限る（手で書いた設定ファイルの値で HTML を壊させない）。
// 振り直した id の対応（最初に出てきた元の id → 新しい id）を返す（近似曲線の系列の参照を直すのに使う）
const assignIds = (items, prefix) => {
  let max = maxIdNumber(items, prefix);
  const seen = new Set();
  const pattern = new RegExp(`^${prefix}\\d+$`);
  const renamed = new Map();
  for (const item of items) {
    if (typeof item.id !== "string" || !pattern.test(item.id) || seen.has(item.id)) {
      const old = item.id;
      max += 1;
      item.id = `${prefix}${max}`;
      if (typeof old === "string" && old !== "" && !pattern.test(old) && !renamed.has(old)) renamed.set(old, item.id);
    }
    seen.add(item.id);
  }
  return renamed;
};

const normalizeSettings = (raw) => {
  const migrated = migrate(raw);
  const out = {};
  for (const key of Object.keys(DEFAULT_SETTINGS)) {
    out[key] = key === "version" ? SCHEMA_VERSION : fillFrom(DEFAULT_SETTINGS[key], migrated[key], key);
  }
  if (out.series.length === 0) out.series = [clone(DEFAULT_SERIES)];
  const renamed = {};
  for (const [key, prefix] of Object.entries(ID_PREFIX)) renamed[key] = assignIds(out[key], prefix);
  // 形の違う系列の id を振り直したら、その系列を指す近似曲線も新しい id にする
  for (const f of out.fits) if (renamed.series.has(f.series)) f.series = renamed.series.get(f.series);
  return out;
};

const looksLikeSettings = (obj) =>
  ["plot", "axes", "load", "save"].some((k) => isObject(obj[k])) || ["series", "annotations", "fits", "computed"].some((k) => Array.isArray(obj[k]));

// text: ファイルの内容。size: ファイルの大きさ（バイト。省略時は文字数）。
// 戻り値: {settings, files: [{name, sheet, columns}]}。失敗は SettingsFileError（message は日本語。何も変えない段階の失敗）
export const parseSettingsFile = (text, { size } = {}) => {
  const bytes = size === undefined ? String(text).length : size;
  if (bytes > MAX_SETTINGS_BYTES) fail("設定ファイルが大きすぎます（1 MB まで）。");
  let data;
  try {
    data = JSON.parse(text);
  } catch (_) {
    fail("設定ファイルを読み込めませんでした: JSON の形式ではありません。");
  }
  const NOT_SETTINGS = "設定ファイルではありません。このアプリの「設定を保存（.json）」で保存したファイルを選んでください。";
  if (!isObject(data)) fail(NOT_SETTINGS);
  let raw = data;
  let filesRaw = [];
  if ("settings" in data || "format" in data) {
    if (("format" in data && data.format !== SETTINGS_FORMAT) || !isObject(data.settings)) fail(NOT_SETTINGS);
    raw = data.settings;
    if (Array.isArray(data.files)) filesRaw = data.files;
  }
  if (!looksLikeSettings(raw)) fail(NOT_SETTINGS);
  if ("version" in raw) {
    const v = raw.version;
    if (typeof v === "number" && Number.isInteger(v) && v > SCHEMA_VERSION) fail(`この設定ファイルは新しい版のアプリで作られたため、読み込めません（version ${v}）。`);
    if (!(typeof v === "number" && Number.isInteger(v) && v >= 1 && v <= SCHEMA_VERSION)) {
      fail(`設定ファイルのバージョン（${typeof v === "string" ? v : JSON.stringify(v)}）に対応していません。`);
    }
  }
  const files = filesRaw.map((f) => {
    const info = isObject(f) ? f : {};
    return {
      name: typeof info.name === "string" ? info.name : "",
      sheet: typeof info.sheet === "string" ? info.sheet : "",
      columns: Number.isInteger(info.columns) && info.columns >= 0 ? info.columns : null,
    };
  });
  return { settings: normalizeSettings(raw), files };
};

// ---- データ元の対応（位置で合わせる）----

const POSITIONAL = /^d(\d+)$/;

// 系列を別のデータ元に付け替えたときに空に戻す項目（ui/series.js の onSourceChange と同じ）
export const clearedColumnsPatch = (series) => {
  const errorBars = clone(series.errorBars);
  for (const dir of ["y", "x"]) Object.assign(errorBars[dir], { column: "", columnMinus: "" });
  return { source: "", x: "", y: "", colorColumn: "", errorBars, fill: { ...series.fill, lower: "", upper: "" } };
};

// settings（コピーを返す）の系列・計算した列のデータ元 dN を、fileIds（今のファイルの id の並び）の N 番目に付け替える。
// fileIds が空なら何もしない（読み込むまで dN のまま残す）。N 番目が無いものはデータ1に戻し、注意の文を返す
export const mapPositionalSources = (settings, fileIds) => {
  const out = clone(settings);
  const notes = [];
  if (fileIds.length === 0) return { settings: out, notes };
  const resolve = (source) => {
    const m = POSITIONAL.exec(source);
    return { id: m && Number(m[1]) >= 1 && Number(m[1]) <= fileIds.length ? fileIds[Number(m[1]) - 1] : "" };
  };
  const missingName = (source) => (POSITIONAL.test(source) ? `データ${Number(POSITIONAL.exec(source)[1])}` : "データ元");
  out.series.forEach((s, i) => {
    const r = resolve(s.source);
    if (r.id === "" && s.source !== "") {
      const was = s.source;
      Object.assign(s, clearedColumnsPatch(s));
      if (i === 0) out.plot.xColumn = "";
      notes.push(`系列${i + 1}: 設定の${missingName(was)}に当たるファイルが無いため、データ元をデータ1に戻し、列を自動に戻しました。`);
    } else {
      s.source = r.id;
    }
  });
  out.computed.forEach((c, i) => {
    const was = c.source;
    c.source = resolve(was).id;
    if (c.source === "" && was !== "") {
      notes.push(`計算した列${i + 1}: 設定の${missingName(was)}に当たるファイルが無いため、データ元を先頭のファイルに戻しました。`);
    }
  });
  return { settings: out, notes };
};

// ---- ファイル名 ----

const INVALID_FILENAME_CHARS = /[\\/:*?"<>|\x00-\x1f]/g;
// Python の str.strip() が取り除く空白（JS の trim とは少し違う）
const PY_SPACE = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const pyStrip = (s) => s.replace(new RegExp(`^[${PY_SPACE}]+|[${PY_SPACE}]+$`, "g"), "");

// 保存ファイル名（入力欄の値）→ 設定ファイルの名前（<base>_settings.json）。base は formats.build_filename と同じ規則
export const settingsFilename = (saveFilename) => {
  const raw = pyStrip(String(saveFilename ?? "")).replace(INVALID_FILENAME_CHARS, "_");
  let base = "plot";
  if (raw) {
    base = raw.replace(/\.+$/, "");
    if (base.includes(".")) base = base.slice(0, base.lastIndexOf("."));
    base = pyStrip(base) || "plot";
  }
  return `${base}_settings.json`;
};
