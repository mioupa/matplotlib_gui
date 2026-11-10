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

from .dataprep import AxisPlan, ErrorPlan, PlotPlan, SeriesPlan
from .fonts import LATIN_FONTS, SANS_SERIF_PRIORITY
from .formats import FORMATS, build_filename, savefig_kwargs, savefig_rc
from .loader import DatetimeColumn, SourceInfo
from .settings import AxisSettings, SeriesSettings, Settings

SCRIPT_NAME = "plot.py"

GENERIC_ERROR_MESSAGE = "グラフを描画できませんでした。X列・Y列に指定した列の値の形式（数値と文字列の混在など）や、設定の値を確認してください。"
TIGHT_LAYOUT_ERROR = "レイアウトの自動調整に失敗しました。余白を手動で指定するか、図の大きさ・フォントサイズを小さくしてください。"
MARGIN_ERROR = "余白の設定を適用できませんでした。左 < 右、下 < 上 になるように、0〜1の値で指定してください。"


def axis_error_message(label: str) -> str:
    return f"{label}軸のスケールまたは範囲を適用できませんでした。範囲の値を確認してください。"


def tick_error_message(label: str) -> str:
    return f"{label}軸の目盛を設定できませんでした。目盛の設定を確認してください。"


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


def _emit_header(
    b: _Builder, sources: list[SourceInfo], latin_font: str = "default", plan: PlotPlan | None = None, settings: Settings | None = None
) -> None:
    latin = LATIN_FONTS.get(latin_font)
    if len(sources) == 1:
        source = sources[0]
        name = comment_text(source.filename)
        if source.pasted:
            usage = f"# 使い方: 貼り付けたデータを保存した「{name}」と同じフォルダに置いて、python {SCRIPT_NAME} で実行します。"
        else:
            usage = f"# 使い方: データファイル「{name}」と同じフォルダに置いて、python {SCRIPT_NAME} で実行します。"
    else:
        names = "".join(
            f"「{comment_text(src.filename)}」" + ("（貼り付けたデータを保存したもの）" if src.pasted else "") for src in sources
        )
        usage = f"# 使い方: データファイル {names} を、このスクリプトと同じフォルダに置いて、python {SCRIPT_NAME} で実行します。"
    b.add(
        "# matplotlib GUI が生成したスクリプト",
        usage,
        "# 必要なライブラリ: pandas, matplotlib, numpy",
    )
    if plan is not None and _uses_date_axis(plan):
        b.add("import matplotlib.dates as mdates")
    b.add("import matplotlib.pyplot as plt")
    if plan is not None and settings is not None and _uses_ticker(settings, plan):
        b.add("import matplotlib.ticker as ticker")
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


def _uses_date_axis(plan: PlotPlan) -> bool:
    return plan.datetime_x and plan.plot_type in {"line", "scatter"}


def _font_list_literal() -> str:
    return "[" + ", ".join(literal(name) for name in SANS_SERIF_PRIORITY) + "]"


# 読込の引数ごとのコメント（SourceInfo.read_kwargs の全てのキーに必要。読込部はこの順・この内容で、全ての引数を明記する）
_READ_COMMENTS = {
    "sep": "区切り文字",
    "header": "先頭行をヘッダにする（None: ヘッダなし）",
    "skiprows": "ヘッダより前に読み飛ばす行数",
    "thousands": "桁区切り（None: なし）",
    "decimal": "小数点",
    "comment": "コメント記号（None: なし）。この記号から行末までを読まない",
    "engine": None,
    "sheet_name": "シート",
}
_READ_COMMENTS_XLSX = {
    "thousands": "桁区切り（文字列のセルだけに効く。None: なし）",
    "decimal": "小数点（文字列のセルだけに効く）",
}
_KIND_NOTES = {"csv": "CSV（.csv）", "txt": "テキスト（.txt）", "tsv": "TSV（.tsv）", "xlsx": "Excel（.xlsx）"}


def _datetime_expr(spec: DatetimeColumn, df: str = "df") -> str:
    """列を日時にする式。loader.convert_datetime と同じ内容（単体テストで一致を確かめる）。"""
    source = f"{df}.iloc[:, {spec.index}]" + (".str.strip()" if spec.strip else "")
    utc = ", utc=True" if spec.utc else ""
    expr = f'pd.to_datetime({source}, format={literal(spec.format)}, errors="coerce"{utc})'
    return expr + ".dt.tz_localize(None)" if spec.has_tz else expr


def _emit_read(b: _Builder, source: SourceInfo, data_file: str, df: str) -> None:
    """1つのファイルの読み込み（DATA_FILE と df の名前は呼び出し側が決める）。"""
    xlsx = source.kind == "xlsx"
    if source.pasted:
        b.add(
            f"# 貼り付けたデータ: 「データ読み込み」の「貼り付けたデータを保存」で {comment_text(source.filename)} を保存し、"
            "このスクリプトと同じフォルダに置いてください。"
        )
    b.add(f"# 形式: {_KIND_NOTES.get(source.kind, comment_text(source.kind))}")
    if xlsx:
        b.add("# 読み込みには openpyxl が必要です（pip install openpyxl）")
        if source.sheets:
            b.add(f"# ファイル内のシート: {comment_text(', '.join(source.sheets))}")
    b.add(f"{data_file} = {literal(source.filename)}")
    func = "pd.read_excel" if xlsx else "pd.read_csv"
    b.add(f"{df} = {func}(", f"    {data_file},")
    if not xlsx:
        b.add(f"    encoding={literal(source.encoding)},  # 文字コード（自動判定）")
    for key, value in source.read_kwargs().items():
        note = (_READ_COMMENTS_XLSX.get(key) if xlsx else None) or _READ_COMMENTS[key]
        line = f"    {key}={literal(value)},"
        b.add(f"{line}  # {note}" if note else line)
    b.add(")")
    if not source.has_header:
        b.add(f'{df}.columns = [f"column_{{i}}" for i in range(len({df}.columns))]  # 列名を column_0, column_1, ... にする')
    if source.datetime_columns:
        b.add("# 日時の列を日時に変換する（自動で認識した書式。読めない値は NaT（欠損）になる）")
        for spec in source.datetime_columns:
            b.add(f"{df}.isetitem({spec.index}, {_datetime_expr(spec, df)})  # {comment_text(spec.name)} [{spec.index}]")


def _emit_load(b: _Builder, plan: PlotPlan, infos: list[SourceInfo]) -> None:
    start = b.section("1. データの読み込み")
    if not plan.multi_source:
        _emit_read(b, infos[0], "DATA_FILE", "df")
    else:
        for i, (src, info) in enumerate(zip(plan.sources, infos)):
            if i > 0:
                b.blank()
            b.add(f"# データ{src.number}: {comment_text(info.filename)}")
            _emit_read(b, info, f"DATA_FILE_{src.number}", src.var)
    b.load_lines = (start, len(b.lines))


def _emit_skip_rows(b: _Builder, plan: PlotPlan) -> None:
    b.section("2. 描画に使う行")
    if plan.skip_rows > 0:
        for src in plan.sources:
            v = src.var
            b.add(f"{v} = {v}.iloc[{literal(plan.skip_rows)}:].reset_index(drop=True)  # 先頭の{plan.skip_rows}行を描画から除外する")
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
    if p.data_var != "df":
        where += f"（{p.data_var}）"
    return f"# 系列{p.number}{where}: X = {_column_comment(p, 'x')}、Y = {_column_comment(p, 'y')}"


def _target(p: SeriesPlan) -> str:
    return "ax2" if p.secondary else "ax"


def _emit_x_data(b: _Builder, p: SeriesPlan) -> None:
    if p.x_index is None:
        b.add(f"x = pd.Series({p.data_var}.index)  # X は指定なし。行番号を使う")
    elif p.datetime_x:
        b.add(f"x = {p.data_var}.iloc[:, {p.x_index}]  # 日時の列（読み込み時に日時に変換済み）")
    elif p.convert_x:
        b.add(f'x = pd.to_numeric({p.data_var}.iloc[:, {p.x_index}], errors="coerce")  # 数値にできない値は NaN にする')
    else:
        b.add(f"x = {p.data_var}.iloc[:, {p.x_index}]")


def _emit_y_data(b: _Builder, p: SeriesPlan) -> None:
    b.add(f'y = pd.to_numeric({p.data_var}.iloc[:, {p.y_index}], errors="coerce")  # 数値にできない値は NaN にする')


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


# ---- error bars (G1) ----

ERROR_BAR_FUNCTION = (
    'def draw_error_bars(ax, x, y, low, high, *, direction="y", color="black", linewidth=1.0, capsize=3.0, zorder=2):',
    '    """ax.errorbar(x, y, yerr=…, fmt="none", capsize=…) と同じ見た目のエラーバーを描く（点が多くても速く描ける）。',
    "",
    "    ax.errorbar は点ごとに別の線を作るので、点が多いと遅い。そこで、各点の線（low → high）を NaN で区切った1本の線にまとめ、",
    "    両端の短い線（capsize）は点の記号で描く。direction=\"y\" は縦線（low・high は Y の下端・上端）、",
    "    direction=\"x\" は横線（low・high は X の左端・右端）。low・high のどちらかが NaN の点は描かない。",
    '    """',
    "    low = np.asarray(low, dtype=float)",
    "    high = np.asarray(high, dtype=float)",
    "    ends = np.column_stack([low, high, np.full(len(low), np.nan)]).ravel()  # 下端, 上端, 区切り（NaN）, …",
    '    style = dict(color=color, zorder=zorder, label="_errorbar")  # _ で始まるラベルは凡例に出ない',
    '    if direction == "y":',
    "        ax.plot(np.repeat(np.asarray(x), 3), ends, linewidth=linewidth, **style)",
    "    else:",
    "        ax.plot(ends, np.repeat(np.asarray(y), 3), linewidth=linewidth, **style)",
    "    if capsize > 0:",
    '        marker = "_" if direction == "y" else "|"',
    "        for end in (low, high):",
    '            px, py = (x, end) if direction == "y" else (end, y)',
    '            ax.plot(px, py, linestyle="none", marker=marker, markersize=2 * capsize, markeredgewidth=linewidth, **style)',
)


def _uses_error_function(plan: PlotPlan) -> bool:
    return plan.plot_type in {"line", "scatter"} and any(p.has_points and (p.y_err or p.x_err) for p in plan.series)


def _error_names(err: ErrorPlan, owner: str = "") -> tuple[str, str]:
    """誤差の変数名（上（右）, 下（左））。対称なら同じ名前。owner は棒グラフ（複数系列）の "y1" など。"""
    base = f"{owner}_err" if owner else f"{err.direction}_err"
    return (base, base) if err.symmetric else (f"{base}_plus", f"{base}_minus")


def _emit_error_columns(b: _Builder, p: SeriesPlan, err: ErrorPlan, owner: str = "") -> None:
    """列の誤差を、数値にして、負の値を NaN にする（fixed のときは何も書かない）。"""
    if err.mode != "column":
        return
    plus, minus = _error_names(err, owner)
    side = "Y" if err.direction == "y" else "X"
    pairs = [(plus, err.index, err.label, "")]
    if not err.symmetric:
        pairs = [
            (plus, err.index, err.label, "（上）" if err.direction == "y" else "（右）"),
            (minus, err.index_minus, err.label_minus, "（下）" if err.direction == "y" else "（左）"),
        ]
    for name, index, label, note in pairs:
        b.add(
            f'{name} = pd.to_numeric({p.data_var}.iloc[:, {index}], errors="coerce")'
            f"  # {side} の誤差{note}: {comment_text(label)}（数値にできない値は NaN）",
            f"{name} = {name}.where({name} >= 0)  # 負の値は NaN にする（その点のエラーバーは描かない）",
        )


def _error_step(p: SeriesPlan, err: ErrorPlan) -> tuple[str, str]:
    side = err.direction.upper()
    return f"系列{p.number}のエラーバーを描けませんでした。誤差の列・値を確認してください。", f"系列{p.number}の{side}誤差"


def _emit_line_error_bars(b: _Builder, s: SeriesSettings, p: SeriesPlan, *, zorder: int | None = None) -> None:
    """line / scatter の系列本体の直前に、エラーバー（Y・X 方向）を描く。"""
    for err in (p.y_err, p.x_err):
        if err is None:
            continue
        message, field_name = _error_step(p, err)
        with b.step(message, field_name):
            _emit_error_columns(b, p, err)
            plus, minus = _error_names(err)
            base = "y[ok]" if err.direction == "y" else "x[ok]"
            if err.mode == "fixed":
                minus_value = err.value if err.symmetric else err.value_minus
                low, high = f"{base} - {literal(minus_value)}", f"{base} + {literal(err.value)}"
            else:
                low, high = f"{base} - {minus}[ok]", f"{base} + {plus}[ok]"
            extra = f", zorder={zorder}" if zorder is not None else ""
            b.add(
                f'draw_error_bars({_target(p)}, x[ok], y[ok], {low}, {high}, direction="{err.direction}", '
                f"color={literal(s.color)}, linewidth={literal(s.line_width)}, capsize={literal(p.cap_size)}{extra})"
            )


def _bar_yerr_expr(err: ErrorPlan, owner: str = "") -> str:
    """ax.bar の yerr 引数の式（owner が空なら1系列の棒グラフ、"y1" などなら bar_data の列）。"""
    if err.mode == "fixed":
        if err.symmetric:
            return literal(err.value)
        return f"[[{literal(err.value_minus)}], [{literal(err.value)}]]"
    plus, minus = _error_names(err, owner)
    if owner:
        plus, minus = f'bar_data["{plus}"]', f'bar_data["{minus}"]'
    else:
        plus, minus = f"{plus}[ok]", f"{minus}[ok]"
    return plus if err.symmetric else f"[{minus}, {plus}]"


def _bar_error_args(s: SeriesSettings, p: SeriesPlan, owner: str = "") -> str:
    if p.y_err is None:
        return ""
    width = literal(s.line_width)
    return (
        f", yerr={_bar_yerr_expr(p.y_err, owner)}, capsize={literal(p.cap_size)}, ecolor=\"black\", "
        f'error_kw={{"elinewidth": {width}, "capthick": {width}}}'
    )


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
            _emit_line_error_bars(b, s, p)
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
            _emit_line_error_bars(b, s, p, zorder=1)  # 点を上に描くため、エラーバーは zorder=1
            b.add(
                f"{_target(p)}.scatter(x[ok], y[ok], color={literal(s.color)}, s={literal(p.marker_size)}, "
                f"label={literal(p.legend_label)})"
            )


def _emit_bar_x(b: _Builder, plan: PlotPlan) -> None:
    df = plan.series[0].data_var  # 棒グラフは全系列が同じデータ元
    if plan.bar_x_index is None:
        b.add(f"x = pd.Series({df}.index)  # X は指定なし。行番号を使う")
    elif plan.datetime_x:
        b.add(
            f"x = {df}.iloc[:, {plan.bar_x_index}].dt.strftime({literal(plan.bar_date_format)})"
            "  # 日時を文字列にして、棒をカテゴリとして並べる"
        )
    else:
        b.add(f"x = {df}.iloc[:, {plan.bar_x_index}]")


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
            if p.y_err is not None:
                with b.step(*_error_step(p, p.y_err)):
                    _emit_error_columns(b, p, p.y_err)
            b.add(f"{_target(p)}.bar(x[ok], y[ok], {_style_args(s)}, label={literal(p.legend_label)}{_bar_error_args(s, p)})")
        return

    n = len(plan.series)
    b.add("# 複数の系列を、X の値ごとに横に並べた棒グラフにする（X は共通）")
    with b.step(GENERIC_ERROR_MESSAGE):
        _emit_bar_x(b, plan)
        for p in plan.series:
            if p.y_err is not None:
                with b.step(*_error_step(p, p.y_err)):
                    _emit_error_columns(b, p, p.y_err, f"y{p.number}")
        b.add("bar_data = pd.DataFrame({")
        b.add('    "x": x,')
        for p in plan.series:
            b.add(f'    "y{p.number}": pd.to_numeric({p.data_var}.iloc[:, {p.y_index}], errors="coerce"),  # {_column_comment(p, "y")}')
            if p.y_err is not None and p.y_err.mode == "column":
                for name in dict.fromkeys(_error_names(p.y_err, f"y{p.number}")):
                    b.add(f'    "{name}": {name},')
        b.add("})")
        keys = ", ".join(literal(f"y{p.number}") for p in plan.series)
        b.add(f'bar_data = bar_data.dropna(subset=[{keys}], how="all")  # 全ての系列が欠けている行は描かない')
        for p in plan.series:
            if p.y_err is not None and p.y_err.mode == "column":
                for name in dict.fromkeys(_error_names(p.y_err, f"y{p.number}")):
                    b.add(f'bar_data["{name}"] = bar_data["{name}"].where(bar_data["y{p.number}"].notna())  # 棒を描かない行のエラーバーも描かない')
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
                f"{_style_args(s)}, label={literal(p.legend_label)}{_bar_error_args(s, p, f'y{p.number}')})"
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


_AXIS_NAMES = {"x": "X", "y": "Y", "y2": "第2Y"}
_INVERT_NOTES = {"x": "右が小さい値", "y": "上が小さい値", "y2": "上が小さい値"}
_DATE_LOCATORS = {
    "year": ("YearLocator", "base", "年"),
    "month": ("MonthLocator", "interval", "か月"),
    "day": ("DayLocator", "interval", "日"),
    "hour": ("HourLocator", "interval", "時間"),
    "minute": ("MinuteLocator", "interval", "分"),
    "second": ("SecondLocator", "interval", "秒"),
}


@dataclass(frozen=True)
class _AxisBlock:
    var: str  # Axes の変数名（ax / ax2）
    which: str  # x / y（軸の向き）
    name: str  # x / y / y2（設定上の軸）
    label: str  # X / Y / 第2Y
    axis: AxisSettings
    plan: AxisPlan


def _axis_blocks(settings: Settings, plan: PlotPlan) -> list[_AxisBlock]:
    blocks = [
        _AxisBlock("ax", "x", "x", "X", settings.axes.x, plan.axes.x),
        _AxisBlock("ax", "y", "y", "Y", settings.axes.y, plan.axes.y),
    ]
    if plan.uses_secondary and plan.axes.y2 is not None:
        blocks.append(_AxisBlock("ax2", "y", "y2", "第2Y", settings.axes.y2, plan.axes.y2))
    return blocks


def _per_axis_minor(plan: PlotPlan) -> bool:
    """副目盛を軸ごとに書くか（どれかの軸が「自動」でないとき）。すべて「自動」なら、今までの書き方（ax.minorticks_on() など）。"""
    return any(a is not None and a.minor != "auto" for a in (plan.axes.x, plan.axes.y, plan.axes.y2))


def _uses_ticker(settings: Settings, plan: PlotPlan) -> bool:
    return any("ticker." in line for blk in _axis_blocks(settings, plan) for line in _axis_tick_lines(blk, settings, plan))


def _scale_lines(blk: _AxisBlock, plan: PlotPlan) -> list[str]:
    """スケールと範囲。X が日時の列のときは、日時の範囲（pd.Timestamp）。"""
    var, which, axis = blk.var, blk.which, blk.axis
    if blk.plan.kind == "datetime":
        limits = [
            f"{k}=pd.Timestamp({literal(v)})" for k, v in (("left", blk.plan.date_min), ("right", blk.plan.date_max)) if v
        ]
        return [f"{var}.set_xlim({', '.join(limits)})"] if limits else []
    return _axis_lines(var, which, axis.scale, axis.min, axis.max)


def _major_lines(blk: _AxisBlock, settings: Settings, plan: PlotPlan) -> list[str]:
    ap, axis_var = blk.plan, f"{blk.var}.{blk.which}axis"
    label = blk.label
    if ap.kind == "datetime":
        fmt = settings.axes.x.date_format
        if ap.major_step is None:
            if fmt:
                return [f"{axis_var}.set_major_formatter(mdates.DateFormatter({literal(fmt)}))  # 日時の表示書式"]
            return [
                "# X が日時の列: 範囲に合わせて目盛の間隔と表示を自動で決める",
                "date_locator = mdates.AutoDateLocator()",
                f"{axis_var}.set_major_locator(date_locator)",
                f"{axis_var}.set_major_formatter(mdates.ConciseDateFormatter(date_locator))",
            ]
        func, kwarg, unit_name = _DATE_LOCATORS[ap.major_step_unit]
        formatter = f"mdates.DateFormatter({literal(fmt)})" if fmt else "mdates.ConciseDateFormatter(date_locator)"
        return [
            f"date_locator = mdates.{func}({kwarg}={literal(ap.major_step)})  # {label}軸の主目盛: {ap.major_step}{unit_name}ごと",
            f"{axis_var}.set_major_locator(date_locator)",
            f"{axis_var}.set_major_formatter({formatter})",
        ]
    if ap.kind == "category":
        if plan.plot_type == "bar" and len(plan.series) > 1:
            return []  # 複数系列の棒は、棒の位置に目盛を付ける節（tick_step）で扱う
        if ap.major_step is not None:
            return [f"{axis_var}.set_major_locator(ticker.MultipleLocator({literal(ap.major_step)}))  # {label}軸の主目盛: {ap.major_step}個おきにラベルを出す"]
        if plan.plot_type in {"line", "scatter"} and plan.thin_categorical_x:
            return [
                "# X が文字列の列: 目盛に X の値を出す（25個を超えるので間引く）",
                f"{axis_var}.set_major_locator(ticker.MaxNLocator(nbins=25, integer=True))",
            ]
        return []
    lines = []
    if ap.major_step is not None:
        lines.append(f"{axis_var}.set_major_locator(ticker.MultipleLocator({literal(ap.major_step)}))  # {label}軸の主目盛: {comment_text(literal(ap.major_step))} ごと")
    fmt = ap.tick_format
    if fmt == "auto":
        return lines
    d = ap.tick_decimals
    formatter = f"{blk.name}_formatter"
    if fmt == "fixed":
        lines.append(f'{axis_var}.set_major_formatter(ticker.FormatStrFormatter({literal(f"%.{d}f")}))  # {label}軸の数字: 小数 {d} 桁')
    elif fmt == "sci":
        lines.append(f'{axis_var}.set_major_formatter(ticker.FormatStrFormatter({literal(f"%.{d}e")}))  # {label}軸の数字: 指数表記（小数 {d} 桁）')
    elif ap.kind == "log":
        lines.append(f"{axis_var}.set_major_formatter(ticker.LogFormatterSciNotation())  # {label}軸の数字: 10^n 表記")
    else:
        lines += [
            f"{formatter} = ticker.ScalarFormatter(useMathText=True)  # {label}軸の数字: 10^n 表記（軸の端に ×10^n をまとめて書く）",
            f"{formatter}.set_powerlimits((0, 0))",
            f"{axis_var}.set_major_formatter({formatter})",
        ]
    if ap.kind == "log":
        lines.append(f"{axis_var}.set_minor_formatter(ticker.NullFormatter())  # 副目盛の数字は消す")
    return lines


def _minor_lines(blk: _AxisBlock, grid_minor: bool) -> list[str]:
    ap, axis_var, label = blk.plan, f"{blk.var}.{blk.which}axis", blk.label
    if ap.minor == "on":
        if ap.minor_divisions is not None and ap.kind != "log":
            n = ap.minor_divisions
            return [f"{axis_var}.set_minor_locator(ticker.AutoMinorLocator({literal(n)}))  # {label}軸の副目盛: 主目盛の間を {n} 等分"]
        return [f"{axis_var}.minorticks_on()  # {label}軸の副目盛を表示する"]
    if ap.minor == "off":
        return [f"{axis_var}.minorticks_off()  # {label}軸の副目盛は出さない"]
    if grid_minor:
        return [f"{axis_var}.minorticks_on()  # {label}軸の副目盛を表示する（副目盛線を表示するため）"]
    if ap.kind == "log":
        return [f"{axis_var}.minorticks_off()  # 対数軸の補助目盛は出さない"]
    return []


def _axis_tick_lines(blk: _AxisBlock, settings: Settings, plan: PlotPlan) -> list[str]:
    """1つの軸の目盛の行（主目盛 → 書式 → 副目盛（軸ごとに書くときだけ）→ 反転）。Axes の変数名と AxisPlan だけで決まる。"""
    lines = _major_lines(blk, settings, plan)
    if _per_axis_minor(plan):
        lines += _minor_lines(blk, settings.plot.grid_minor)
    if blk.plan.inverted:
        lines.append(f"{blk.var}.invert_{blk.which}axis()  # {blk.label}軸を反転する（{_INVERT_NOTES[blk.name]}）")
    return lines


def _emit_spines(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    plot = settings.plot
    if not plot.spine_top:
        b.add('ax.spines["top"].set_visible(False)  # 上の枠線を消す')
        if plan.uses_secondary:
            b.add('ax2.spines["top"].set_visible(False)')
    if not plot.spine_right and not plan.uses_secondary:  # 第2Y軸があるときの右の枠線は、第2Y軸の線なので消せない
        b.add('ax.spines["right"].set_visible(False)  # 右の枠線を消す')


def _emit_axes(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    b.section("5. 軸（ラベル・スケール・範囲・目盛）")
    plot, axes = settings.plot, settings.axes
    if plot.title:
        b.add(f"ax.set_title({literal(plot.title)}, fontsize=FONT_SIZE + 2)")
    b.add(f"ax.set_xlabel({literal(axes.x.label or plan.x_label)}, fontsize=FONT_SIZE)")
    b.add(f"ax.set_ylabel({literal(axes.y.label or plan.y_label)}, fontsize=FONT_SIZE)")
    if plan.uses_secondary:
        b.add(f"ax2.set_ylabel({literal(axes.y2.label or plan.y2_label)}, fontsize=FONT_SIZE)")

    # 軸ごとに: スケール → 範囲 → 主目盛・書式 → 副目盛 → 反転（スケールを変えると目盛の設定が戻るので、この順）
    for blk in _axis_blocks(settings, plan):
        lines = _scale_lines(blk, plan)
        if lines:
            with b.step(axis_error_message(blk.label), f"{blk.label}軸の範囲"):
                b.add(*lines)
        ticks = _axis_tick_lines(blk, settings, plan)
        if ticks:
            with b.step(tick_error_message(blk.label), f"{blk.label}軸の目盛"):
                b.add(*ticks)

    if plan.plot_type == "bar" and len(plan.series) > 1:
        step = plan.axes.x.major_step
        if step is not None:
            b.add(
                f"# 棒の位置に X の値を目盛として付ける（X軸の主目盛の間隔: {step}個おき）",
                f"tick_step = {literal(step)}",
            )
        else:
            b.add(
                "# 棒の位置に X の値を目盛として付ける（25個を超えるときは間引く）",
                "tick_step = max(1, len(positions) // 25)",
            )
        b.add(
            "ax.set_xticks(positions[::tick_step])",
            'ax.set_xticklabels(x_labels[::tick_step], rotation=45, ha="right")',
        )

    size = _label_size_expr(plot.font_size)
    b.add("# 目盛は内向きにする", f'ax.tick_params(which="both", direction="in", labelsize={size})')
    if plan.uses_secondary:
        b.add(f'ax2.tick_params(which="both", direction="in", labelsize={size})')

    if not plot.grid_minor and not _per_axis_minor(plan):
        if axes.x.scale == "log" or axes.y.scale == "log":
            b.add("ax.minorticks_off()  # 対数軸の補助目盛は出さない")
        if plan.uses_secondary and axes.y2.scale == "log":
            b.add("ax2.minorticks_off()")
    _emit_spines(b, settings, plan)


def _emit_grid_and_legend(b: _Builder, settings: Settings, plan: PlotPlan) -> None:
    b.section("6. グリッドと凡例")
    plot = settings.plot
    if plot.grid_minor and not _per_axis_minor(plan):  # 軸ごとの副目盛の指定があるときは、5. 軸で書いた（minorticks_on() は軸ごとの指定を上書きする）
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


def generate_script(settings: Settings, source, plan: PlotPlan) -> GeneratedScript:
    """設定・読み込んだファイルの情報・描画計画から、完全なスクリプトを作る。

    source は SourceInfo（1つ）または {ファイル id: SourceInfo}（plan.sources のすべてを含む）。"""
    if isinstance(source, SourceInfo):
        source = {src.id: source for src in plan.sources}
    infos = [source[src.id] for src in plan.sources]
    b = _Builder()
    _emit_header(b, infos, settings.plot.latin_font, plan, settings)
    b.add(f"FONT_SIZE = {literal(settings.plot.font_size)}  # 文字の大きさ（pt）")
    if _uses_error_function(plan):
        b.blank()
        b.add(*ERROR_BAR_FUNCTION)
    _emit_load(b, plan, infos)
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
