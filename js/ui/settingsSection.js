// 保存区分の「設定」: 設定の保存（.json）・読込・初期設定に戻す（R1）と、前回の設定の自動保存・復元。
// 形・検査・補完は settings-io.js（純粋）、state の入れ替えとデータ元・列の合わせは bridge.js が行う。
// 控えは localStorage にだけ書く（外部には送らない）。localStorage が使えなくても動く。
import { getSettings, subscribe } from "../state.js";
import { DEFAULT_SETTINGS } from "../defaults.js";
import { MAX_SETTINGS_BYTES, parseSettingsFile, serializeSettings, settingsFilename } from "../settings-io.js";
import { applyParsedSettings, getFilesInfo, getPendingColumnCounts } from "../bridge.js";
import { setStatus } from "./notify.js";

const byId = (id) => document.getElementById(id);
const LAST_KEY = "mplgui.lastSettings";
const AUTOSAVE_DELAY_MS = 500;
const RESET_CONFIRM = "すべての設定を初期状態に戻します。読み込んだデータはそのままです。よろしいですか？";
const RESTORED_MESSAGE = "前回の設定を復元しました。既定に戻すには「初期設定に戻す」を押してください。";
const RESTORE_FAILED_MESSAGE = "前回の設定を読めなかったため、初期設定で始めます。";

let appliedCount = 0;
const markApplied = () => {
  appliedCount += 1;
  document.documentElement.dataset.settingsApplied = String(appliedCount); // E2E 用: 設定を入れ替えた回数（復元・読込・初期設定に戻す）
};

// ---- 保存 ----
const download = (filename, text) => {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const saveSettingsFile = () => {
  const wrapper = serializeSettings(getSettings(), getFilesInfo(), { names: true });
  const filename = settingsFilename(getSettings().save.filename);
  download(filename, `${JSON.stringify(wrapper, null, 2)}\n`);
  setStatus(`設定を保存しました: ${filename}`, "ok");
};

// ---- 読込 ----
const loadSettingsFile = async (file) => {
  try {
    if (file.size > MAX_SETTINGS_BYTES) {
      setStatus("設定ファイルが大きすぎます（1 MB まで）。", "error");
      return;
    }
    const parsed = parseSettingsFile(await file.text(), { size: file.size });
    applyParsedSettings(parsed);
    markApplied();
  } catch (err) {
    // 形の検査の失敗は、何も変えずにエラーを出す（field は「設定ファイル」）
    setStatus(err && err.message ? err.message : "設定ファイルを読み込めませんでした。", "error");
  }
};

const resetSettings = () => {
  if (!window.confirm(RESET_CONFIRM)) return;
  applyParsedSettings({ settings: JSON.parse(JSON.stringify(DEFAULT_SETTINGS)), files: [] });
  markApplied();
};

// ---- 前回の設定の自動保存と復元（localStorage）----
const writeLast = () => {
  try {
    const loaded = getFilesInfo();
    const info = loaded.length > 0 ? loaded : getPendingColumnCounts().map((columns) => ({ columns }));
    const wrapper = serializeSettings(getSettings(), info, { names: false }); // ファイル名は控えない
    window.localStorage.setItem(LAST_KEY, JSON.stringify(wrapper));
  } catch (_) {
    // 控えられなくても動作には影響しない
  }
};

// ページを開いたとき（画面を描く前）に呼ぶ。何も控えが無い・localStorage が使えないときは何もしない。戻したら true
export const restoreLastSettings = () => {
  let text;
  try {
    text = window.localStorage.getItem(LAST_KEY);
  } catch (_) {
    return false;
  }
  if (text === null || text === undefined) return false;
  let parsed;
  try {
    parsed = parseSettingsFile(text, { size: text.length });
  } catch (_) {
    try {
      window.localStorage.removeItem(LAST_KEY);
    } catch (__) {
      // 消せなくても続ける
    }
    setStatus(RESTORE_FAILED_MESSAGE, "warning");
    return false;
  }
  applyParsedSettings(parsed);
  markApplied();
  setStatus(RESTORED_MESSAGE, "ok");
  return true;
};

export const bindSettingsSection = () => {
  document.documentElement.dataset.settingsApplied = String(appliedCount);
  byId("saveSettingsBtn")?.addEventListener("click", saveSettingsFile);
  byId("resetSettingsBtn")?.addEventListener("click", resetSettings);
  const input = byId("loadSettingsInput");
  byId("loadSettingsBtn")?.addEventListener("click", () => input?.click());
  input?.addEventListener("change", () => {
    const file = input.files && input.files[0];
    input.value = ""; // 同じファイルをもう一度選んでも change が起きるように
    if (file) loadSettingsFile(file);
  });
  // 設定が変わるたびに 0.5 秒後に控える。ページを離れるときは、変更があれば即座に控える
  let timer = null;
  let dirty = false;
  subscribe(() => {
    dirty = true;
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      timer = null;
      writeLast();
    }, AUTOSAVE_DELAY_MS);
  });
  window.addEventListener("pagehide", () => {
    if (!dirty) return;
    if (timer) window.clearTimeout(timer);
    timer = null;
    writeLast();
  });
};
