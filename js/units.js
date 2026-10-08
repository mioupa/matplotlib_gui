// 図サイズの単位の換算。純粋な ES module（DOM に触れない）。
export const UNITS = ["in", "cm", "mm"];
export const UNIT_NAMES = { in: "inch", cm: "cm", mm: "mm" }; // 画面に出す名前
export const UNIT_STEP = { in: 0.1, cm: 0.1, mm: 1 };

const MM_PER_UNIT = { in: 25.4, cm: 10, mm: 1 };
const DECIMALS = { in: 3, cm: 2, mm: 1 }; // 換算後の丸め（小数の桁数）。末尾の 0 は数値にすると消える

// 長さを from の単位から to の単位へ換算する。数値でない値（空欄・不正な入力）はそのまま返す。
export const convertLength = (value, from, to) => {
  if (typeof value !== "number" || !Number.isFinite(value) || from === to) return value;
  if (!(from in MM_PER_UNIT) || !(to in MM_PER_UNIT)) return value;
  return Number(((value * MM_PER_UNIT[from]) / MM_PER_UNIT[to]).toFixed(DECIMALS[to]));
};
