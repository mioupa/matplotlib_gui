"""設定オブジェクト（JSON, camelCase, version=1）の既定値・検証・型付きデータクラス。

JS 側の js/defaults.js と default_settings() は同一でなければならない（単体テストで比較する）。
このモジュールは js / pyodide / pyscript に依存しない。
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

from matplotlib.colors import is_color_like

from .errors import UserError

SCHEMA_VERSION = 1

PLOT_TYPES = ("line", "scatter", "bar")
LINE_STYLES = ("solid", "dashed", "dashdot", "dotted")
SCALES = ("linear", "log")
SAVE_FORMATS = ("png", "jpg", "svg", "pdf")
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
}


def default_settings() -> dict:
    """既定の設定（JSON 互換の dict）。呼ぶたびに新しい dict を返す。"""
    return {
        "version": SCHEMA_VERSION,
        "load": {"delimiter": "", "hasHeader": True},
        "plot": {
            "type": "line",
            "skipRows": 0,
            "xColumn": "",
            "title": "",
            "fontSize": 15,
            "figure": {"width": 8, "height": 6},
            "legend": {"location": "best"},
            "grid": {"major": False, "minor": False},
            "margins": {"left": None, "right": None, "bottom": None, "top": None},
        },
        "axes": {
            "x": {"label": "", "scale": "linear", "min": None, "max": None},
            "y": {"label": "", "scale": "linear", "min": None, "max": None},
            "y2": {"label": "", "scale": "linear", "min": None, "max": None},
        },
        "series": [copy.deepcopy(_DEFAULT_SERIES)],
        "save": {"filename": "", "format": "png", "transparent": False},
    }


# ---------------------------------------------------------------- dataclasses


@dataclass(frozen=True)
class LoadSettings:
    delimiter: str = ""
    has_header: bool = True


@dataclass(frozen=True)
class AxisSettings:
    label: str = ""
    scale: str = "linear"
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class FigureSettings:
    width: float = 8.0
    height: float = 6.0


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
    legend_location: str = "best"
    grid_major: bool = False
    grid_minor: bool = False
    margins: MarginSettings = field(default_factory=MarginSettings)


@dataclass(frozen=True)
class AxesSettings:
    x: AxisSettings = field(default_factory=AxisSettings)
    y: AxisSettings = field(default_factory=AxisSettings)
    y2: AxisSettings = field(default_factory=AxisSettings)


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


def _check_version(raw: dict) -> None:
    version = raw.get("version", SCHEMA_VERSION)
    if isinstance(version, bool) or version != SCHEMA_VERSION:
        raise UserError(f"設定のバージョン（{version}）に対応していません。ページを再読み込みしてください。", field="version")


# ---------------------------------------------------------------- parsing


def parse_load_settings(raw: dict | None) -> LoadSettings:
    """読み込み設定だけを検証する（描画設定の不備でファイル読込を止めないため）。"""
    raw = raw if isinstance(raw, dict) else {}
    _check_version(raw)
    load = _merge(default_settings()["load"], raw.get("load"))
    return LoadSettings(
        delimiter=_string(load["delimiter"], "区切り文字"),
        has_header=_boolean(load["hasHeader"], "先頭行をヘッダとして扱う"),
    )


def _parse_axis(raw: dict, key: str, name: str) -> AxisSettings:
    axis = raw[key]
    lo = _number(axis["min"], f"{name}軸の最小値", default=None)
    hi = _number(axis["max"], f"{name}軸の最大値", default=None)
    scale = _choice(axis["scale"], f"{name}軸スケール", SCALES)
    return AxisSettings(label=_string(axis["label"], f"{name}軸ラベル").strip(), scale=scale, min=lo, max=hi)


def _check_axis_range(axis: AxisSettings, name: str) -> None:
    if axis.min is not None and axis.max is not None and axis.min >= axis.max:
        raise UserError(f"{name}軸の範囲は最小値 < 最大値で指定してください。", field=f"{name}軸の範囲")
    if axis.scale == "log" and ((axis.min is not None and axis.min <= 0) or (axis.max is not None and axis.max <= 0)):
        raise UserError(f"{name}軸を対数にする場合、範囲は0より大きい値で指定してください。", field=f"{name}軸の範囲")


def _parse_series(raw_series: Any) -> tuple[SeriesSettings, ...]:
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
            )
        )
    return tuple(out)


def parse_settings(raw: dict | None) -> Settings:
    """設定 dict を検証し、型付きの Settings にする。欠けているキーは既定値で補う。

    不正な値は UserError（日本語・項目名つき）。
    """
    raw = raw if isinstance(raw, dict) else {}
    _check_version(raw)
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
    figure = FigureSettings(
        width=_number(fig.get("width"), "図幅", default=8.0, exclusive_min=0, maximum=MAX_FIGURE_INCH),
        height=_number(fig.get("height"), "図高さ", default=6.0, exclusive_min=0, maximum=MAX_FIGURE_INCH),
    )
    legend = p["legend"] if isinstance(p["legend"], dict) else {}
    grid = p["grid"] if isinstance(p["grid"], dict) else {}
    m = p["margins"] if isinstance(p["margins"], dict) else {}
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
        legend_location=_choice(legend.get("location", "best"), "凡例位置", LEGEND_LOCATIONS),
        grid_major=_boolean(grid.get("major", False), "主目盛線を表示"),
        grid_minor=_boolean(grid.get("minor", False), "副目盛線を表示"),
        margins=margins,
    )

    ax = merged["axes"]
    axes = AxesSettings(
        x=_parse_axis(ax, "x", "X"),
        y=_parse_axis(ax, "y", "Y"),
        y2=_parse_axis(ax, "y2", "第2Y"),
    )
    series = _parse_series(raw.get("series", d["series"]))
    _check_axis_range(axes.x, "X")
    _check_axis_range(axes.y, "Y")
    if any(s.secondary_axis for s in series):
        _check_axis_range(axes.y2, "第2Y")

    save = _parse_save(merged["save"])
    return Settings(version=SCHEMA_VERSION, load=load, plot=plot, axes=axes, series=series, save=save)


def _parse_save(sv: dict) -> SaveSettings:
    return SaveSettings(
        filename=_string(sv["filename"], "保存ファイル名").strip(),
        format=_choice(str(sv["format"]).strip().lower() if isinstance(sv["format"], str) else sv["format"], "保存形式", SAVE_FORMATS),
        transparent=_boolean(sv["transparent"], "背景を透過して保存"),
    )


def parse_save_settings(raw: dict | None) -> SaveSettings:
    """保存設定だけを検証する（編集モードの保存を、使わない描画設定の不備で止めないため）。"""
    raw = raw if isinstance(raw, dict) else {}
    _check_version(raw)
    return _parse_save(_merge(default_settings()["save"], raw.get("save")))
