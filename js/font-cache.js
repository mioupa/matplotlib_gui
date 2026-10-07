// 日本語フォント（Noto Sans CJK JP）の取得。Cache Storage に保存し、再訪問ではダウンロードしない。
// - セッション中の取得は最大1回（失敗しても再試行しない）。
// - Cache Storage が使えない環境では通常の fetch にフォールバックする。
export const FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@Sans2.004/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf";
export const FONT_CACHE_NAME = "mplgui-fonts-v1";

let fontPromise = null; // 取得結果（Uint8Array | null）。一度作ったら使い回す

const openCache = async () => {
  try {
    if (typeof caches === "undefined") return null;
    return await caches.open(FONT_CACHE_NAME);
  } catch (_) {
    return null;
  }
};

const readCached = async (cache) => {
  if (!cache) return null;
  try {
    const hit = await cache.match(FONT_URL);
    return hit ? new Uint8Array(await hit.arrayBuffer()) : null;
  } catch (_) {
    return null;
  }
};

// Cache Storage に入っているか（ダウンロードを伴わない確認）
export const isFontCached = async () => {
  const cache = await openCache();
  if (!cache) return false;
  try {
    return !!(await cache.match(FONT_URL));
  } catch (_) {
    return false;
  }
};

// ストリームで読み、進捗(0-100)を onProgress に通知する。content-length が圧縮後サイズのこともあるので 99 で頭打ちにする。
const download = async (onProgress) => {
  const response = await fetch(FONT_URL);
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

// 成功: Uint8Array、失敗: null（onProgress(percent) は 0〜100）。2回目以降は同じ結果を返す。
export const loadFont = (onProgress = () => {}) => {
  if (!fontPromise) {
    fontPromise = (async () => {
      const cache = await openCache();
      const cached = await readCached(cache);
      if (cached) {
        onProgress(100);
        return cached;
      }
      try {
        onProgress(0);
        const bytes = await download(onProgress);
        if (cache) {
          try {
            await cache.put(FONT_URL, new Response(bytes, { headers: { "content-type": "font/otf" } }));
          } catch (_) {
            // 保存に失敗しても今回のセッションでは使える
          }
        }
        return bytes;
      } catch (_) {
        return null;
      }
    })();
  }
  return fontPromise;
};
