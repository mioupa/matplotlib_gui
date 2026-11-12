"""スクリプトの実行と、Figure → 画像バイト列（DOM / js には依存しない）。

GUI の描画も、ユーザーが編集したコードの実行も、ここの run_script() 1本を通る。
GUI の設定を、実行後の Figure に上書き適用することはしない（A8）。
"""
from __future__ import annotations

import base64
import builtins
import contextlib
import io
import linecache
import os
import traceback
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.layout_engine import PlaceHolderLayoutEngine

from .errors import UserError
from .formats import DEFAULT_SAVE_DPI, FORMATS, build_filename, check_raster_size, savefig_kwargs, savefig_rc  # noqa: F401  (build_filename は runner からも使えるようにする)

SCRIPT_FILENAME = "plot.py"
CODE_FIELD = "Pythonコード"
NO_FIGURE_MESSAGE = "図が作られませんでした。fig, ax = plt.subplots() などで図を作ってください。"

# plt.show() は Agg バックエンドでは何も表示できず、この警告を出す。実行中はこれだけを無視する。
_SHOW_WARNING = r"FigureCanvasAgg is non-interactive, and thus cannot be shown"


# ---------------------------------------------------------------- image output


def drop_placeholder_layout_engine(fig) -> None:
    """tight_layout() 後に残る PlaceHolderLayoutEngine を外す（savefig が余分に全体を再描画するため）。

    実際のエンジン（constrained / tight / compressed）は出力が変わるので外さない。
    """
    get = getattr(fig, "get_layout_engine", None)
    if get is not None and isinstance(get(), PlaceHolderLayoutEngine):
        fig.set_layout_engine(None)


def figure_to_bytes(
    fig, file_format: str, transparent: bool = False, dpi: int = DEFAULT_SAVE_DPI, svg_text: str = "path"
) -> tuple[bytes, str, str]:
    """Figure を指定形式のバイト列にする。戻り値は (bytes, mime, 拡張子)。

    保存形式ごとの rcParams（PDF の fonttype、SVG の文字）は savefig の間だけ適用する（生成スクリプトと同じ値）。
    PNG / JPG は、画素数が大きすぎるときは書き出す前に UserError にする。
    """
    fmt = (file_format or "").lower()
    if fmt not in FORMATS:
        raise UserError("「保存形式」の値が不正です。png / jpg / svg / pdf から選んでください。", field="保存形式")
    if transparent and fmt not in {"png", "svg"}:
        raise UserError("背景透過を有効にした場合、保存形式はpngまたはsvgを選択してください。", field="保存形式")
    save_format, mime, ext = FORMATS[fmt]

    if save_format in {"png", "jpeg"}:
        width_in, height_in = fig.get_size_inches()
        check_raster_size(float(width_in), float(height_in), dpi)

    buffer = io.BytesIO()
    drop_placeholder_layout_engine(fig)
    try:
        with matplotlib.rc_context(savefig_rc(fmt, svg_text)):
            fig.savefig(buffer, format=save_format, **savefig_kwargs(fmt, transparent, dpi))
    except (ValueError, OverflowError, MemoryError) as exc:
        if is_mathtext_error(exc):
            raise MathtextError(MATHTEXT_HINT, field="数式", detail=f"{type(exc).__name__}: {exc}") from exc
        raise UserError(
            "画像を書き出せませんでした。図幅・図高さを小さくするか、保存形式を変えてください。",
            field="図幅",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
    return buffer.getvalue(), mime, ext


def figure_to_data_uri(
    fig, file_format: str, transparent: bool = False, dpi: int = DEFAULT_SAVE_DPI, svg_text: str = "path"
) -> tuple[str, str]:
    data, mime, ext = figure_to_bytes(fig, file_format, transparent, dpi, svg_text)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", ext


def _offset_text(axis) -> str:
    """軸の端の ×10^n（オフセット）の文字列。目盛ラベルを作った後（get_ticklabels の後）の値。"""
    get_offset = getattr(axis.get_major_formatter(), "get_offset", None)
    return str(get_offset()) if get_offset is not None else ""


_AUX_LINE_LABELS = {"_errorbar", "_fit"}


def _is_fit_label(label: str) -> bool:
    return label == "_fit" or "$R^2$ = " in label


def _is_fit_text(text: str) -> bool:
    return "y = " in text and "$R^2$ = " in text


def _transform_kind(artist, ax) -> tuple[bool, bool]:
    """(X が データ座標か, Y が データ座標か)。axhline / axvline / axhspan / axvspan は片方だけデータ座標。"""
    return tuple(bool(v) for v in artist.get_transform().contains_branch_seperately(ax.transData))


def _is_colorbar_axes(ax) -> bool:
    """カラーバーの Axes か（fig.colorbar が作る Axes は `_colorbar` を持つ）。"""
    return getattr(ax, "_colorbar", None) is not None


def _colorbar_summary(fig):
    """カラーバー（あれば1本目）の {label, cmap, vmin, vmax}。無ければ None。"""
    for ax in fig.axes:
        cb = getattr(ax, "_colorbar", None)
        if cb is not None:
            return {"label": cb.ax.get_ylabel(), "cmap": cb.cmap.name, "vmin": float(cb.norm.vmin), "vmax": float(cb.norm.vmax)}
    return None


def _bar_summary(ax) -> dict:
    """棒（BarContainer）の要約: 向き別の棒の本数、容器ごとの棒の数、段になっている容器（棒の下端が 0 でないもの）の数。"""
    vertical = horizontal = stacked = 0
    containers = []
    for c in ax.containers:
        if type(c).__name__ != "BarContainer":
            continue
        horizontal_bars = getattr(c, "orientation", "vertical") == "horizontal"
        patches = list(c.patches)
        containers.append(len(patches))
        if horizontal_bars:
            horizontal += len(patches)
            stacked += any(abs(p.get_x()) > 1e-12 for p in patches)
        else:
            vertical += len(patches)
            stacked += any(abs(p.get_y()) > 1e-12 for p in patches)
    return {"vertical": vertical, "horizontal": horizontal, "containers": containers, "stacked": int(stacked)}


def _series_lines(ax) -> list:
    """系列の線（エラーバー・近似曲線・注釈の線を除く）。"""
    return [
        ln for ln in ax.lines
        if ln.get_label() not in _AUX_LINE_LABELS and not _is_fit_label(ln.get_label()) and _transform_kind(ln, ax) == (True, True)
    ]


def _style_summary(ax) -> dict:
    """点の形・不透明度・塗りつぶし帯・注釈・近似曲線の要約（既存のキーの値は変えない）。"""
    lines = ax.lines
    hlines = vlines = 0
    for ln in lines:
        kind = _transform_kind(ln, ax)
        hlines += kind == (False, True)
        vlines += kind == (True, False)
    hspans = vspans = 0
    for patch in ax.patches:
        kind = _transform_kind(patch, ax)
        hspans += kind == (False, True)
        vspans += kind == (True, False)
    fit_texts = sum(1 for t in ax.texts if _is_fit_text(t.get_text()))
    series_lines = _series_lines(ax)
    scatters = [c for c in ax.collections if type(c).__name__ == "PathCollection" and not c.get_label().startswith("_")]
    return {
        "drawstyles": [ln.get_drawstyle() for ln in series_lines],
        "bars": _bar_summary(ax),
        "bands": sum(1 for c in ax.collections if c.get_label() == "_fill"),
        "markers": [str(ln.get_marker()) for ln in series_lines],
        "alphas": [ln.get_alpha() for ln in series_lines] + [c.get_alpha() for c in scatters],
        "annotations": {
            "texts": len(ax.texts) - fit_texts,
            "hlines": hlines,
            "vlines": vlines,
            "hspans": hspans,
            "vspans": vspans,
        },
        "fitlines": sum(1 for ln in lines if _is_fit_label(ln.get_label())),
        "fittexts": fit_texts,
    }


def figure_summary(fig) -> list[dict]:
    """Figure の中身の要約（軸ごと）。JSON にできる値だけで、E2E と生成コードの一致確認に使う。

    Phase 5c で足したキー（既存のキーの値は変えない）:
    - drawstyles: 系列の線の drawstyle（"default" / "steps-pre" / "steps-mid" / "steps-post"。markers と同じ絞り込み）
    - bars: {vertical, horizontal, containers, stacked}。BarContainer の棒の本数（縦向き・横向き）、容器ごとの棒の数、
      棒の下端（横棒は左端）が 0 でない容器の数（積み上げ棒の2系列目以降）。ヒストグラムも BarContainer
    - colorbar: カラーバーが無ければ null、あれば {label, cmap, vmin, vmax}。カラーバーの Axes は軸ごとの一覧に入れず、
      元の Axes の項目として出す（色分け散布図は第2Y軸が無いので、最初の Axes に付く）
    """
    out = []
    colorbar = _colorbar_summary(fig)
    for ax in fig.axes:
        if _is_colorbar_axes(ax):
            continue
        legend = ax.get_legend()
        out.append(
            {
                "title": ax.get_title(),
                "xlabel": ax.get_xlabel(),
                "ylabel": ax.get_ylabel(),
                "xlim": [float(v) for v in ax.get_xlim()],
                "ylim": [float(v) for v in ax.get_ylim()],
                "xscale": ax.get_xscale(),
                "yscale": ax.get_yscale(),
                "lines": len(ax.lines),
                "collections": len(ax.collections),
                "patches": len(ax.patches),
                "legend": [t.get_text() for t in legend.get_texts()] if legend is not None else [],
                "xticklabels": [t.get_text() for t in ax.get_xticklabels()],
                "xconverter": type(ax.xaxis.get_converter()).__name__ if ax.xaxis.get_converter() is not None else None,
                "yticklabels": [t.get_text() for t in ax.get_yticklabels()],
                "xinverted": bool(ax.xaxis_inverted()),
                "yinverted": bool(ax.yaxis_inverted()),
                "spines": {"top": bool(ax.spines["top"].get_visible()), "right": bool(ax.spines["right"].get_visible())},
                "xmajor": type(ax.xaxis.get_major_locator()).__name__,
                "ymajor": type(ax.yaxis.get_major_locator()).__name__,
                "xminor": type(ax.xaxis.get_minor_locator()).__name__,
                "yminor": type(ax.yaxis.get_minor_locator()).__name__,
                "xformatter": type(ax.xaxis.get_major_formatter()).__name__,
                "yformatter": type(ax.yaxis.get_major_formatter()).__name__,
                "yoffset": _offset_text(ax.yaxis),
                "errorbars": sum(1 for line in ax.lines if line.get_label() == "_errorbar")
                + sum(1 for c in ax.containers if type(c).__name__ == "ErrorbarContainer"),
                **_style_summary(ax),
                "colorbar": colorbar if not out else None,
            }
        )
    return out


# ---------------------------------------------------------------- script execution

# 例外の型 → 日本語の説明（上から順に isinstance で判定する。サブクラスを先に並べる）
_HINTS: tuple[tuple[type, str], ...] = (
    (IndentationError, "インデント（字下げ）が正しくありません"),
    (SyntaxError, "書き方（文法）が正しくありません"),
    (NameError, "定義されていない名前を使っています"),
    (FileNotFoundError, "ファイルが見つかりません"),
    (ModuleNotFoundError, "読み込めないライブラリがあります（使えるのは pandas, matplotlib, numpy です）"),
    (ImportError, "読み込めないライブラリや名前があります（使えるのは pandas, matplotlib, numpy です）"),
    (KeyError, "存在しないキー（列名など）を指定しています"),
    (IndexError, "範囲の外の位置を指定しています"),
    (TypeError, "型が合わない操作をしています"),
    (ValueError, "値が正しくありません"),
    (AttributeError, "存在しない属性やメソッドを使っています"),
    (ZeroDivisionError, "0で割り算をしています"),
    (SystemExit, "exit() などでスクリプトが途中で終了しました"),
)


MATHTEXT_HINT = "数式（$ で囲んだ部分）の書き方が正しくありません。$ を文字として使うときは \\$ と書きます。"


class MathtextError(UserError):
    """保存・画像化のときに見つかった、数式（mathtext）の書き間違い。"""


def is_mathtext_error(exc: BaseException | None) -> bool:
    """matplotlib の数式（mathtext）の構文エラーか。例外（と __cause__ / __context__ の連鎖）を調べる。

    matplotlib/_mathtext.py のパーサから出た ValueError、または pyparsing の ParseBaseException を数式のエラーとみなす。
    """
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if any(c.__name__ == "ParseBaseException" for c in type(exc).__mro__):
            return True
        if isinstance(exc, ValueError):
            for frame in traceback.extract_tb(exc.__traceback__):
                if os.path.basename(frame.filename) in {"_mathtext.py", "mathtext.py"} and "matplotlib" in frame.filename:
                    return True
        exc = exc.__cause__ or exc.__context__
    return False


def japanese_hint(exc: BaseException) -> str | None:
    if is_mathtext_error(exc):
        return MATHTEXT_HINT
    for kind, hint in _HINTS:
        if isinstance(exc, kind):
            return hint
    return None


class ScriptError(UserError):
    """スクリプトの実行時エラー。message は日本語の要約。traceback は plot.py の行だけ、detail は全体。"""

    def __init__(self, message, *, field=None, detail=None, traceback_text="", line=None, output="", exc=None):
        super().__init__(message, field=field, detail=detail)
        self.traceback_text = traceback_text
        self.line = line
        self.output = output
        self.exc = exc

    def to_dict(self) -> dict:
        out = super().to_dict()
        out["traceback"] = self.traceback_text
        out["line"] = self.line
        return out


def _user_frames(tb) -> list[traceback.FrameSummary]:
    return [f for f in traceback.extract_tb(tb) if f.filename == SCRIPT_FILENAME]


def _format_user_traceback(exc: BaseException) -> tuple[str, int | None]:
    """plot.py の行だけのトレースバック文字列と、最後の plot.py の行番号。"""
    frames = _user_frames(exc.__traceback__)
    lines: list[str] = []
    line: int | None = None
    if frames:
        lines.append("Traceback (most recent call last):\n")
        lines.extend(traceback.format_list(frames))
        line = frames[-1].lineno
    if isinstance(exc, SyntaxError) and exc.lineno:
        line = exc.lineno
    lines.extend(traceback.format_exception_only(type(exc), exc))
    return "".join(lines), line


def _error_message(exc: BaseException, line: int | None) -> str:
    kind = type(exc).__name__
    hint = japanese_hint(exc)
    what = f"{kind}: {hint}" if hint else kind
    where = f"{line}行目、" if line else ""
    return f"Pythonコードの実行中にエラーが発生しました（{where}{what}）。詳細は「{CODE_FIELD}」タブに表示しています。"


@dataclass
class ScriptRun:
    fig: Figure
    output: str
    namespace: dict = field(default_factory=dict)


@contextlib.contextmanager
def _working_directory(path):
    if path is None:
        yield
        return
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _pick_figure(namespace: dict, before: set[int]):
    fig = namespace.get("fig")
    if isinstance(fig, Figure):
        return fig
    new_numbers = [n for n in plt.get_fignums() if n not in before]
    if new_numbers:
        return plt.figure(new_numbers[-1])
    return None


@contextlib.contextmanager
def run_script(code: str, *, injected: dict | None = None, cwd: str | Path | None = None):
    """コードを実行し、Figure と print の出力を返す（with ブロックを抜けると、実行中に作られた図を全て閉じる）。

    - rcParams は実行前に戻す（スクリプトが変えた設定を次の実行に持ち越さない）。
    - 実行中に作られた図は、ブロックを抜けるときに閉じる（呼び出し側は with の中で画像にする）。
    - 失敗は ScriptError（compile / 実行時の例外）または UserError（図が作られなかった）。
    """
    before = set(plt.get_fignums())
    buffer = io.StringIO()
    namespace: dict = {"__name__": "__main__", "__builtins__": builtins, **(injected or {})}
    try:
        with matplotlib.rc_context():
            try:
                _execute(code, namespace, buffer, cwd)
            except UserError:
                raise
            except (Exception, SystemExit) as exc:
                text, line = _format_user_traceback(exc)
                raise ScriptError(
                    _error_message(exc, line),
                    field=CODE_FIELD,
                    detail="".join(traceback.format_exception(exc)),
                    traceback_text=text,
                    line=line,
                    output=buffer.getvalue(),
                    exc=exc,
                ) from exc
            fig = _pick_figure(namespace, before)
            if fig is None:
                err = UserError(NO_FIGURE_MESSAGE, field=CODE_FIELD)
                err.output = buffer.getvalue()
                raise err
            yield ScriptRun(fig=fig, output=buffer.getvalue(), namespace=namespace)
    finally:
        linecache.cache.pop(SCRIPT_FILENAME, None)  # トレースバックの整形は終わっている
        for num in set(plt.get_fignums()) - before:
            plt.close(num)


def _execute(code: str, namespace: dict, buffer: io.StringIO, cwd) -> None:
    lines = code.splitlines(True)
    linecache.cache[SCRIPT_FILENAME] = (len(code), None, lines, SCRIPT_FILENAME)
    with _working_directory(cwd), contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        compiled = compile(code, SCRIPT_FILENAME, "exec")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=_SHOW_WARNING, category=UserWarning)
            exec(compiled, namespace)  # noqa: S102 - 利用者自身のコード（または生成したコード）を実行する




@dataclass
class ImageResult:
    data: bytes
    mime: str
    ext: str
    output: str
    summary: list


def run_to_image(
    code: str,
    *,
    file_format: str = "png",
    transparent: bool = False,
    dpi: int = 100,
    svg_text: str = "path",
    injected: dict | None = None,
    cwd: str | Path | None = None,
) -> ImageResult:
    """コードを実行して Figure を画像にする。失敗した例外には、実行中の出力を output 属性で付ける。"""
    with run_script(code, injected=injected, cwd=cwd) as run:
        output = run.output
        try:
            data, mime, ext = figure_to_bytes(run.fig, file_format, transparent, dpi, svg_text)
            summary = figure_summary(run.fig)
        except UserError as exc:
            exc.output = output
            raise
    return ImageResult(data=data, mime=mime, ext=ext, output=output, summary=summary)
