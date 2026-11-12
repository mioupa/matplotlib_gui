// 軸・目盛区分: 目盛の入力欄・日時の範囲・枠線の表示と無効の切り替え（設定の値は消さない。隠した欄の値は Python も使わない: 要件 §2.2）。
// 軸の種類（number / log / datetime / category）は Python（dataprep）と同じ規則で series.js が決めて渡す。
import { getSettings, hasSecondaryAxis } from "../state.js";

const byId = (id) => document.getElementById(id);

const STEP_HELP = {
  number: "空欄は自動です。",
  log: "対数軸では使えません（主目盛は 10^n ごと）。",
  datetime: "整数で、単位の何個ごとかを指定します。",
  category: "何個おきに目盛を付けるか（整数）を指定します。",
};

const setHidden = (id, hidden) => {
  const el = byId(id);
  if (el) el.hidden = hidden;
};

// kind: その軸の種類。prefix: x / y / y2
const syncOneAxis = (prefix, kind, axis) => {
  const step = byId(`${prefix}MajorStep`);
  if (step) step.disabled = kind === "log";
  const help = byId(`${prefix}MajorStepHelp`);
  if (help) help.textContent = STEP_HELP[kind] || STEP_HELP.number;
  setHidden(`${prefix}MinorGroup`, kind === "category");
  setHidden(`${prefix}MinorDivisionsWrap`, !(axis.minorTicks === "on" && kind !== "log" && kind !== "category"));
  const formatVisible = kind === "number" || kind === "log";
  setHidden(`${prefix}TickFormatGroup`, !formatVisible);
  setHidden(`${prefix}TickDecimalsWrap`, !(formatVisible && (axis.tickFormat === "fixed" || axis.tickFormat === "sci")));
};

// xKind / yKind: X・Y 軸の種類（series.js が列の種類とグラフの種類から決める。yKind は横棒の縦軸のカテゴリ用）
export const syncAxisTicks = (xKind, yKind) => {
  const { axes } = getSettings();
  const kind = xKind || (axes.x.scale === "log" ? "log" : "number");
  syncOneAxis("x", kind, axes.x);
  syncOneAxis("y", yKind || (axes.y.scale === "log" ? "log" : "number"), axes.y);
  syncOneAxis("y2", axes.y2.scale === "log" ? "log" : "number", axes.y2);
  setHidden("xMajorStepUnitWrap", kind !== "datetime");
  setHidden("xRangeGroup", kind === "datetime");
  setHidden("xDateRangeGroup", kind !== "datetime");
  const hasY2 = hasSecondaryAxis();
  const right = byId("spineRight");
  if (right) right.disabled = hasY2;
  setHidden("spineRightHelp", !hasY2);
};
