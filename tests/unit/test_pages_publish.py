"""GitHub Pages (Jekyll) で公開されるファイルに、index.html / pyscript.toml が参照するものが全て含まれるか。

ブラウザは使わない。Jekyll の既定の除外規則（"_" "." "#" "~" 始まりは、include に無ければ配信しない）と
_config.yml の exclude / include を再現して判定する。
"""
import fnmatch
import tomllib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]


class _RefParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []  # (tag, attr, value)

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src", "config") and value:
                self.refs.append((tag, name, value))


def _local_path(ref: str) -> str | None:
    """ローカルファイルへの参照なら、リポジトリルートからの相対パスを返す。"""
    parsed = urlparse(ref)
    if parsed.scheme or parsed.netloc or ref.startswith(("//", "#", "data:")):
        return None
    path = parsed.path
    if not path:
        return None
    return path.removeprefix("./").lstrip("/")


def _matches(pattern: str, rel: str) -> bool:
    pattern = pattern.rstrip("/")
    parts = rel.split("/")
    candidates = ["/".join(parts[: i + 1]) for i in range(len(parts))]  # 親ディレクトリを含む
    return any(fnmatch.fnmatch(c, pattern) or fnmatch.fnmatch(c.rsplit("/", 1)[-1], pattern) for c in candidates)


def _is_published(rel: str, config: dict) -> bool:
    includes = config.get("include", []) or []
    excludes = config.get("exclude", []) or []
    if any(_matches(p, rel) for p in excludes):
        return False
    for part_end in range(1, len(rel.split("/")) + 1):
        sub = "/".join(rel.split("/")[:part_end])
        name = sub.rsplit("/", 1)[-1]
        if name.startswith(("_", ".", "#", "~")) and not any(
            fnmatch.fnmatch(sub, p) or fnmatch.fnmatch(name, p) for p in includes
        ):
            return False
    return True


@pytest.fixture(scope="module")
def jekyll_config():
    return yaml.safe_load((REPO / "_config.yml").read_text(encoding="utf-8")) or {}


def _assert_published(rel: str, config: dict, origin: str):
    assert (REPO / rel).is_file(), f"{origin}: {rel} が存在しない"
    assert _is_published(rel, config), f"{origin}: {rel} は Jekyll では公開されない（_config.yml の include/exclude を確認）"


def test_index_html_references_are_published(jekyll_config):
    parser = _RefParser()
    parser.feed((REPO / "index.html").read_text(encoding="utf-8"))
    local = [(t, a, p) for t, a, v in parser.refs if (p := _local_path(v))]
    assert any(p == "css/style.css" for _, _, p in local)
    assert any(p == "js/main.js" for _, _, p in local)
    assert any(p == "py/main.py" for _, _, p in local)
    for tag, attr, rel in local:
        _assert_published(rel, jekyll_config, f"index.html <{tag} {attr}>")


def test_pyscript_toml_files_are_published(jekyll_config):
    cfg = tomllib.loads((REPO / "pyscript.toml").read_text(encoding="utf-8"))
    files = cfg.get("files", {})
    assert files, "[files] が定義されていない"
    for src in files:
        rel = _local_path(src)
        assert rel, f"[files] の取得元がローカルパスではない: {src}"
        _assert_published(rel, jekyll_config, "pyscript.toml [files]")
    destinations = [d for d in files.values() if d]
    assert len(destinations) == len(set(destinations)), "[files] の配置先が重複している"


def test_every_mplgui_module_is_listed_in_pyscript_toml():
    cfg = tomllib.loads((REPO / "pyscript.toml").read_text(encoding="utf-8"))
    listed = {_local_path(src) for src in cfg.get("files", {})}
    on_disk = {p.relative_to(REPO).as_posix() for p in (REPO / "py" / "mplgui").glob("*.py")}
    assert on_disk <= listed, f"pyscript.toml [files] に無いモジュール: {sorted(on_disk - listed)}"


def test_dev_files_are_not_published(jekyll_config):
    for rel in ("tests/e2e/test_smoke.py", "pyproject.toml", "uv.lock", ".python-version", "docs/REQUIREMENTS.md", "AGENTS.md"):
        assert not _is_published(rel, jekyll_config), f"{rel} が公開されてしまう"


def test_publish_rules_sanity(jekyll_config):
    assert _is_published("py/mplgui/__init__.py", jekyll_config)
    assert not _is_published("py/mplgui/__init__.py", {})  # include が無ければ Jekyll は配信しない
    assert not _is_published("_hidden/a.js", jekyll_config)
