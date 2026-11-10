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

from .errors import UserError

SCHEMA_VERSION = 4

PLOT_TYPES = ("line", "scatter", "bar")
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
}


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

    def effective_marker_size(self, plot_type: str) -> float:
        """自動(None)は line=0 / それ以外=24。scatter で 0 以下なら 24 に補正する。"""
        size = self.marker_size
        if size is None:
            return 0.0 if plot_type == "line" else DEFAULT_SCATTER_MARKER_SIZE
        if plot_type == "scatter" and size <= 0:
            return DEFAULT_SCATTER_MARKER_SIZE
        return float(size)


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
            exclusive_min: float | None = None, maximum: float | None = None, owner: str = "") -> float | None:
    """数値項目を検証する。空(None/空文字)は default を返す（None なら None）。"""
    name = f"{owner}「{label}」"
    if _is_blank(value):
        return default
    num = _to_float(value)
    if num is None:
        raise UserError(f"{name}は数値で入力してください。", field=label)
    if exclusive_min is not None and num <= exclusive_min:
        raise UserError(f"{name}は{_fmt(exclusive_min)}より大きい数値で入力してください。", field=label)
    if minimum is not None and num < minimum:
        raise UserError(f"{name}は{_fmt(minimum)}以上の数値で入力してください。", field=label)
    if maximum is not None and num > maximum:
        raise UserError(f"{name}は{_fmt(maximum)}以下の数値で入力してください。", field=label)
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


def _choice(value: Any, label: str, choices: tuple[str, ...], *, owner: str = "") -> str:
    if not isinstance(value, str) or value not in choices:
        raise UserError(f"{owner}「{label}」の値が不正です。", field=label)
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


def _parse_axis(raw: dict, key: str, name: str, *, ticks: bool = True) -> AxisSettings:
    """ticks が False のとき（使っていない第2Y軸）は、目盛の項目を検証せず既定値にする（隠れた不正な値で描画を止めないため）。"""
    axis = raw[key]
    lo = _number(axis["min"], f"{name}軸の最小値", default=None)
    hi = _number(axis["max"], f"{name}軸の最大値", default=None)
    scale = _choice(axis["scale"], f"{name}軸スケール", SCALES)
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


def _check_axis_range(axis: AxisSettings, name: str) -> None:
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
    cap = _number(raw["capSize"], "エラーバーの端の長さ", default=3.0, minimum=0, maximum=MAX_CAP_SIZE, owner=owner)
    return ErrorBarSettings(
        y=_parse_error_spec(raw["y"], "Y", owner),
        x=ErrorSpec() if plot_type == "bar" else _parse_error_spec(raw["x"], "X", owner),  # 棒グラフでは X 方向を隠すので使わない
        cap_size=cap,
    )


def _parse_series(raw_series: Any, plot_type: str = "line") -> tuple[SeriesSettings, ...]:
    if not isinstance(raw_series, list) or not raw_series:
        raise UserError("描画系列を1つ以上追加してください。", field="描画系列")
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
        color = _string(s["color"], "色", owner=owner).strip() or _DEFAULT_SERIES["color"]
        if not is_color_like(color):
            raise UserError(f"{owner}「色」が不正です。", field="色")
        line_width = _number(s["lineWidth"], "線幅", default=2.0, exclusive_min=0, owner=owner)
        marker = _number(s["markerSize"], "点サイズ", default=None, minimum=0, owner=owner)
        out.append(
            SeriesSettings(
                id=sid,
                x=_string(s["x"], "X列", owner=owner).strip(),
                y=_string(s["y"], "Y列", owner=owner).strip(),
                color=color,
                line_width=line_width,
                line_style=_choice(s["lineStyle"], "線種", LINE_STYLES, owner=owner),
                marker_size=marker,
                label=_string(s["label"], "凡例名", owner=owner).strip(),
                secondary_axis=_boolean(s["secondaryAxis"], "第2軸を使用", owner=owner),
                source=_string(s["source"], "データ元", owner=owner),
                error_bars=_parse_error_bars(s["errorBars"], plot_type, owner),
            )
        )
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

    plot = PlotSettings(
        type=_choice(p["type"], "プロット種別", PLOT_TYPES),
        skip_rows=_integer(p["skipRows"], "除外する先頭行数", default=0, minimum=0),
        x_column=_string(p["xColumn"], "X列").strip(),
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
    )

    ax = merged["axes"]
    raw_series = raw.get("series", d["series"])
    y2_used = isinstance(raw_series, list) and any(isinstance(s, dict) and s.get("secondaryAxis") is True for s in raw_series)
    axes = AxesSettings(
        x=_parse_axis(ax, "x", "X"),
        y=_parse_axis(ax, "y", "Y"),
        y2=_parse_axis(ax, "y2", "第2Y", ticks=y2_used),
    )
    series = _parse_series(raw_series, plot.type)
    file_ids = {f.id for f in load.files}
    for i, s in enumerate(series):
        if s.source and s.source not in file_ids:
            raise UserError(f"系列{i + 1}のデータ元が見つかりません。データ元を選び直してください。", field=f"系列{i + 1}のデータ元")
    _check_axis_range(axes.x, "X")
    _check_axis_range(axes.y, "Y")
    if any(s.secondary_axis for s in series):
        _check_axis_range(axes.y2, "第2Y")

    save = _parse_save(merged["save"])
    return Settings(version=SCHEMA_VERSION, load=load, plot=plot, axes=axes, series=series, save=save)


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
