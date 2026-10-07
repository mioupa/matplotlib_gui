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


def figure_summary(fig) -> list[dict]:
    """Figure の中身の要約（軸ごと）。JSON にできる値だけで、E2E と生成コードの一致確認に使う。"""
    out = []
    for ax in fig.axes:
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


def japanese_hint(exc: BaseException) -> str | None:
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
