// フォントの取得（日本語: Noto Sans JP の TrueType 版、約5.7 MB。欧文: Arimo / Tinos、各 0.3〜0.5 MB）。
// Cache Storage に保存し、再訪問ではダウンロードしない。
// - 種類ごとに、セッション中の取得は最大1回（失敗しても再試行しない）。
// - Cache Storage が使えない環境では通常の fetch にフォールバックする。
// TrueType 版を使う理由: matplotlib は CFF 形式の OTF を pdf.fonttype=42 で正しく埋め込めない（PDF が壊れる）ため。
// ライセンス: いずれも SIL OFL 1.1（Noto Sans JP: https://cdn.jsdelivr.net/npm/@expo-google-fonts/noto-sans-jp@0.4.4/LICENSE_FONT）
export const FONT_URLS = {
  japanese: "https://cdn.jsdelivr.net/npm/@expo-google-fonts/noto-sans-jp@0.4.4/400Regular/NotoSansJP_400Regular.ttf",
  arimo: "https://cdn.jsdelivr.net/npm/@expo-google-fonts/arimo@0.4.3/400Regular/Arimo_400Regular.ttf",
  tinos: "https://cdn.jsdelivr.net/npm/@expo-google-fonts/tinos@0.4.2/400Regular/Tinos_400Regular.ttf",
};
export const FONT_URL = FONT_URLS.japanese;
// 以前に使っていた約16 MB の OTF。同じキャッシュに残っていれば消す（ベストエフォート）
const LEGACY_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@Sans2.004/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf";
export const FONT_CACHE_NAME = "mplgui-fonts-v1";

// テスト専用の上書き: E2E が addInitScript で window.__MPLGUI_TEST_OVERRIDES__ = {fontStallMs, fontFirstRenderWaitMs} を
// 設定すると、起動時に1回だけ読む（UI には出さない）。
const overrides = (typeof window !== "undefined" && window.__MPLGUI_TEST_OVERRIDES__) || {};
const pick = (value, fallback) => (Number.isFinite(value) && value > 0 ? value : fallback);
// ヘッダが届かない／本文が一定時間まったく進まない場合に取得を失敗扱いにする（総時間の上限は設けない）
export const FONT_STALL_MS = pick(overrides.fontStallMs, 20_000);
// 最初の描画がフォント取得を待つ最大時間。超えたらフォールバックフォントで描画し、取得完了後に1回だけ再描画する
export const FONT_FIRST_RENDER_WAIT_MS = pick(overrides.fontFirstRenderWaitMs, 8_000);

const fontPromises = new Map(); // 種類 → 取得結果の Promise（Uint8Array | null）。一度作ったら使い回す

const openCache = async () => {
  try {
    if (typeof caches === "undefined") return null;
    return await caches.open(FONT_CACHE_NAME);
  } catch (_) {
    return null;
  }
};

// 古い OTF のキャッシュを1回だけ削除する（失敗しても無視する）
let legacyCleaned = false;
const cleanupLegacy = async (cache) => {
  if (!cache || legacyCleaned) return;
  legacyCleaned = true;
  try {
    await cache.delete(LEGACY_FONT_URL);
  } catch (_) {
    // 無視
  }
};

const readCached = async (cache, url) => {
  if (!cache) return null;
  try {
    const hit = await cache.match(url);
    return hit ? new Uint8Array(await hit.arrayBuffer()) : null;
  } catch (_) {
    return null;
  }
};

// Cache Storage に入っているか（ダウンロードを伴わない確認）
export const isFontCached = async (kind = "japanese") => {
  const cache = await openCache();
  if (!cache) return false;
  try {
    return !!(await cache.match(FONT_URLS[kind]));
  } catch (_) {
    return false;
  }
};

// ストリームで読み、進捗(0-100)を onProgress に通知する。content-length が圧縮後サイズのこともあるので 99 で頭打ちにする。
const download = async (url, onProgress) => {
  const controller = new AbortController();
  let stallTimer = null;
  const armStall = () => {
    if (stallTimer) clearTimeout(stallTimer);
    stallTimer = setTimeout(() => controller.abort(), FONT_STALL_MS);
  };
  armStall();
  try {
    return await downloadWith(url, controller.signal, onProgress, armStall);
  } finally {
    if (stallTimer) clearTimeout(stallTimer);
  }
};

const downloadWith = async (url, signal, onProgress, armStall) => {
  const response = await fetch(url, { signal });
  armStall();
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const total = Number(response.headers.get("content-length")) || 0;
  if (!response.body || !response.body.getReader) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    onProgress(100);
    return bytes;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    armStall();
    chunks.push(value);
    received += value.length;
    if (total > 0) onProgress(Math.min(99, Math.floor((received / total) * 100)));
  }
  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  onProgress(100);
  return bytes;
};

// 成功: Uint8Array、失敗: null（onProgress(percent) は 0〜100）。同じ種類の2回目以降は同じ結果を返す。
export const loadFont = (kind = "japanese", onProgress = () => {}) => {
  const url = FONT_URLS[kind];
  if (!url) return Promise.resolve(null);
  if (!fontPromises.has(kind)) {
    fontPromises.set(
      kind,
      (async () => {
        const cache = await openCache();
        if (kind === "japanese") await cleanupLegacy(cache);
        const cached = await readCached(cache, url);
        if (cached) {
          onProgress(100);
          return cached;
        }
        try {
          onProgress(0);
          const bytes = await download(url, onProgress);
          if (cache) {
            try {
              await cache.put(url, new Response(bytes, { headers: { "content-type": "font/ttf" } }));
            } catch (_) {
              // 保存に失敗しても今回のセッションでは使える
            }
          }
          return bytes;
        } catch (_) {
          return null;
        }
      })(),
    );
  }
  return fontPromises.get(kind);
};
