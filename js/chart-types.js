// グラフの種類ごとに「どの設定を使うか」の規則（Python の settings / dataprep と同じ。要件 §2.2: 隠した設定は図に使わない）。
// 純粋な ES module（DOM にも state にも触れない）。画面の出し分けはすべてここを見る。
// py/mplgui/settings.py の BAR_LIKE_TYPES / NO_Y2_TYPES / NO_Y_ERROR_TYPES と揃えること。

export const PLOT_TYPES = ["line", "step", "scatter", "scatterColor", "bar", "barStacked", "barh", "hist"];

const LINE_LIKE = ["line", "step"];
const SCATTER_LIKE = ["scatter", "scatterColor"];
const XY_TYPES = [...LINE_LIKE, ...SCATTER_LIKE]; // 系列ごとに X 列を持つ種類
const CATEGORY_BAR_TYPES = ["bar", "barStacked", "barh"]; // 全系列共通の X列（#xColumn）を使う種類
const NO_Y2_TYPES = ["barh", "barStacked", "hist", "scatterColor"];
const NO_Y_ERROR_TYPES = ["barStacked", "hist"];

export const isLineLike = (type) => LINE_LIKE.includes(type); // 点サイズの自動は 0（点なし）
export const isScatterLike = (type) => SCATTER_LIKE.includes(type); // 点サイズの自動は 24
export const usesSeriesX = (type) => XY_TYPES.includes(type); // 系列ごとの X 列
export const usesGlobalX = (type) => CATEGORY_BAR_TYPES.includes(type); // X列（#xColumn）
export const usesMarker = (type) => XY_TYPES.includes(type); // 点の形・点サイズ
export const usesFill = (type) => XY_TYPES.includes(type); // 塗りつぶし帯
export const usesFits = (type) => XY_TYPES.includes(type); // 近似曲線
export const usesXErrors = (type) => XY_TYPES.includes(type); // X 方向のエラーバー
export const usesYErrors = (type) => !NO_Y_ERROR_TYPES.includes(type); // エラーバー（Y 方向）。使わなければ折りたたみごと隠す
export const usesY2 = (type) => !NO_Y2_TYPES.includes(type); // 第2Y軸
export const usesColorColumn = (type) => type === "scatterColor";
export const usesStep = (type) => type === "step";
export const usesHist = (type) => type === "hist";
