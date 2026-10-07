"""外部 CDN の URL がすべてバージョン固定であること（@main / @latest / バージョン無し / Google Fonts css2 を禁止）。"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
URL_RE = re.compile(r"https?://[^\s\"'<>)`]+")

# (ホスト, 固定済みとみなすパスのパターン)
PINNED = [
    ("pyscript.net", re.compile(r"^/releases/\d{4}\.\d+\.\d+/")),
    ("cdn.jsdelivr.net", re.compile(r"^/npm/(@[\w.-]+/)?[\w.-]+@\d+\.\d+\.\d+(?:[-+.\w]*)?/")),
    ("cdn.jsdelivr.net", re.compile(r"^/gh/[\w.-]+/[\w.-]+@(?!main\b|master\b|latest\b)[\w.-]*\d[\w.-]*/")),
]
NAMESPACE_HOSTS = {"www.w3.org"}  # SVG などの名前空間 URI（取得されない）


def scan_files():
    files = [REPO / "index.html"]
    for sub, pattern in (("js", "*.js"), ("css", "*.css"), ("py", "*.py")):
        files += sorted((REPO / sub).rglob(pattern))
    return files


def check_url(url: str) -> str | None:
    """問題があれば理由を返す。"""
    m = re.match(r"https?://([^/]+)(/.*)?$", url)
    host, path = m.group(1), m.group(2) or "/"
    if host in NAMESPACE_HOSTS:
        return None
    if "fonts.googleapis.com" in host or "fonts.gstatic.com" in host:
        return "Google Fonts は固定できない"
    for pinned_host, pat in PINNED:
        if host == pinned_host and pat.match(path):
            return None
    return "バージョン固定されていない（または未許可のホスト）"


def test_all_urls_are_pinned():
    problems = []
    seen = 0
    for f in scan_files():
        for url in URL_RE.findall(f.read_text(encoding="utf-8")):
            seen += 1
            reason = check_url(url.rstrip(".,;"))
            if reason:
                problems.append(f"{f.relative_to(REPO)}: {url} ({reason})")
    assert seen > 0
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@main/Sans/x.otf",
        "https://cdn.jsdelivr.net/npm/@fontsource/noto-sans-jp@latest/400.css",
        "https://cdn.jsdelivr.net/npm/@fontsource/noto-sans-jp/400.css",
        "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk/Sans/x.otf",
        "https://fonts.googleapis.com/css2?family=Noto+Sans+JP",
        "https://pyscript.net/latest/core.js",
        "https://example.com/x.js",
    ],
)
def test_checker_rejects_unpinned(url):
    assert check_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@Sans2.004/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf",
        "https://cdn.jsdelivr.net/npm/@fontsource/noto-sans-jp@5.3.0/400.css",
        "https://pyscript.net/releases/2026.7.3/core.js",
    ],
)
def test_checker_accepts_pinned(url):
    assert check_url(url) is None
