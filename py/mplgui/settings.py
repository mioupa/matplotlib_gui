"""設定オブジェクト（JSON, camelCase, version=4）の既定値・検証・型付きデータクラス。

JS 側の js/defaults.js と default_settings() は同一でなければならない（単体テストで比較する）。
このモジュールは js / pyodide / pyscript に依存しない。
"""
from __future__ import annotations

import copy
import math
import re
from datetime import datetime
from dataclasses import dataclass, field, replace
from typing import Any

from matplotlib.colors import is_color_like

from . import expr as expr_module
from .errors import UserError

SCHEMA_VERSION = 4

PLOT_TYPES = ("line", "scatter", "bar", "step", "barh", "barStacked", "hist", "scatterColor", "box", "violin", "heatmap")
# 種類ごとに画面で隠す設定は、検証せず使わない（要件 §2.2。docs/PHASE5_DESIGN.md §6.2・§7.3）。js/chart-types.js と揃えること
XY_TYPES = ("line", "step", "scatter", "scatterColor")  # 点の形・塗りつぶし帯・X 方向のエラーバー・近似曲線を使う（系列ごとの X と Y の組で描く）
BOX_TYPES = ("box", "violin")  # 系列ごとに1つの箱・胴を描く（横軸は系列の名前）
CATEGORY_BAR_TYPES = ("bar", "barStacked", "barh")  # 全系列共通の X列（plot.xColumn）を使う
SERIES_X_TYPES = XY_TYPES + ("heatmap",)  # 系列ごとの X 列を使う
NO_Y2_TYPES = ("barh", "barStacked", "hist", "scatterColor") + BOX_TYPES + ("heatmap",)  # 第2Y軸を使わない
NO_Y_ERROR_TYPES = ("barStacked", "hist") + BOX_TYPES + ("heatmap",)  # Y 方向のエラーバーを使わない
COLOR_COLUMN_TYPES = ("scatterColor", "heatmap")  # 色分けの列（ヒートマップでは値の列）を使う
HEATMAP_SERIES_MESSAGE = "ヒートマップは系列1つで描きます。系列を1つにしてください。"
STEP_WHERE_CHOICES = ("pre", "mid", "post")
COLORMAPS = ("viridis", "cividis", "plasma", "inferno", "magma", "coolwarm", "RdBu_r", "gray")
MAX_HIST_BINS = 1000
MAX_HEATMAP_SIZE = 500  # ヒートマップの X・Y の異なる値の上限（それぞれ）
LINE_STYLES = ("solid", "dashed", "dashdot", "dotted")
SCALES = ("linear", "log")
SAVE_FORMATS = ("png", "jpg", "svg", "pdf")
FIGURE_UNITS = ("in", "cm", "mm")
LATIN_FONTS = ("default", "arimo", "tinos")
PALETTES = ("ud", "tab10", "gray")  # 色そのものは JS 側だけが持つ。Python は選択肢を検証するだけ
SVG_TEXT_MODES = ("path", "text")
DEFAULT_DPI = 300
MIN_DPI = 50
MAX_DPI = 1200
# 1 インチあたりの長さ。インチへは「値 / これ」で直す（生成コードと同じ割り算。1 / 2.54 を掛けると 20.32 cm が 7.999… inch になる）
_UNITS_PER_INCH = {"in": 1.0, "cm": 2.54, "mm": 25.4}
LEGEND_LOCATIONS = (
    "best",
    "upper right",
    "upper left",
    "lower right",
    "lower left",
    "upper center",
    "lower center",
    "center right",
    "center left",
    "center",
    "none",
)
DEFAULT_SCATTER_MARKER_SIZE = 24.0
THOUSANDS_CHOICES = ("", ",", ".", " ", "'")
DECIMAL_CHOICES = (".", ",")
MAX_SKIP_LINES = 1_000_000
MAX_FILES = 10
MAX_DATE_FORMAT_LENGTH = 64
_FILE_ID_RE = re.compile(r"d[0-9]{1,4}")
DATE_UNITS = ("year", "month", "day", "hour", "minute", "second")
MINOR_TICKS_CHOICES = ("auto", "on", "off")
TICK_FORMATS = ("auto", "fixed", "sci", "pow10")
ERROR_MODES = ("none", "fixed", "column")
MAX_CAP_SIZE = 50
_COLUMN_RE = re.compile(r"__idx__[0-9]+")
MARKERS = ("auto", "none", "o", "s", "^", "v", "D", "x", "+", "*")
ANNOTATION_KINDS = ("text", "hline", "vline", "hspan", "vspan")
ANNOTATION_COORDS = ("data", "axes")
ANNOTATION_AXES = ("y", "y2")
FIT_MODELS = ("linear", "poly", "custom")
FIT_SHOWS = ("legend", "text", "none")
MAX_ANNOTATIONS = 50
MAX_FITS = 20
MAX_COMPUTED = 20
MAX_COMPUTED_NAME = 50
MAX_ANNOTATION_TEXT = 200
_DATE_INPUT_RE = re.compile(r"(\d{4})([-/])(\d{1,2})\2(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?")
DATE_RANGE_LABEL = "X軸の範囲（日時）"

_DEFAULT_ERROR_SPEC = {"mode": "none", "symmetric": True, "value": None, "valueMinus": None, "column": "", "columnMinus": ""}
_DEFAULT_TICKS = {
    "majorStep": None,
    "minorTicks": "auto",
    "minorDivisions": None,
    "tickFormat": "auto",
    "tickDecimals": 1,
    "inverted": False,
}

_DEFAULT_FILL = {"lower": "", "upper": "", "alpha": 0.25}
_DEFAULT_ANNOTATION = {
    "id": "a1",
    "kind": "hline",
    "text": "",
    "x": "",
    "y": "",
    "start": "",
    "end": "",
    "coords": "data",
    "axis": "y",
    "color": "#000000",
    "lineStyle": "dashed",
    "lineWidth": 1,
    "alpha": None,
    "fontSize": None,
    "label": "",
}
_DEFAULT_COMPUTED = {"id": "", "source": "", "name": "", "expr": ""}
_DEFAULT_FIT = {
    "id": "f1", "series": "s1", "model": "linear", "degree": 2, "show": "legend", "color": "", "lineStyle": "dashed",
    "expr": "", "initial": {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1},
}

_DEFAULT_SERIES = {
    "id": "s1",
    "x": "",
    "y": "",
    "color": "#FF4B00",
    "lineWidth": 2,
    "lineStyle": "solid",
    "markerSize": None,
    "label": "",
    "secondaryAxis": False,
    "source": "",
    "errorBars": {"y": copy.deepcopy(_DEFAULT_ERROR_SPEC), "x": copy.deepcopy(_DEFAULT_ERROR_SPEC), "capSize": 3},
    "marker": "auto",
    "alpha": 1,
    "fill": copy.deepcopy(_DEFAULT_FILL),
    "colorColumn": "",
}


def default_annotation() -> dict:
    """注釈1つの既定値（js/defaults.js の DEFAULT_ANNOTATION と同一）。"""
    return copy.deepcopy(_DEFAULT_ANNOTATION)


def default_computed() -> dict:
    """計算した列1つの既定値（js/defaults.js の DEFAULT_COMPUTED と同一）。"""
    return copy.deepcopy(_DEFAULT_COMPUTED)


def default_fit() -> dict:
    """近似曲線1つの既定値（js/defaults.js の DEFAULT_FIT と同一）。"""
    return copy.deepcopy(_DEFAULT_FIT)


def default_settings() -> dict:
    """既定の設定（JSON 互換の dict）。呼ぶたびに新しい dict を返す。"""
    return {
        "version": SCHEMA_VERSION,
        "load": {
            "delimiter": "",
            "hasHeader": True,
            "skipLines": 0,
            "thousands": "",
            "decimal": ".",
            "comment": "",
            "parseDates": True,
            "files": [],
        },
        "plot": {
            "type": "line",
            "skipRows": 0,
            "xColumn": "",
            "title": "",
            "fontSize": 15,
            "figure": {"width": 8, "height": 6, "unit": "in"},
            "latinFont": "default",
            "palette": "ud",
            "legend": {"location": "best"},
            "grid": {"major": False, "minor": False},
            "margins": {"left": None, "right": None, "bottom": None, "top": None},
            "spines": {"top": True, "right": True},
            "step": {"where": "post"},
            "hist": {"bins": None, "density": False},
            "colormap": "viridis",
            "colorbarLabel": "",
            "box": {"fliers": True, "means": False},
            "violin": {"medians": True, "means": False},
        },
        "axes": {
            "x": {
                "label": "", "scale": "linear", "min": None, "max": None, "dateFormat": "",
                **copy.deepcopy(_DEFAULT_TICKS), "majorStepUnit": "day", "dateMin": "", "dateMax": "",
            },
            "y": {"label": "", "scale": "linear", "min": None, "max": None, **copy.deepcopy(_DEFAULT_TICKS)},
            "y2": {"label": "", "scale": "linear", "min": None, "max": None, **copy.deepcopy(_DEFAULT_TICKS)},
        },
        "series": [copy.deepcopy(_DEFAULT_SERIES)],
        "annotations": [],
        "fits": [],
        "computed": [],
        "save": {"filename": "", "format": "png", "transparent": False, "dpi": DEFAULT_DPI, "svgText": "path"},
    }


# ---------------------------------------------------------------- dataclasses


@dataclass(frozen=True)
class FileEntry:
    id: str
    name: str = ""
    sheet: str = ""  # "" = 先頭シート


@dataclass(frozen=True)
class LoadSettings:
    delimiter: str = ""
    has_header: bool = True
    skip_lines: int = 0
    thousands: str = ""
    decimal: str = "."
    comment: str = ""
    parse_dates: bool = True
    files: tuple[FileEntry, ...] = ()


@dataclass(frozen=True)
class AxisSettings:
    label: str = ""
    scale: str = "linear"
    min: float | None = None
    max: float | None = None
    date_format: str = ""  # X 軸だけ。"" = 自動
    major_step: float | None = None  # None = 自動
    major_step_unit: str = "day"  # X 軸だけ。日時の X のときの間隔の単位
    minor_ticks: str = "auto"  # auto / on / off
    minor_divisions: int | None = None  # None = 自動
    tick_format: str = "auto"  # auto / fixed / sci / pow10
    tick_decimals: int = 1
    inverted: bool = False
    date_min: str = ""  # X 軸だけ。日時の X の範囲（正規化済み。"" = 指定なし）
    date_max: str = ""


@dataclass(frozen=True)
class FigureSettings:
    width: float = 8.0  # unit で指定した単位の値
    height: float = 6.0
    unit: str = "in"

    @property
    def width_in(self) -> float:
        return self.width / _UNITS_PER_INCH[self.unit]

    @property
    def height_in(self) -> float:
        return self.height / _UNITS_PER_INCH[self.unit]


@dataclass(frozen=True)
class MarginSettings:
    left: float | None = None
    right: float | None = None
    bottom: float | None = None
    top: float | None = None

    def provided(self) -> dict:
        return {k: v for k, v in (("left", self.left), ("right", self.right), ("bottom", self.bottom), ("top", self.top)) if v is not None}


@dataclass(frozen=True)
class PlotSettings:
    type: str = "line"
    skip_rows: int = 0
    x_column: str = ""
    title: str = ""
    font_size: float = 15.0
    figure: FigureSettings = field(default_factory=FigureSettings)
    latin_font: str = "default"
    palette: str = "ud"
    legend_location: str = "best"
    grid_major: bool = False
    grid_minor: bool = False
    margins: MarginSettings = field(default_factory=MarginSettings)
    spine_top: bool = True  # 上の枠線を表示する
    spine_right: bool = True  # 右の枠線を表示する（第2Y軸があるときは無視）
    step_where: str = "post"  # step のときだけ使う: pre / mid / post
    hist_bins: int | None = None  # hist のときだけ使う: None = 自動（numpy の "auto"）
    hist_density: bool = False  # hist のときだけ使う: 縦軸を確率密度にする
    colormap: str = "viridis"  # scatterColor / heatmap のときだけ使う
    colorbar_label: str = ""  # scatterColor / heatmap のときだけ使う（"" = 系列1の色分けの列（値の列）の名前）
    box_fliers: bool = True  # box のときだけ使う: 外れ値の点を描く
    box_means: bool = False  # box のときだけ使う: 平均の印を描く
    violin_medians: bool = True  # violin のときだけ使う: 中央値の線を描く
    violin_means: bool = False  # violin のときだけ使う: 平均の線を描く


@dataclass(frozen=True)
class AxesSettings:
    x: AxisSettings = field(default_factory=AxisSettings)
    y: AxisSettings = field(default_factory=AxisSettings)
    y2: AxisSettings = field(default_factory=AxisSettings)


@dataclass(frozen=True)
class ErrorSpec:
    """片方向（Y または X）のエラーバーの指定。value / column が「上（右）」、*_minus が「下（左）」。"""

    mode: str = "none"  # none / fixed / column
    symmetric: bool = True
    value: float | None = None
    value_minus: float | None = None
    column: str = ""  # "__idx__N"
    column_minus: str = ""


@dataclass(frozen=True)
class ErrorBarSettings:
    y: ErrorSpec = field(default_factory=ErrorSpec)
    x: ErrorSpec = field(default_factory=ErrorSpec)
    cap_size: float = 3.0


@dataclass(frozen=True)
class FillSettings:
    """塗りつぶし帯（fill_between）。lower / upper は "__idx__N"。両方空なら帯なし。"""

    lower: str = ""
    upper: str = ""
    alpha: float = 0.25

    @property
    def enabled(self) -> bool:
        return bool(self.lower and self.upper)


@dataclass(frozen=True)
class SeriesSettings:
    id: str = "s1"
    x: str = ""
    y: str = ""
    color: str = "#FF4B00"
    line_width: float = 2.0
    line_style: str = "solid"
    marker_size: float | None = None  # None = プロット種別ごとの自動値
    label: str = ""
    secondary_axis: bool = False
    source: str = ""  # データ元のファイル id（"" = load.files の先頭）
    error_bars: ErrorBarSettings = field(default_factory=ErrorBarSettings)
    marker: str = "auto"  # auto / none / o / s / ^ / v / D / x / + / *（棒グラフでは使わない）
    alpha: float = 1.0  # 不透明度（1 = 透けない）
    fill: FillSettings = field(default_factory=FillSettings)  # 棒グラフでは使わない
    color_column: str = ""  # "__idx__N"。scatterColor / heatmap（値の列）のときだけ使う（必須）

    def effective_marker_size(self, plot_type: str) -> float:
        """自動(None)は line / step=0 / それ以外=24。scatter / scatterColor で 0 以下なら 24 に補正する。"""
        size = self.marker_size
        if size is None:
            return 0.0 if plot_type in {"line", "step"} else DEFAULT_SCATTER_MARKER_SIZE
        if plot_type in {"scatter", "scatterColor"} and size <= 0:
            return DEFAULT_SCATTER_MARKER_SIZE
        return float(size)


@dataclass(frozen=True)
class AnnotationSettings:
    """注釈1つ。位置（x / y / start / end）は入力欄の文字のまま持つ（軸の種類で解釈するのは dataprep）。種類で使わない項目は既定値。"""

    id: str = "a1"
    kind: str = "hline"  # text / hline / vline / hspan / vspan
    text: str = ""
    x: str = ""
    y: str = ""
    start: str = ""
    end: str = ""
    coords: str = "data"  # text だけ: data / axes
    axis: str = "y"  # y / y2（Y を使う種類で、第2Y軸を使うときだけ）
    color: str = "#000000"
    line_style: str = "dashed"
    line_width: float = 1.0
    alpha: float | None = None  # None = 自動（帯 0.2、それ以外 1）
    font_size: float | None = None  # None = 図のフォントサイズ
    label: str = ""


@dataclass(frozen=True)
class FitSettings:
    id: str = "f1"
    series: str = "s1"  # 系列の id
    model: str = "linear"
    degree: int = 1  # linear は 1、poly は 2〜6
    show: str = "legend"  # legend / text / none
    color: str = ""  # "" = 系列の色
    line_style: str = "dashed"
    # custom（任意の式）のときだけ使う。expr_node は解釈済みの式、params は使うパラメータ（a〜e の順）、initial はその初期値
    expr: str = ""
    expr_node: Any = field(default=None, compare=False, repr=False)
    params: tuple[str, ...] = ()
    initial: tuple[float, ...] = ()


@dataclass(frozen=True)
class ComputedSettings:
    """計算した列1つ。式は解釈済み（expr_node）で、設定の検証の時点で構文の誤りを UserError にする。"""

    id: str = "c1"
    source: str = ""  # "" = load.files の先頭
    name: str = ""  # "" = 「計算N」
    expr: str = ""
    expr_node: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class SaveSettings:
    filename: str = ""
    format: str = "png"
    transparent: bool = False
    dpi: int = DEFAULT_DPI
    svg_text: str = "path"


@dataclass(frozen=True)
class Settings:
    version: int = SCHEMA_VERSION
    load: LoadSettings = field(default_factory=LoadSettings)
    plot: PlotSettings = field(default_factory=PlotSettings)
    axes: AxesSettings = field(default_factory=AxesSettings)
    series: tuple[SeriesSettings, ...] = ()
    save: SaveSettings = field(default_factory=SaveSettings)
    annotations: tuple[AnnotationSettings, ...] = ()
    fits: tuple[FitSettings, ...] = ()
    computed: tuple[ComputedSettings, ...] = ()

    @property
    def uses_secondary_axis(self) -> bool:
        return any(s.secondary_axis for s in self.series)


# ---------------------------------------------------------------- coercion helpers


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _to_float(value: Any) -> float | None:
    """数値 | 数値文字列 → float。変換できなければ None（bool・NaN・inf も不可）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        try:
            num = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return num if math.isfinite(num) else None


def _number(value: Any, label: str, *, default: float | None = None, minimum: float | None = None,
            exclusive_min: float | None = None, maximum: float | None = None, owner: str = "",
            field_name: str | None = None) -> float | None:
    """数値項目を検証する。空(None/空文字)は default を返す（None なら None）。"""
    name = f"{owner}「{label}」"
    field_name = field_name or label
    if _is_blank(value):
        return default
    num = _to_float(value)
    if num is None:
        raise UserError(f"{name}は数値で入力してください。", field=field_name)
    if exclusive_min is not None and num <= exclusive_min:
        raise UserError(f"{name}は{_fmt(exclusive_min)}より大きい数値で入力してください。", field=field_name)
    if minimum is not None and num < minimum:
        raise UserError(f"{name}は{_fmt(minimum)}以上の数値で入力してください。", field=field_name)
    if maximum is not None and num > maximum:
        raise UserError(f"{name}は{_fmt(maximum)}以下の数値で入力してください。", field=field_name)
    return num


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def _integer(value: Any, label: str, *, default: int = 0, minimum: int = 0) -> int:
    if _is_blank(value):
        return default
    num = _to_float(value)
    if num is None or not num.is_integer():
        raise UserError(f"「{label}」は{minimum}以上の整数で入力してください。", field=label)
    if num < minimum:
        raise UserError(f"「{label}」は{minimum}以上の整数で入力してください。", field=label)
    return int(num)


def _string(value: Any, label: str, *, owner: str = "") -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise UserError(f"{owner}「{label}」は文字列で指定してください。", field=label)
    return value


def _boolean(value: Any, label: str, *, owner: str = "") -> bool:
    if isinstance(value, bool):
        return value
    raise UserError(f"{owner}「{label}」の値が不正です。", field=label)


def _choice(value: Any, label: str, choices: tuple[str, ...], *, owner: str = "", field_name: str | None = None) -> str:
    if not isinstance(value, str) or value not in choices:
        raise UserError(f"{owner}「{label}」の値が不正です。", field=field_name or label)
    return value


def _merge(defaults: dict, given: Any) -> dict:
    """given の値で defaults を再帰的に上書きする（欠けているキーは既定値）。given が dict でなければ既定値。"""
    out = copy.deepcopy(defaults)
    if not isinstance(given, dict):
        return out
    for key, value in given.items():
        if key in out and isinstance(out[key], dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


MAX_FIGURE_INCH = 50  # これより大きいと画像サイズが過大になり描画できない


def migrate_settings(raw: dict) -> dict:
    """古いバージョンの設定を現在のバージョンにする（純粋。引数は変更しない）。

    バージョンが無いものは現在のバージョンとして扱う。対応していないバージョンは UserError。
    - 1 → 2: 保存 DPI を追加する。v1 は常に 120 dpi で保存していたので、同じ出力になるよう 120 にする。
      図の単位・欧文フォント・カラーパレット・SVG の文字は、既定値で補われる。
    - 2 → 3: データ取り込みの項目（読み飛ばす行数・桁区切り・小数点・コメント記号・複数ファイル・
      系列のデータ元・X 軸の日時の書式）を追加する。日時の自動認識（load.parseDates）は、v2 までの
      出力を保つため false にする（v3 で新しく作る設定の既定値は true）。他の項目は既定値で補われる。
    - 3 → 4: 目盛・枠線・日時の範囲・エラーバーの項目を追加する。version を 4 にするだけ
      （新しい項目の既定値は、v3 までの出力を変えない値なので、既定値で補われる）。
    """
    version = raw.get("version", SCHEMA_VERSION)
    if isinstance(version, bool) or version not in (1, 2, 3, SCHEMA_VERSION):
        raise UserError(f"設定のバージョン（{version}）に対応していません。ページを再読み込みしてください。", field="version")
    out = copy.deepcopy(raw)
    if version == 1:
        save = out.get("save")
        if not isinstance(save, dict):
            save = {}
        if "dpi" not in save:
            save["dpi"] = 120
        out["save"] = save
    if version != SCHEMA_VERSION:
        out["version"] = SCHEMA_VERSION
    if version in (1, 2):
        load = out.get("load")
        if not isinstance(load, dict):
            load = {}
        if "parseDates" not in load:
            load["parseDates"] = False
        out["load"] = load
    return out


# ---------------------------------------------------------------- parsing


def parse_load_settings(raw: dict | None) -> LoadSettings:
    """読み込み設定だけを検証する（描画設定の不備でファイル読込を止めないため）。"""
    raw = migrate_settings(raw if isinstance(raw, dict) else {})
    load = _merge(default_settings()["load"], raw.get("load"))
    skip_lines = _integer(load["skipLines"], "ヘッダより前に読み飛ばす行数", default=0, minimum=0)
    if skip_lines > MAX_SKIP_LINES:
        raise UserError(f"「ヘッダより前に読み飛ばす行数」は{MAX_SKIP_LINES}以下の整数で入力してください。", field="ヘッダより前に読み飛ばす行数")
    thousands = _choice(load["thousands"], "桁区切り", THOUSANDS_CHOICES)
    decimal = _choice(load["decimal"], "小数点", DECIMAL_CHOICES)
    if thousands and thousands == decimal:
        raise UserError("「桁区切り」と「小数点」に同じ記号は使えません。", field="桁区切り")
    comment = _parse_comment(load["comment"], thousands, decimal)
    return LoadSettings(
        delimiter=_string(load["delimiter"], "区切り文字"),
        has_header=_boolean(load["hasHeader"], "先頭行をヘッダとして扱う"),
        skip_lines=skip_lines,
        thousands=thousands,
        decimal=decimal,
        comment=comment,
        parse_dates=_boolean(load["parseDates"], "日時の列を自動で認識する"),
        files=_parse_files(load["files"]),
    )


def _parse_comment(value: Any, thousands: str, decimal: str) -> str:
    label = "コメント記号"
    if value is None:
        return ""
    if not isinstance(value, str):
        raise UserError(f"「{label}」は文字列で指定してください。", field=label)
    if value == "":
        return ""
    if len(value) != 1:
        raise UserError(f"「{label}」は1文字で指定してください（例: #）。", field=label)
    if value == '"' or value.isspace():
        raise UserError(f"「{label}」に \" や空白は使えません。", field=label)
    if value in (thousands, decimal):
        raise UserError(f"「{label}」に、桁区切り・小数点と同じ記号は使えません。", field=label)
    return value


def _parse_files(raw_files: Any) -> tuple[FileEntry, ...]:
    label = "読み込むファイル"
    if not isinstance(raw_files, list):
        raise UserError(f"「{label}」の値が不正です。", field=label)
    if len(raw_files) > MAX_FILES:
        raise UserError(f"読み込めるファイルは{MAX_FILES}個までです。", field=label)
    out = []
    seen: set[str] = set()
    for item in raw_files:
        if not isinstance(item, dict):
            raise UserError(f"「{label}」の値が不正です。", field=label)
        fid = item.get("id")
        if not isinstance(fid, str) or not _FILE_ID_RE.fullmatch(fid):
            raise UserError(f"「{label}」のIDが不正です。", field=label)
        if fid in seen:
            raise UserError(f"「{label}」のIDが重複しています。", field=label)
        seen.add(fid)
        out.append(
            FileEntry(
                id=fid,
                name=_string(item.get("name", ""), "ファイル名", owner="読み込むファイルの"),
                sheet=_string(item.get("sheet", ""), "シート", owner="読み込むファイルの"),
            )
        )
    return tuple(out)


def _parse_axis(raw: dict, key: str, name: str, *, ticks: bool = True, linear: bool = False) -> AxisSettings:
    """ticks が False のとき（使っていない第2Y軸）は、目盛の項目を検証せず既定値にする（隠れた不正な値で描画を止めないため）。"""
    axis = raw[key]
    lo = _number(axis["min"], f"{name}軸の最小値", default=None)
    hi = _number(axis["max"], f"{name}軸の最大値", default=None)
    scale = "linear" if linear else _choice(axis["scale"], f"{name}軸スケール", SCALES)  # linear: スケールを隠している軸（横棒の縦軸）
    date_format = _date_format(axis["dateFormat"]) if key == "x" else ""
    base = AxisSettings(label=_string(axis["label"], f"{name}軸ラベル").strip(), scale=scale, min=lo, max=hi, date_format=date_format)
    if not ticks:
        return base
    # 隠れている項目（対数軸の主目盛の間隔、副目盛が「表示」でないときの分割数、書式が小数・指数でないときの桁数）は
    # 使わないので検証せず、既定値にする（隠れた不正な値で描画を止めないため。§2.2）
    major_step = _number(axis["majorStep"], f"{name}軸の主目盛の間隔", default=None, exclusive_min=0) if scale == "linear" else None
    minor_ticks = _choice(axis["minorTicks"], f"{name}軸の副目盛", MINOR_TICKS_CHOICES)
    tick_format = _choice(axis["tickFormat"], f"{name}軸の目盛の書式", TICK_FORMATS)
    extra: dict[str, Any] = {
        "major_step": major_step,
        "minor_ticks": minor_ticks,
        "minor_divisions": (
            _int_range(axis["minorDivisions"], f"{name}軸の副目盛の分割数", 2, 10, default=None) if minor_ticks == "on" else None
        ),
        "tick_format": tick_format,
        "tick_decimals": (
            _int_range(axis["tickDecimals"], f"{name}軸の目盛の小数の桁数", 0, 10, default=1)
            if tick_format in {"fixed", "sci"}
            else 1
        ),
        "inverted": _boolean(axis["inverted"], f"{name}軸を反転"),
    }
    if key == "x":
        extra["major_step_unit"] = _choice(axis["majorStepUnit"], f"{name}軸の主目盛の単位", DATE_UNITS)
        # 日時の範囲は X が日時の列のときだけ使う（隠れているときは描画を止めない）。検証は dataprep（validate_date_range）
        extra["date_min"] = _lenient_date_range(axis["dateMin"])
        extra["date_max"] = _lenient_date_range(axis["dateMax"])
    return replace(base, **extra)


def _int_range(value: Any, label: str, lo: int, hi: int, *, default: int | None, owner: str = "") -> int | None:
    """lo〜hi の整数（整数に見える数値・数値文字列も可）。空欄は default。"""
    if _is_blank(value):
        return default
    num = _to_float(value)
    if num is None or not num.is_integer() or not lo <= num <= hi:
        raise UserError(f"{owner}「{label}」は{lo}〜{hi}の整数で入力してください。", field=label)
    return int(num)


_DATE_EXAMPLE = "2026-01-31 または 2026-01-31 12:00"


def _date_range_value(value: Any, which: str) -> str:
    """X 軸の日時の範囲（年が先頭の日付・日時）。正規化して返す（時刻なしは YYYY-MM-DD、あれば YYYY-MM-DD HH:MM:SS）。"""
    if _is_blank(value):
        return ""
    bad = UserError(
        f"「{DATE_RANGE_LABEL}」の{which}が正しくありません。年が先頭の日付か日時で入力してください（例: {_DATE_EXAMPLE}）。",
        field=DATE_RANGE_LABEL,
    )
    if not isinstance(value, str):
        raise bad
    m = _DATE_INPUT_RE.fullmatch(value.strip())
    if not m:
        raise bad
    y, _, mo, d, hh, mi, ss = m.groups()
    try:
        moment = datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0), int(ss or 0))
    except ValueError:
        raise bad from None
    return moment.strftime("%Y-%m-%d" if hh is None else "%Y-%m-%d %H:%M:%S")


def _lenient_date_range(value: Any) -> str:
    """正しければ正規化した値、そうでなければ前後の空白を除いた元の文字列（検証は X が日時のときだけ）。"""
    try:
        return _date_range_value(value, "")
    except UserError:
        return value.strip() if isinstance(value, str) else str(value)


def validate_date_range(axis: AxisSettings) -> tuple[str, str]:
    """X が日時の列のときの X 軸の範囲（日時）の検証。(最小, 最大)（正規化済み。指定なしは ""）を返す。"""
    date_min = _date_range_value(axis.date_min, "最小値")
    date_max = _date_range_value(axis.date_max, "最大値")
    if date_min and date_max and _date_value(date_min) >= _date_value(date_max):
        raise UserError(f"{DATE_RANGE_LABEL}は最小値 < 最大値で指定してください。", field=DATE_RANGE_LABEL)
    return date_min, date_max


def _date_value(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S" if " " in text else "%Y-%m-%d")


def _date_format(value: Any) -> str:
    label = "X軸の日時の書式"
    if value is None:
        return ""
    bad = UserError(f"「{label}」が正しくありません。%Y/%m/%d のように、% で始まる指定を含めてください。", field=label)
    if not isinstance(value, str) or len(value) > MAX_DATE_FORMAT_LENGTH:
        raise bad
    if value == "":
        return ""
    if "%" not in value:
        raise bad
    try:
        datetime(2024, 1, 31, 13, 45, 30).strftime(value)
    except (ValueError, TypeError, OverflowError):
        raise bad from None
    return value


def check_axis_range(axis: AxisSettings, name: str) -> None:
    if axis.min is not None and axis.max is not None and axis.min >= axis.max:
        raise UserError(f"{name}軸の範囲は最小値 < 最大値で指定してください。", field=f"{name}軸の範囲")
    if axis.scale == "log" and ((axis.min is not None and axis.min <= 0) or (axis.max is not None and axis.max <= 0)):
        raise UserError(f"{name}軸を対数にする場合、範囲は0より大きい値で指定してください。", field=f"{name}軸の範囲")


def _error_label(axis: str, symmetric: bool, what: str, side: int) -> str:
    """エラーバーの項目名。axis は Y / X、what は 値 / 列、side は 0=上（右）/ 1=下（左）。"""
    if symmetric:
        return f"{axis}誤差の{what}"
    pair = ("上", "下") if axis == "Y" else ("右", "左")
    return f"{axis}誤差（{pair[side]}）の{what}"


def _parse_error_spec(raw: dict, axis: str, owner: str) -> ErrorSpec:
    mode = _choice(raw["mode"], f"{axis}誤差の方式", ERROR_MODES, owner=owner)
    if mode == "none":
        return ErrorSpec()
    symmetric = _boolean(raw["symmetric"], f"{axis}誤差を上下で同じ値にする" if axis == "Y" else f"{axis}誤差を左右で同じ値にする", owner=owner)
    sides = (0,) if symmetric else (0, 1)
    if mode == "fixed":
        values = []
        for side, key in zip(sides, ("value", "valueMinus")):
            label = _error_label(axis, symmetric, "値", side)
            if _is_blank(raw[key]):
                raise UserError(f"{owner}「{label}」を入力してください。", field=label)
            values.append(_number(raw[key], label, minimum=0, owner=owner))
        return ErrorSpec(mode=mode, symmetric=symmetric, value=values[0], value_minus=values[1] if not symmetric else None)
    columns = []
    for side, key in zip(sides, ("column", "columnMinus")):
        label = _error_label(axis, symmetric, "列", side)
        value = raw[key]
        if not isinstance(value, str) or not value.strip():
            raise UserError(f"{owner}「{label}」を選んでください。", field=label)
        if not _COLUMN_RE.fullmatch(value.strip()):
            raise UserError(f"{owner}「{label}」の指定が正しくありません。列を選び直してください。", field=label)
        columns.append(value.strip())
    return ErrorSpec(mode=mode, symmetric=symmetric, column=columns[0], column_minus=columns[1] if not symmetric else "")


def _parse_error_bars(raw: dict, plot_type: str, owner: str) -> ErrorBarSettings:
    if plot_type in NO_Y_ERROR_TYPES:  # 積み上げ棒・ヒストグラム・箱ひげ・バイオリン・ヒートマップはエラーバーを両方向とも隠すので、何も検証しない
        return ErrorBarSettings()
    cap = _number(raw["capSize"], "エラーバーの端の長さ", default=3.0, minimum=0, maximum=MAX_CAP_SIZE, owner=owner)
    return ErrorBarSettings(
        y=ErrorSpec() if plot_type in NO_Y_ERROR_TYPES else _parse_error_spec(raw["y"], "Y", owner),  # 積み上げ棒・ヒストグラムでは Y 方向を隠す
        x=_parse_error_spec(raw["x"], "X", owner) if plot_type in XY_TYPES else ErrorSpec(),  # X 方向は XY の種類だけ
        cap_size=cap,
    )


def _parse_fill(raw: dict, owner: str) -> FillSettings:
    field_name = f"{owner}塗りつぶし帯"
    columns = []
    for key, what in (("lower", "下端"), ("upper", "上端")):
        value = raw[key]
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise UserError(f"{owner}「塗りつぶし帯の{what}」の指定が正しくありません。列を選び直してください。", field=field_name)
        value = value.strip()
        if value and not _COLUMN_RE.fullmatch(value):
            raise UserError(f"{owner}「塗りつぶし帯の{what}」の指定が正しくありません。列を選び直してください。", field=field_name)
        columns.append(value)
    lower, upper = columns
    if not lower and not upper:
        return FillSettings()  # 帯なし。不透明度は使わないので検証しない
    if not lower or not upper:
        missing = "下端" if not lower else "上端"
        raise UserError(f"{owner}「塗りつぶし帯」は、下端と上端の両方の列を選んでください（{missing}が未選択です）。", field=field_name)
    alpha = _number(raw["alpha"], "塗りつぶし帯の不透明度", default=0.25, minimum=0, maximum=1, owner=owner, field_name=field_name)
    return FillSettings(lower=lower, upper=upper, alpha=alpha)


def _parse_color_column(value: Any, owner: str, what: str = "色分けの列") -> str:
    """色分けの列（scatterColor では「色分けの列」、heatmap では「値の列」。どちらも必須）。"""
    field_name = f"{owner}{what}"
    if value is None or (isinstance(value, str) and not value.strip()):
        raise UserError(f"{owner}{what}を選んでください。", field=field_name)
    if not isinstance(value, str) or not _COLUMN_RE.fullmatch(value.strip()):
        raise UserError(f"{owner}「{what}」の指定が正しくありません。列を選び直してください。", field=field_name)
    return value.strip()


def _parse_series(raw_series: Any, plot_type: str = "line") -> tuple[SeriesSettings, ...]:
    if not isinstance(raw_series, list) or not raw_series:
        raise UserError("描画系列を1つ以上追加してください。", field="描画系列")
    if plot_type == "heatmap" and len(raw_series) > 1:  # 系列ごとの検証（値の列が未選択など）より先に知らせる
        raise UserError(HEATMAP_SERIES_MESSAGE, field="系列")
    out = []
    used_ids: set[str] = set()
    for i, given in enumerate(raw_series):
        n = i + 1
        owner = f"系列{n}の"
        s = _merge(_DEFAULT_SERIES, given)
        sid = s["id"] if isinstance(s["id"], str) and s["id"] and s["id"] not in used_ids else f"s{n}"
        while sid in used_ids:
            sid += "_"
        used_ids.add(sid)
        heat = plot_type == "heatmap"  # ヒートマップは色・線幅・線種・点サイズを隠す（カラーマップを使う）。検証せず使わない
        box = plot_type in BOX_TYPES  # 箱ひげ・バイオリンは点サイズ・線種を隠す
        color = _DEFAULT_SERIES["color"]
        line_width = 2.0
        if not heat:
            color = _string(s["color"], "色", owner=owner).strip() or _DEFAULT_SERIES["color"]
            if not is_color_like(color):
                raise UserError(f"{owner}「色」が不正です。", field="色")
            line_width = _number(s["lineWidth"], "線幅", default=2.0, exclusive_min=0, owner=owner)
        marker = None if (heat or box) else _number(s["markerSize"], "点サイズ", default=None, minimum=0, owner=owner)
        line_style = "solid" if (heat or box) else _choice(s["lineStyle"], "線種", LINE_STYLES, owner=owner)
        marker_shape = "auto"
        fill = FillSettings()
        if plot_type in XY_TYPES:  # 点の形と塗りつぶし帯は XY の種類だけ。ほかは隠すので、検証せず使わない
            marker_shape = _choice(s["marker"], "点の形", MARKERS, owner=owner, field_name=f"{owner}点の形")
            if plot_type in {"scatter", "scatterColor"} and marker_shape == "none":
                raise UserError(
                    f"{owner}「点の形」を「なし」にすると、散布図の点が見えなくなります。点の形を選んでください。", field=f"{owner}点の形"
                )
            fill = _parse_fill(s["fill"], owner)
        color_column = ""
        if plot_type in COLOR_COLUMN_TYPES:
            color_column = _parse_color_column(s["colorColumn"], owner, "値の列" if heat else "色分けの列")
        out.append(
            SeriesSettings(
                id=sid,
                x=_string(s["x"], "X列", owner=owner).strip(),
                y=_string(s["y"], "Y列", owner=owner).strip(),
                color=color,
                line_width=line_width,
                line_style=line_style,
                marker_size=marker,
                label=_string(s["label"], "凡例名", owner=owner).strip(),
                # 横棒・積み上げ棒・ヒストグラム・色分け散布図では第2Y軸を隠す（false として扱い、検証しない）
                secondary_axis=False if plot_type in NO_Y2_TYPES else _boolean(s["secondaryAxis"], "第2軸を使用", owner=owner),
                source=_string(s["source"], "データ元", owner=owner),
                error_bars=_parse_error_bars(s["errorBars"], plot_type, owner),
                marker=marker_shape,
                alpha=_number(s["alpha"], "不透明度", default=1.0, minimum=0, maximum=1, owner=owner, field_name=f"{owner}不透明度"),
                fill=fill,
                color_column=color_column,
            )
        )
    return tuple(out)


def _position_text(value: Any, label: str, field_name: str) -> str:
    """位置の入力（x / y / start / end）。文字列で持つ（数値は文字列にする）。解釈は dataprep。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        raise UserError(f"「{label}」の値が不正です。", field=field_name)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise UserError(f"「{label}」の値が不正です。", field=field_name)
        return repr(value)
    if isinstance(value, str):
        return value.strip()
    raise UserError(f"「{label}」の値が不正です。", field=field_name)


def _parse_annotations(raw: Any, y2_used: bool) -> tuple[AnnotationSettings, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise UserError("「注釈」の値が不正です。", field="注釈")
    if len(raw) > MAX_ANNOTATIONS:
        raise UserError(f"注釈は{MAX_ANNOTATIONS}個までです。", field="注釈")
    out = []
    used_ids: set[str] = set()
    for i, given in enumerate(raw):
        n = i + 1
        owner = f"注釈{n}の"

        def f(label: str) -> str:
            return f"{owner}{label}"

        a = _merge(_DEFAULT_ANNOTATION, given)
        aid = a["id"] if isinstance(a["id"], str) and a["id"] and a["id"] not in used_ids else f"a{n}"
        while aid in used_ids:
            aid += "_"
        used_ids.add(aid)
        kind = _choice(a["kind"], "種類", ANNOTATION_KINDS, owner=owner, field_name=f("種類"))
        color = _string(a["color"], "色", owner=owner).strip() or _DEFAULT_ANNOTATION["color"]
        if not is_color_like(color):
            raise UserError(f"{owner}「色」が不正です。", field=f("色"))
        alpha = _number(a["alpha"], "不透明度", default=None, minimum=0, maximum=1, owner=owner, field_name=f("不透明度"))
        values: dict[str, Any] = {"id": aid, "kind": kind, "color": color, "alpha": alpha}
        # 種類で使わない項目は検証せず、既定値にする（隠れた不正な値で描画を止めないため。§2.2）
        if kind == "text":
            text = _string(a["text"], "文字", owner=owner)
            if len(text) > MAX_ANNOTATION_TEXT:
                raise UserError(f"{owner}「文字」は{MAX_ANNOTATION_TEXT}文字以内で入力してください。", field=f("文字"))
            coords = _choice(a["coords"], "座標", ANNOTATION_COORDS, owner=owner, field_name=f("座標"))
            values.update(
                text=text,
                coords=coords,
                x=_position_text(a["x"], "X", f("X")),
                y=_position_text(a["y"], "Y", f("Y")),
                font_size=_number(a["fontSize"], "文字の大きさ", default=None, exclusive_min=0, owner=owner, field_name=f("文字の大きさ")),
            )
        else:
            if kind == "vline":
                values["x"] = _position_text(a["x"], "X", f("X"))
            elif kind == "hline":
                values["y"] = _position_text(a["y"], "Y", f("Y"))
            else:
                values["start"] = _position_text(a["start"], "開始", f("開始"))
                values["end"] = _position_text(a["end"], "終了", f("終了"))
            values["label"] = _string(a["label"], "凡例名", owner=owner).strip()
            if kind in {"hline", "vline"}:
                values["line_style"] = _choice(a["lineStyle"], "線種", LINE_STYLES, owner=owner, field_name=f("線種"))
                values["line_width"] = _number(
                    a["lineWidth"], "線幅", default=1.0, exclusive_min=0, owner=owner, field_name=f("線幅")
                )
        uses_y = kind in {"hline", "hspan"} or (kind == "text" and values.get("coords") == "data")
        if uses_y and y2_used:
            values["axis"] = _choice(a["axis"], "軸", ANNOTATION_AXES, owner=owner, field_name=f("軸"))
        out.append(AnnotationSettings(**values))
    return tuple(out)


def _parse_fits(raw: Any, series_ids: set[str]) -> tuple[FitSettings, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise UserError("「近似曲線」の値が不正です。", field="近似曲線")
    if len(raw) > MAX_FITS:
        raise UserError(f"近似曲線は{MAX_FITS}本までです。", field="近似曲線")
    out = []
    used_ids: set[str] = set()
    for i, given in enumerate(raw):
        n = i + 1
        owner = f"近似曲線{n}の"
        f = _merge(_DEFAULT_FIT, given)
        fid = f["id"] if isinstance(f["id"], str) and f["id"] and f["id"] not in used_ids else f"f{n}"
        while fid in used_ids:
            fid += "_"
        used_ids.add(fid)
        series = f["series"]
        if not isinstance(series, str) or series not in series_ids:
            raise UserError(f"{owner}系列が見つかりません。近似する系列を選び直してください。", field=f"{owner}系列")
        model = _choice(f["model"], "モデル", FIT_MODELS, owner=owner, field_name=f"{owner}モデル")
        degree = 1
        if model == "poly":
            degree = _int_range(f["degree"], f"{owner}次数", 2, 6, default=2)
        expr_text, node, params, initial = "", None, (), ()
        if model == "custom":
            expr_text = _string(f["expr"], "式", owner=owner)
            if not expr_text.strip():
                raise UserError(f"近似曲線{n}の式を入力してください。", field=f"近似曲線{n}の式")
            try:
                node = expr_module.parse_model(expr_text)
            except expr_module.ExprError as e:
                raise UserError(f"近似曲線{n}の式: {e}", field=f"近似曲線{n}の式") from None
            params = expr_module.model_params(node)
            given_initial = f["initial"] if isinstance(f["initial"], dict) else {}
            initial = tuple(
                _number(
                    given_initial.get(name, 1), f"初期値（{name}）", default=1.0, owner=owner,
                    field_name=f"{owner}初期値（{name}）",
                )
                for name in params
            )
        color = _string(f["color"], "色", owner=owner).strip()
        if color and not is_color_like(color):
            raise UserError(f"{owner}「色」が不正です。", field=f"{owner}色")
        out.append(
            FitSettings(
                id=fid,
                series=series,
                model=model,
                degree=degree,
                show=_choice(f["show"], "式の表示先", FIT_SHOWS, owner=owner, field_name=f"{owner}式の表示先"),
                color=color,
                line_style=_choice(f["lineStyle"], "線種", LINE_STYLES, owner=owner, field_name=f"{owner}線種"),
                expr=expr_text,
                expr_node=node,
                params=params,
                initial=initial,
            )
        )
    return tuple(out)


def _parse_computed(raw: Any, file_ids: set[str]) -> tuple[ComputedSettings, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise UserError("「計算した列」の値が不正です。", field="計算した列")
    if len(raw) > MAX_COMPUTED:
        raise UserError(f"計算した列は{MAX_COMPUTED}個までです。", field="計算した列")
    out = []
    used_ids: set[str] = set()
    for i, given in enumerate(raw):
        n = i + 1
        owner = f"計算した列{n}の"
        c = _merge(_DEFAULT_COMPUTED, given)
        cid = c["id"] if isinstance(c["id"], str) and c["id"] and c["id"] not in used_ids else f"c{n}"
        while cid in used_ids:
            cid += "_"
        used_ids.add(cid)
        source = _string(c["source"], "データ元", owner=owner)
        if source and source not in file_ids:
            raise UserError(f"計算した列{n}のデータ元が見つかりません。データ元を選び直してください。", field=f"計算した列{n}のデータ元")
        name = _string(c["name"], "名前", owner=owner).strip()
        if len(name) > MAX_COMPUTED_NAME:
            raise UserError(f"{owner}「名前」は{MAX_COMPUTED_NAME}文字以内で入力してください。", field=f"計算した列{n}の名前")
        expr = _string(c["expr"], "式", owner=owner)
        if not expr.strip():
            raise UserError(f"計算した列{n}の式を入力してください。", field=f"計算した列{n}の式")
        try:
            node = expr_module.parse(expr)
        except expr_module.ExprError as e:
            raise UserError(f"計算した列{n}の式: {e}", field=f"計算した列{n}の式") from None
        out.append(ComputedSettings(id=cid, source=source, name=name, expr=expr, expr_node=node))
    return tuple(out)


def parse_settings(raw: dict | None) -> Settings:
    """設定 dict を検証し、型付きの Settings にする。欠けているキーは既定値で補う。

    不正な値は UserError（日本語・項目名つき）。
    """
    raw = migrate_settings(raw if isinstance(raw, dict) else {})
    d = default_settings()
    merged = {
        "load": _merge(d["load"], raw.get("load")),
        "plot": _merge(d["plot"], raw.get("plot")),
        "axes": _merge(d["axes"], raw.get("axes")),
        "save": _merge(d["save"], raw.get("save")),
    }
    load = parse_load_settings(raw)

    p = merged["plot"]
    fig = p["figure"] if isinstance(p["figure"], dict) else {}
    unit = _choice(fig.get("unit", "in"), "図のサイズの単位", FIGURE_UNITS)
    figure = FigureSettings(
        width=_figure_length(fig.get("width"), "図幅", 8.0, unit),
        height=_figure_length(fig.get("height"), "図高さ", 6.0, unit),
        unit=unit,
    )
    legend = p["legend"] if isinstance(p["legend"], dict) else {}
    grid = p["grid"] if isinstance(p["grid"], dict) else {}
    m = p["margins"] if isinstance(p["margins"], dict) else {}
    spines = p["spines"] if isinstance(p["spines"], dict) else {}
    margin_labels = (("left", "余白 左(left)"), ("right", "余白 右(right)"), ("bottom", "余白 下(bottom)"), ("top", "余白 上(top)"))
    margin_values = {}
    for key, label in margin_labels:
        value = _number(m.get(key), label, default=None)
        if value is not None and not 0 <= value <= 1:
            raise UserError(f"「{label}」は0〜1の数値で入力してください。", field=label)
        margin_values[key] = value
    margins = MarginSettings(**margin_values)
    if margins.left is not None and margins.right is not None and margins.left >= margins.right:
        raise UserError("余白は left < right になるように指定してください。", field="余白")
    if margins.bottom is not None and margins.top is not None and margins.bottom >= margins.top:
        raise UserError("余白は bottom < top になるように指定してください。", field="余白")

    plot_type = _choice(p["type"], "プロット種別", PLOT_TYPES)
    step_where, hist_bins, hist_density, colormap, colorbar_label = "post", None, False, "viridis", ""
    box_fliers, box_means, violin_medians, violin_means = True, False, True, False
    if plot_type == "step":
        step = p["step"] if isinstance(p["step"], dict) else {}
        step_where = _choice(step.get("where", "post"), "段の付き方", STEP_WHERE_CHOICES)
    elif plot_type == "hist":
        hist = p["hist"] if isinstance(p["hist"], dict) else {}
        hist_bins = _int_range(hist.get("bins"), "区間の数", 1, MAX_HIST_BINS, default=None)
        hist_density = _boolean(hist.get("density", False), "確率密度")
    elif plot_type in COLOR_COLUMN_TYPES:
        colormap = _choice(p["colormap"], "カラーマップ", COLORMAPS)
        colorbar_label = _string(p["colorbarLabel"], "カラーバーのラベル").strip()
    elif plot_type == "box":
        box = p["box"] if isinstance(p["box"], dict) else {}
        box_fliers = _boolean(box.get("fliers", True), "外れ値の点")
        box_means = _boolean(box.get("means", False), "平均の印")
    elif plot_type == "violin":
        violin = p["violin"] if isinstance(p["violin"], dict) else {}
        violin_medians = _boolean(violin.get("medians", True), "中央値の線")
        violin_means = _boolean(violin.get("means", False), "平均の線")

    plot = PlotSettings(
        type=plot_type,
        skip_rows=_integer(p["skipRows"], "除外する先頭行数", default=0, minimum=0),
        x_column="" if plot_type in {"hist", "box", "violin", "heatmap"} else _string(p["xColumn"], "X列").strip(),  # ヒストグラム・箱ひげ・バイオリン・ヒートマップは X列を隠す
        title=_string(p["title"], "タイトル").strip(),
        font_size=_number(p["fontSize"], "フォントサイズ", default=15.0, exclusive_min=0),
        figure=figure,
        latin_font=_choice(p["latinFont"], "欧文フォント", LATIN_FONTS),
        palette=_choice(p["palette"], "カラーパレット", PALETTES),
        legend_location=_choice(legend.get("location", "best"), "凡例位置", LEGEND_LOCATIONS),
        grid_major=_boolean(grid.get("major", False), "主目盛線を表示"),
        grid_minor=_boolean(grid.get("minor", False), "副目盛線を表示"),
        margins=margins,
        spine_top=_boolean(spines.get("top", True), "上の枠線"),
        spine_right=_boolean(spines.get("right", True), "右の枠線"),
        step_where=step_where,
        hist_bins=hist_bins,
        hist_density=hist_density,
        colormap=colormap,
        colorbar_label=colorbar_label,
        box_fliers=box_fliers,
        box_means=box_means,
        violin_medians=violin_medians,
        violin_means=violin_means,
    )

    ax = merged["axes"]
    raw_series = raw.get("series", d["series"])
    y2_used = (
        plot.type not in NO_Y2_TYPES
        and isinstance(raw_series, list)
        and any(isinstance(s, dict) and s.get("secondaryAxis") is True for s in raw_series)
    )
    axes = AxesSettings(
        x=_parse_axis(ax, "x", "X", linear=plot.type in BOX_TYPES),  # 箱ひげ・バイオリンの横軸はカテゴリなので、X のスケールは使わない
        y=_parse_axis(ax, "y", "Y", linear=plot.type == "barh"),  # 横棒の縦軸はカテゴリなので、Y のスケールは使わない
        y2=_parse_axis(ax, "y2", "第2Y", ticks=y2_used),
    )
    series = _parse_series(raw_series, plot.type)
    file_ids = {f.id for f in load.files}
    for i, s in enumerate(series):
        if s.source and s.source not in file_ids:
            raise UserError(f"系列{i + 1}のデータ元が見つかりません。データ元を選び直してください。", field=f"系列{i + 1}のデータ元")
    # X の数値の範囲は、X が日時の列のときは使わない（隠れている）ので、dataprep が軸の種類を見て検査する
    check_axis_range(axes.y, "Y")
    if any(s.secondary_axis for s in series):
        check_axis_range(axes.y2, "第2Y")

    annotations = _parse_annotations(raw.get("annotations"), any(s.secondary_axis for s in series))
    # XY の種類以外では近似曲線を使わない（隠れているので検証しない）
    fits = _parse_fits(raw.get("fits"), {s.id for s in series}) if plot.type in XY_TYPES else ()

    # 計算した列は常に表示されるので、グラフの種類によらず検証する
    computed = _parse_computed(raw.get("computed"), file_ids)

    save = _parse_save(merged["save"])
    return Settings(
        version=SCHEMA_VERSION, load=load, plot=plot, axes=axes, series=series, save=save,
        annotations=annotations, fits=fits, computed=computed,
    )


def _figure_length(value: Any, label: str, default: float, unit: str) -> float:
    """図幅・図高さ。上限は 50 inch を選んだ単位に直した値（in: 50, cm: 127, mm: 1270）。"""
    num = _number(value, label, default=default, exclusive_min=0)
    limit = MAX_FIGURE_INCH * _UNITS_PER_INCH[unit]
    if num > limit + 1e-9:
        raise UserError(f"「{label}」は{_fmt(round(limit, 6))}以下の数値で入力してください（単位: {unit}）。", field=label)
    return num


def _dpi(value: Any) -> int:
    label = "保存 DPI"
    if _is_blank(value):
        return DEFAULT_DPI
    num = _to_float(value)
    if num is None or not num.is_integer() or not MIN_DPI <= num <= MAX_DPI:
        raise UserError(f"「{label}」は{MIN_DPI}〜{MAX_DPI}の整数で入力してください。", field=label)
    return int(num)


def _parse_save(sv: dict) -> SaveSettings:
    return SaveSettings(
        filename=_string(sv["filename"], "保存ファイル名").strip(),
        format=_choice(str(sv["format"]).strip().lower() if isinstance(sv["format"], str) else sv["format"], "保存形式", SAVE_FORMATS),
        transparent=_boolean(sv["transparent"], "背景を透過して保存"),
        dpi=_dpi(sv["dpi"]),
        svg_text=_choice(sv["svgText"], "SVG の文字", SVG_TEXT_MODES),
    )


def parse_save_settings(raw: dict | None) -> SaveSettings:
    """保存設定だけを検証する（編集モードの保存を、使わない描画設定の不備で止めないため）。"""
    raw = migrate_settings(raw if isinstance(raw, dict) else {})
    return _parse_save(_merge(default_settings()["save"], raw.get("save")))
