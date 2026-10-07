"""設定（と読み込んだファイルの情報・描画計画）から、matplotlib のスクリプトを生成する（純粋な関数）。

生成するコードが使うのは pandas / matplotlib / numpy だけ。ローカルの Python でそのまま実行できる。
GUI の描画は、このスクリプトの「データ読込」と「保存・表示」を除いた部分を実行して行う（runner）。

安全性: 列名・タイトル・ラベル・色・ファイル名は信頼できない入力であり、実行されるコードに入る。
すべての値は literal() だけを通して書き出し（str / int / 有限の float / bool / None を repr で出力）、
コメントに入る文字列は comment_text() で改行・制御文字を空白にする。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .dataprep import PlotPlan, SeriesPlan
from .fonts import LATIN_FONTS, SANS_SERIF_PRIORITY
from .formats import FORMATS, build_filename, savefig_kwargs, savefig_rc
from .loader import SourceInfo
from .settings import SeriesSettings, Settings

SCRIPT_NAME = "plot.py"

GENERIC_ERROR_MESSAGE = "グラフを描画できませんでした。X列・Y列に指定した列の値の形式（数値と文字列の混在など）や、設定の値を確認してください。"
TIGHT_LAYOUT_ERROR = "レイアウトの自動調整に失敗しました。余白を手動で指定するか、図の大きさ・フォントサイズを小さくしてください。"
MARGIN_ERROR = "余白の設定を適用できませんでした。左 < 右、下 < 上 になるように、0〜1の値で指定してください。"


def axis_error_message(label: str) -> str:
    return f"{label}軸のスケールまたは範囲を適用できませんでした。範囲の値を確認してください。"


# ---------------------------------------------------------------- literals and comments


def literal(value) -> str:
    """コードに書き出せる値（str / int / 有限の float / bool / None）だけを repr で文字列にする。"""
    kind = type(value)
    if value is None or kind is bool:
        return repr(value)
    if kind is int:
        return repr(value)
    if kind is float:
        if not math.isfinite(value):
            raise ValueError("有限でない数値はコードに書き出せません")
        return repr(value)
    if kind is str:
        text = repr(value)
        if text[0] == "'" and '"' not in value and "'" not in value:
            text = '"' + text[1:-1] + '"'  # 読みやすいように二重引用符にする（中身はエスケープだけなので安全）
        return text
    raise TypeError(f"コードに書き出せない型です: {kind.__name__}")


_LINE_BREAKS = {" ", " ", "\x85", "\x0b", "\x0c", "\r", "\n"}


def comment_text(text) -> str:
    """コメントに入れる文字列。改行・印字できない文字（制御文字を含む）を空白にする。"""
    return "".join(" " if (ch in _LINE_BREAKS or not ch.isprintable()) else ch for ch in str(text))


def _column_comment(plan_series: SeriesPlan, which: str) -> str:
    if which == "x":
        if plan_series.x_index is None:
            return "行番号"
        return f"{comment_text(plan_series.x_label)} [{plan_series.x_index}]"
    return comment_text(plan_series.data_label)


# ---------------------------------------------------------------- result type


@dataclass(frozen=True)
class Step:
    start: int  # 1 始まり、両端を含む
    end: int
    message: str
    field: str | None = None


@dataclass(frozen=True)
class GeneratedScript:
    text: str
    load_lines: tuple[int, int]
    output_lines: tuple[int, int]
    steps: tuple[Step, ...]

    def auto_render_text(self) -> str:
        """データ読込と保存・表示の行を空行にしたもの（行番号は表示中のスクリプトと同じ）。df を外から渡して実行する。"""
        lines = self.text.split("\n")
        for start, end in (self.load_lines, self.output_lines):
            for n in range(start, end + 1):
                lines[n - 1] = ""
        return "\n".join(lines)

    def step_for_line(self, line: int | None) -> Step | None:
        if line is None:
            return None
        for step in self.steps:
            if step.start <= line <= step.end:
                return step
        return None


class _Builder:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.steps: list[Step] = []
        self.load_lines = (0, -1)
        self.output_lines = (0, -1)

    def add(self, *lines: str) -> None:
        self.lines.extend(lines)

    def blank(self) -> None:
        self.lines.append("")

    def section(self, title: str) -> int:
        """区切りの見出しを書き、その行番号（1 始まり）を返す。"""
        if self.lines:
            self.blank()
        self.lines.append(f"# ==== {title} ====")
        return len(self.lines)

    def step(self, message: str, field: str | None = None):
        return _StepContext(self, message, field)


class _StepContext:
    def __init__(self, builder: _Builder, message: str, field: str | None) -> None:
        self.builder, self.message, self.field = builder, message, field

    def __enter__(self):
        self.start = len(self.builder.lines) + 1
        return self

    def __exit__(self, *exc):
        end = len(self.builder.lines)
        if end >= self.start:
            self.builder.steps.append(Step(self.start, end, self.message, self.field))
        return False


# ---------------------------------------------------------------- numbers


def _label_size_expr(font_size: float) -> str:
    """目盛・凡例の文字サイズ。max(font_size - 1, 1) と同じ値になる式（下限が効くときは値そのもの）。"""
    return "FONT_SIZE - 1" if font_size - 1 >= 1 else literal(1.0)


# ---------------------------------------------------------------- sections


def _emit_header(b: _Builder, source: SourceInfo, latin_font: str = "default") -> None:
    name = comment_text(source.filename)
    latin = LATIN_FONTS.get(latin_font)
    b.add(
        "# matplotlib GUI が生成したスクリプト",
        f"# 使い方: データファイル「{name}」と同じフォルダに置いて、python {SCRIPT_NAME} で実行します。",
        "# 必要なライブラリ: pandas, matplotlib, numpy",
        "import matplotlib.pyplot as plt",
    )
    if latin is not None:
        b.add("from matplotlib import font_manager")
    b.add(
        "import numpy as np",
        "import pandas as pd",
        "",
        "# 日本語フォント: 一覧の先頭から、見つかったものを使う。",
        "# どれも無い環境では DejaVu Sans になる（日本語は豆腐になるが、実行はできる）",
    )
    if latin is None:
        b.add('plt.rcParams["font.family"] = "sans-serif"')
    b.add(
        f'plt.rcParams["font.sans-serif"] = {_font_list_literal()}',
        'plt.rcParams["axes.unicode_minus"] = False',
    )
    if latin is not None:
        names = "[" + ", ".join(literal(n) for n in latin.candidates) + "]"
        b.add(
            "",
            f"# 欧文フォント: {comment_text(latin.display)}。無ければ一覧の次のフォントを使い、どれも無ければ日本語フォントで書く",
            "installed = {font.name for font in font_manager.fontManager.ttflist}",
            f"latin = [name for name in {names} if name in installed][:1]",
            'plt.rcParams["font.family"] = latin + ["sans-serif"]  # 欧文は latin のフォント、日本語は font.sans-serif のフォントで書く',
        )
        if latin.mathtext_fontset is not None:
            b.add(f'plt.rcParams["mathtext.fontset"] = {literal(latin.mathtext_fontset)}  # 数式（$...$）も Times 系の字形にする（STIX は matplotlib に同梱）')


def _font_list_literal() -> str:
    return "[" + ", ".join(literal(name) for name in SANS_SERIF_PRIORITY) + "]"


def _emit_load(b: _Builder, source: SourceInfo) -> None:
    start = b.section("1. データの読み込み")
    header_arg = literal(0 if source.has_header else None)
    header_note = "あり" if source.has_header else "なし"
    if source.kind == "xlsx":
        b.add(
            f"# 形式: Excel（.xlsx）、シート: {comment_text(source.sheet_name)}（先頭のシート）、先頭行をヘッダにする: {header_note}",
            "# .xlsx の読み込みには openpyxl が必要です（pip install openpyxl）",
            f"DATA_FILE = {literal(source.filename)}",
            "# 前置き行（データの前にある説明の行）を飛ばすときは、read_excel に skiprows=行数 を足す",
            f"df = pd.read_excel(DATA_FILE, sheet_name={literal(source.sheet_name)}, header={header_arg})",
        )
    else:
        b.add(
            f"# 文字コード: {comment_text(source.encoding)}（自動判定）、区切り文字: {comment_text(literal(source.separator))}、先頭行をヘッダにする: {header_note}",
            f"DATA_FILE = {literal(source.filename)}",
            "# 前置き行（データの前にある説明の行）を飛ばすときは、read_csv に skiprows=行数 を足す",
            f"df = pd.read_csv(DATA_FILE, encoding={literal(source.encoding)}, sep={literal(source.separator)}, "
            f'header={header_arg}, engine="python")',
        )
    if not source.has_header:
        b.add('df.columns = [f"column_{i}" for i in range(len(df.columns))]  # 列名を column_0, column_1, ... にする')
    b.load_lines = (start, len(b.lines))


def _emit_skip_rows(b: _Builder, plan: PlotPlan) -> None:
    b.section("2. 描画に使う行")
    if plan.skip_rows > 0:
        b.add(f"df = df.iloc[{literal(plan.skip_rows)}:].reset_index(drop=True)  # 先頭の{plan.skip_rows}行を描画から除外する")
    else:
        b.add("# 先頭の行は除外しない（全ての行を使う）")


def _emit_figure(b: _Builder, settings: Settings) -> None:
    b.section("3. 図と軸")
    fig = settings.plot.figure
    w, h = literal(fig.width), literal(fig.height)
    if fig.unit == "in":
        b.add(f"fig, ax = plt.subplots(figsize=({w}, {h}), dpi=100)  # 幅 {comment_text(w)} × 高さ {comment_text(h)} インチ")
    else:
        # 割り算で直す（1 / 2.54 を掛けると、20.32 cm が 7.999… inch になり、画像が 1 px 欠ける）
        const, per_inch = ("CM_PER_INCH", "2.54") if fig.unit == "cm" else ("MM_PER_INCH", "25.4")
        b.add(
            f"{const} = {per_inch}  # 1 インチ = {per_inch} {fig.unit}（figsize はインチで指定するので、{fig.unit} の値をこれで割る）",
            f"fig, ax = plt.subplots(figsize=({w} / {const}, {h} / {const}), dpi=100)  # 幅 {comment_text(w)} {fig.unit} × 高さ {comment_text(h)} {fig.unit}",
        )


# ---- series emitters (registry) ----


def _series_comment(p: SeriesPlan, *, bar_x: bool = False) -> str:
    where = "（第2Y軸）" if p.secondary else ""
    return f"# 系列{p.number}{where}: X = {_column_comment(p, 'x')}、Y = {_column_comment(p, 'y')}"


def _target(p: SeriesPlan) -> str:
    return "ax2" if p.secondary else "ax"


def _emit_x_data(b: _Builder, p: SeriesPlan) -> None:
    if p.x_index is None:
        b.add("x = pd.Series(df.index)  # X は指定なし。行番号を使う")
    elif p.convert_x:
        b.add(f'x = pd.to_numeric(df.iloc[:, {p.x_index}], errors="coerce")  # 数値にできない値は NaN にする')
    else:
        b.add(f"x = df.iloc[:, {p.x_index}]")


def _emit_y_data(b: _Builder, p: SeriesPlan) -> None:
    b.add(f'y = pd.to_numeric(df.iloc[:, {p.y_index}], errors="coerce")  # 数値にできない値は NaN にする')


def _emit_ok_mask(b: _Builder) -> None:
    b.add("ok = x.notna() & y.notna()  # X か Y が欠けている行は描かない")


class _Axes2State:
    """第2Y軸（ax2）を、最初に描く第2軸の系列の直前に作る。"""

    def __init__(self) -> None:
        self.created = False

    def ensure(self, b: _Builder, p: SeriesPlan) -> None:
        if p.secondary and not self.created:
            b.add("ax2 = ax.twinx()  # 第2Y軸（右側）")
            self.created = True


def _style_args(s: SeriesSettings) -> str:
    return f"color={literal(s.color)}, linewidth={literal(s.line_width)}, linestyle={literal(s.line_style)}"


def _emit_line_series(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    ax2 = _Axes2State()
    for i, (s, p) in enumerate(zip(settings.series, plan.series)):
        if i > 0:
            b.blank()  # 系列ごとに1行あける
        b.add(_series_comment(p))
        if not p.has_points:
            b.add("# 描ける点（X・Y とも数値の行）が無いため、この系列は描かない")
            continue
        with b.step(GENERIC_ERROR_MESSAGE):
            ax2.ensure(b, p)
            _emit_x_data(b, p)
            _emit_y_data(b, p)
            _emit_ok_mask(b)
            marker = ""
            if p.marker_size > 0:
                b.add("# 点の大きさ: 面積（scatter の s と同じ単位）の平方根を markersize（直径）にする")
                marker = f', marker="o", markersize={literal(p.marker_size)} ** 0.5'
            b.add(f"{_target(p)}.plot(x[ok], y[ok], {_style_args(s)}{marker}, label={literal(p.legend_label)})")


def _emit_scatter_series(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    ax2 = _Axes2State()
    for i, (s, p) in enumerate(zip(settings.series, plan.series)):
        if i > 0:
            b.blank()  # 系列ごとに1行あける
        b.add(_series_comment(p))
        if not p.has_points:
            b.add("# 描ける点（X・Y とも数値の行）が無いため、この系列は描かない")
            continue
        with b.step(GENERIC_ERROR_MESSAGE):
            ax2.ensure(b, p)
            _emit_x_data(b, p)
            _emit_y_data(b, p)
            _emit_ok_mask(b)
            b.add(
                f"{_target(p)}.scatter(x[ok], y[ok], color={literal(s.color)}, s={literal(p.marker_size)}, "
                f"label={literal(p.legend_label)})"
            )


def _emit_bar_x(b: _Builder, plan: PlotPlan) -> None:
    if plan.bar_x_index is None:
        b.add("x = pd.Series(df.index)  # X は指定なし。行番号を使う")
    else:
        b.add(f"x = df.iloc[:, {plan.bar_x_index}]")


def _emit_bar_series(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    ax2 = _Axes2State()
    if len(plan.series) == 1:
        s, p = settings.series[0], plan.series[0]
        b.add(_series_comment(p))
        with b.step(GENERIC_ERROR_MESSAGE):
            ax2.ensure(b, p)
            _emit_bar_x(b, plan)
            _emit_y_data(b, p)
            _emit_ok_mask(b)
            b.add(f"{_target(p)}.bar(x[ok], y[ok], {_style_args(s)}, label={literal(p.legend_label)})")
        return

    n = len(plan.series)
    b.add("# 複数の系列を、X の値ごとに横に並べた棒グラフにする（X は共通）")
    with b.step(GENERIC_ERROR_MESSAGE):
        _emit_bar_x(b, plan)
        b.add("bar_data = pd.DataFrame({")
        b.add('    "x": x,')
        for p in plan.series:
            b.add(f'    "y{p.number}": pd.to_numeric(df.iloc[:, {p.y_index}], errors="coerce"),  # {_column_comment(p, "y")}')
        b.add("})")
        keys = ", ".join(literal(f"y{p.number}") for p in plan.series)
        b.add(f'bar_data = bar_data.dropna(subset=[{keys}], how="all")  # 全ての系列が欠けている行は描かない')
        b.add("x_labels = [str(v) for v in bar_data[\"x\"]]")
        b.add("positions = np.arange(len(x_labels))")
        b.add(f"width = 0.8 / {n}  # 棒1本の幅")
        for i, (s, p) in enumerate(zip(settings.series, plan.series)):
            b.blank()
            b.add(_series_comment(p))
            ax2.ensure(b, p)
            b.add(f"offset = -0.4 + (width / 2.0) + ({i} * width)")
            b.add(
                f'{_target(p)}.bar(positions + offset, bar_data["y{p.number}"].fillna(0.0), width=width, '
                f"{_style_args(s)}, label={literal(p.legend_label)})"
            )


SERIES_EMITTERS: dict[str, Callable[[_Builder, Settings, PlotPlan], None]] = {
    "line": _emit_line_series,
    "scatter": _emit_scatter_series,
    "bar": _emit_bar_series,
}


def _emit_series(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    b.section("4. 系列")
    SERIES_EMITTERS[plan.plot_type](b, settings, plan)


def _axis_lines(var: str, which: str, scale: str, lo, hi) -> list[str]:
    lines = []
    if scale == "log":
        lines.append(f'{var}.set_{which}scale("log")')
    limits = [f"{k}={literal(v)}" for k, v in (("left" if which == "x" else "bottom", lo), ("right" if which == "x" else "top", hi)) if v is not None]
    if limits:
        lines.append(f"{var}.set_{which}lim({', '.join(limits)})")
    return lines


def _emit_axes(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    b.section("5. 軸（ラベル・スケール・範囲・目盛）")
    plot, axes = settings.plot, settings.axes
    if plot.title:
        b.add(f"ax.set_title({literal(plot.title)}, fontsize=FONT_SIZE + 2)")
    b.add(f"ax.set_xlabel({literal(axes.x.label or plan.x_label)}, fontsize=FONT_SIZE)")
    b.add(f"ax.set_ylabel({literal(axes.y.label or plan.y_label)}, fontsize=FONT_SIZE)")
    if plan.uses_secondary:
        b.add(f"ax2.set_ylabel({literal(axes.y2.label or plan.y2_label)}, fontsize=FONT_SIZE)")

    for var, which, label, axis in (
        ("ax", "x", "X", axes.x),
        ("ax", "y", "Y", axes.y),
        ("ax2", "y", "第2Y", axes.y2),
    ):
        if var == "ax2" and not plan.uses_secondary:
            continue
        lines = _axis_lines(var, which, axis.scale, axis.min, axis.max)
        if var == "ax" and which == "x" and axis.scale == "linear" and any(p.categorical_x and p.has_points for p in plan.series):
            lines.insert(0, 'ax.set_xscale("linear")  # X が文字列・日時の列: 目盛は位置の番号になる（値を目盛にするには、この行を消す）')
        if lines:
            with b.step(axis_error_message(label), f"{label}軸の範囲"):
                b.add(*lines)

    if plan.plot_type == "bar" and len(plan.series) > 1:
        b.add(
            "# 棒の位置に X の値を目盛として付ける（25個を超えるときは間引く）",
            "tick_step = max(1, len(positions) // 25)",
            "ax.set_xticks(positions[::tick_step])",
            'ax.set_xticklabels(x_labels[::tick_step], rotation=45, ha="right")',
        )

    size = _label_size_expr(plot.font_size)
    b.add("# 目盛は内向きにする", f'ax.tick_params(which="both", direction="in", labelsize={size})')
    if plan.uses_secondary:
        b.add(f'ax2.tick_params(which="both", direction="in", labelsize={size})')

    if not plot.grid_minor:
        if axes.x.scale == "log" or axes.y.scale == "log":
            b.add("ax.minorticks_off()  # 対数軸の補助目盛は出さない")
        if plan.uses_secondary and axes.y2.scale == "log":
            b.add("ax2.minorticks_off()")


def _emit_grid_and_legend(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    b.section("6. グリッドと凡例")
    plot = settings.plot
    if plot.grid_minor:
        b.add("ax.minorticks_on()")
        if plan.uses_secondary:
            b.add("ax2.minorticks_on()")
    if plot.grid_major:
        b.add('ax.grid(True, which="major", axis="both", alpha=0.3)')
        if plan.uses_secondary:
            b.add('ax2.grid(True, which="major", axis="y", alpha=0.3)')
    if plot.grid_minor:
        b.add('ax.grid(True, which="minor", axis="both", alpha=0.2, linestyle=":")')
        if plan.uses_secondary:
            b.add('ax2.grid(True, which="minor", axis="y", alpha=0.2, linestyle=":")')
    if not (plot.grid_major or plot.grid_minor):
        b.add("# グリッドは表示しない")

    if plot.legend_location == "none":
        b.add("# 凡例は表示しない")
        return
    if not any(p.has_points and p.legend_label and not p.legend_label.startswith("_") for p in plan.series):
        b.add("# 凡例に出せるラベルが無い（空、または _ で始まる）ため、凡例は表示しない")
        return
    size = _label_size_expr(plot.font_size)
    loc = literal(plot.legend_location)
    if plan.uses_secondary:
        b.add(
            "# 第1・第2Y軸の系列をまとめて凡例にする",
            "handles, labels = ax.get_legend_handles_labels()",
            "handles2, labels2 = ax2.get_legend_handles_labels()",
            f'ax.legend(handles + handles2, labels + labels2, loc={loc}, fontsize={size}, edgecolor="black")',
        )
    else:
        b.add(f'ax.legend(loc={loc}, fontsize={size}, edgecolor="black")')


def _emit_margins(b: _Builder, settings: Settings) -> None:
    b.section("7. 余白")
    provided = settings.plot.margins.provided()
    if len(provided) < 4:
        b.add("# 余白は自動で調整する")
        with b.step(TIGHT_LAYOUT_ERROR, "余白"):
            b.add("fig.tight_layout()")
    else:
        b.add("# 余白は4辺とも指定されている")
    if provided:
        args = ", ".join(f"{k}={literal(v)}" for k, v in provided.items())
        if len(provided) < 4:
            b.add("# 指定された辺だけ、自動調整の結果を上書きする")
        with b.step(MARGIN_ERROR, "余白"):
            b.add(f"fig.subplots_adjust({args})")


_RC_COMMENTS = {
    ("pdf", "pdf.fonttype"): "PDF に文字をフォントとして埋め込む（Illustrator などで文字を編集できる）",
    ("svg", "svg.fonttype", "path"): "SVG の文字を図形（パス）にする（どの環境でも同じ見た目）。\"none\" にすると文字のまま残る",
    ("svg", "svg.fonttype", "none"): "SVG の文字をテキストのまま残す（編集できる。開く環境に同じフォントが無いと見た目が変わる）",
}

_PDF_CFF_NOTE = (
    "# ※ 手元の日本語フォントが OpenType（CFF）形式（macOS のヒラギノなど）だと、この PDF の文字は正しく表示されないことがある。",
    "#   そのときは Noto Sans JP（TrueType 版）を入れるか、42 を 3 にする（文字は編集できなくなる）",
)


def _emit_output(b: _Builder, settings: Settings) -> None:
    start = b.section("8. 保存と表示")
    save = settings.save
    _, _, ext = FORMATS[save.format]
    filename = build_filename(save.filename, ext)
    for key, value in savefig_rc(save.format, save.svg_text).items():
        comment = _RC_COMMENTS.get((save.format, key)) or _RC_COMMENTS[(save.format, key, value)]
        if save.format == "pdf":
            b.add(*_PDF_CFF_NOTE)
        b.add(f"plt.rcParams[{literal(key)}] = {literal(value)}  # {comment}")
    kwargs = savefig_kwargs(save.format, save.transparent, save.dpi)
    args = "".join(f", {k}={literal(v)}" for k, v in kwargs.items())
    note = f"GUI の「保存」と同じ形式（{ext}）" + (f"と解像度（{save.dpi} dpi）" if "dpi" in kwargs else "")
    b.add(f"fig.savefig({literal(filename)}{args})  # {note}", "plt.show()")
    b.output_lines = (start, len(b.lines))


# ---------------------------------------------------------------- entry


def generate_script(settings: Settings, source: SourceInfo, plan: PlotPlan) -> GeneratedScript:
    """設定・読み込んだファイルの情報・描画計画から、完全なスクリプトを作る。"""
    b = _Builder()
    _emit_header(b, source, settings.plot.latin_font)
    b.add(f"FONT_SIZE = {literal(settings.plot.font_size)}  # 文字の大きさ（pt）")
    _emit_load(b, source)
    _emit_skip_rows(b, plan)
    _emit_figure(b, settings)
    _emit_series(b, settings, plan)
    _emit_axes(b, settings, plan)
    _emit_grid_and_legend(b, settings, plan)
    _emit_margins(b, settings)
    _emit_output(b, settings)
    return GeneratedScript(
        text="\n".join(b.lines) + "\n",
        load_lines=b.load_lines,
        output_lines=b.output_lines,
        steps=tuple(b.steps),
    )
