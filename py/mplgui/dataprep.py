"""DataFrame の中身を見て決める処理（codegen に渡す描画計画 PlotPlan を作る）。

js / pyodide には依存しない。列指定は "__idx__N"（列番号）形式。
ここで決めるのは「データを見ないと分からないこと」だけ（Y 列の自動割り当て、X の数値変換の要否、
描ける点があるか、数値に変換できず除外した値の警告、データ由来のエラー）。コードの組み立ては codegen が行う。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from . import expr as expr_module
from .errors import UserError
from .loader import is_blank_cell as _is_blank_cell
from .loader import looks_numeric as _looks_numeric
from .settings import BAR_LIKE_TYPES, MAX_HIST_BINS, AxisSettings, ErrorSpec, Settings, check_axis_range, validate_date_range
from .settings import _DATE_EXAMPLE, _date_range_value, _to_float

MAX_EXAMPLES = 3
NO_DRAWABLE_DATA = "描画可能なデータがありません。"

# ---------------------------------------------------------------- dropped (non-numeric) values (A7)


def coerce_numeric(raw: pd.Series) -> tuple[pd.Series, int, list[str]]:
    """数値に変換する。戻り値は (変換後, 変換できなかった非空欄のセル数, 例（最大3件・重複なし）)。空欄は数えない。

    すでに数値型の列は、そのまま返す（NaN は空欄であり、変換の失敗ではない）。
    """
    if pd.api.types.is_numeric_dtype(raw.dtype):
        return raw, 0, []
    numeric = pd.to_numeric(raw, errors="coerce")
    blank = pd.Series([_is_blank_cell(v) for v in raw.tolist()], index=raw.index, dtype=bool)
    failed = numeric.isna() & ~blank
    count = int(failed.sum())
    examples: list[str] = []
    if count:
        for v in raw[failed].tolist():
            text = str(v)
            if text not in examples:
                examples.append(text)
            if len(examples) >= MAX_EXAMPLES:
                break
    return numeric, count, examples


_THOUSANDS_LIKE = re.compile(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?")  # 1,234 / -1,234,567.5
_DECIMAL_COMMA_LIKE = re.compile(r"[+-]?(\d+,\d+|\d{1,3}(\.\d{3})+,\d+)")  # 1,5 / 1.234,5
THOUSANDS_HINT = "（桁区切りのカンマなら、「データ読み込み」の「桁区切り」をカンマにしてください）"
DECIMAL_HINT = "（小数点がカンマなら、「データ読み込み」の「小数点」をカンマにしてください）"


def load_hint(examples: list[str], load) -> str:
    """除外した値の例が、桁区切り・小数点カンマの数に見えるのに読込設定がそうなっていないとき、設定の案内を返す。"""
    if load is None:
        return ""
    for text in examples:
        value = text.strip()
        if _THOUSANDS_LIKE.fullmatch(value):  # 両方に当てはまる 1,234 は桁区切りとして案内する
            if load.thousands != ",":
                return THOUSANDS_HINT
        elif _DECIMAL_COMMA_LIKE.fullmatch(value) and load.decimal != ",":
            return DECIMAL_HINT
    return ""


def dropped_warning(series_no: int, what: str, count: int, examples: list[str], load=None) -> dict:
    ex = ", ".join(f'"{e}"' for e in examples)
    message = f"{what}: 数値に変換できない値が{count}件あったため、その行を除外しました（例: {ex}）。{load_hint(examples, load)}"
    return {"series": series_no, "message": message}


def _no_data_message(warnings: list[dict]) -> str:
    base = "描画可能な数値データがありません。"
    if warnings:
        return base + "数値に変換できない値は除外されます。" + warnings[0]["message"]
    return base


# ---------------------------------------------------------------- columns


def parse_column_index(requested: str) -> int | None:
    if not requested.startswith("__idx__"):
        return None
    idx_text = requested.replace("__idx__", "", 1)
    if not idx_text.isdigit():
        return None
    return int(idx_text)


def _column_out_of_range(idx: int, ncols: int) -> str:
    return f"選択した列（{idx + 1}列目）がデータにありません（データは{ncols}列です）。別のファイルを読み込んだ場合は、列を選び直してください。"


def resolve_column_index(df: pd.DataFrame, requested: str) -> int:
    """列指定（"__idx__N" または列名）を列番号にする。見つからなければ UserError。"""
    if requested.startswith("__idx__"):
        idx = parse_column_index(requested)
        if idx is None:
            raise UserError("列の指定が正しくありません。列を選び直してください。", detail=requested)
        if idx >= len(df.columns):
            raise UserError(_column_out_of_range(idx, len(df.columns)))
        return idx
    for i, col in enumerate(df.columns):
        if col == requested or str(col) == requested:
            return i
    raise UserError(f"列「{requested}」がデータに見つかりません。列を選び直してください。")


def resolve_y_indices(df: pd.DataFrame, requests: list[str]) -> list[str]:
    """Y列が自動("")の系列に、未使用の最初の数値列を割り当てる。戻り値は列指定のリスト。"""
    numeric_indices = [i for i, dtype in enumerate(df.dtypes) if pd.api.types.is_numeric_dtype(dtype)]
    candidates = numeric_indices if numeric_indices else [0]
    used: set[int] = set()
    resolved = []
    for request in requests:
        if request:
            idx = parse_column_index(request)
            if idx is not None:
                used.add(idx)
            resolved.append(request)
            continue
        chosen = next((i for i in candidates if i not in used), candidates[0])
        used.add(chosen)
        resolved.append(f"__idx__{chosen}")
    return resolved


def slice_skip_rows(df_full: pd.DataFrame, skip_rows: int, label: str = "") -> pd.DataFrame:
    """label は複数ファイルのときのデータ元の名前（「データ2（b.csv）」）。1つのときは空。"""
    if skip_rows >= len(df_full):
        prefix = f"{label}: " if label else ""
        raise UserError(
            f"{prefix}スキップ行数がデータ行数以上です。「除外する先頭行数」を小さくしてください。", field="除外する先頭行数"
        )
    return df_full.iloc[skip_rows:].reset_index(drop=True)


# ---------------------------------------------------------------- plan


@dataclass(frozen=True)
class ErrorPlan:
    """片方向のエラーバー。列は系列のデータ元の列番号（誤差の列は「大きさ」で、0 以上）。"""

    direction: str  # "y" / "x"
    mode: str  # "fixed" / "column"
    symmetric: bool
    value: float | None = None  # fixed: 上（右）の値。対称なら下（左）にも使う
    value_minus: float | None = None  # fixed かつ非対称: 下（左）の値
    index: int | None = None  # column: 上（右）の列番号。対称なら下（左）にも使う
    index_minus: int | None = None  # column かつ非対称: 下（左）の列番号
    label: str = ""  # コメント用の列の表示（「名前 [番号]」）
    label_minus: str = ""


@dataclass(frozen=True)
class FillPlan:
    """塗りつぶし帯（fill_between）。列は系列のデータ元の列番号（値は下端・上端そのもの）。"""

    lower_index: int
    upper_index: int
    lower_label: str  # コメント用の列の表示（「名前 [番号]」）
    upper_label: str
    alpha: float


@dataclass(frozen=True)
class AnnotationPlan:
    """解釈済みの注釈。位置は、軸の種類で解釈した値（数値は float、日時の X は正規化した日付の文字列）。"""

    number: int  # 1 始まり
    kind: str  # text / hline / vline / hspan / vspan
    text: str = ""
    x: float | str | None = None  # text（データ座標・図の中の割合）と vline の X
    y: float | None = None  # text と hline の Y
    start: float | str | None = None  # hspan は Y、vspan は X の範囲
    end: float | str | None = None
    date: bool = False  # X 軸の値（x / vspan の start・end）が日時（pd.Timestamp で書く）
    coords: str = "data"  # text だけ
    target: str = "ax"  # ax / ax2
    color: str = "#000000"
    line_style: str = "dashed"
    line_width: float = 1.0
    alpha: float | None = None  # None = 自動（帯 0.2、それ以外 1）
    font_size: float | None = None  # None = FONT_SIZE
    label: str = ""


@dataclass(frozen=True)
class FitPlan:
    number: int  # 1 始まり
    series_number: int  # 近似する系列の番号（1 始まり）
    series_label: str  # コメント・凡例名用の系列の名前
    degree: int  # linear は 1
    show: str  # legend / text / none
    color: str  # 実際に使う色（"" だった場合は系列の色）
    line_style: str
    line_width: float
    label_prefix: str  # 凡例・図の中の文字の先頭（「温度の近似」）
    text_index: int  # show が text の近似曲線のうちの順番（0 始まり。それ以外は -1）
    target: str  # ax / ax2


@dataclass(frozen=True)
class SeriesPlan:
    number: int  # 1 始まり
    y_index: int
    y_name: str
    x_index: int | None  # None = 行番号
    x_label: str  # X 未指定は "index"
    data_label: str  # f"{name} [{idx}]"
    legend_label: str
    convert_x: bool  # X を pd.to_numeric で変換する（line / scatter のみ）
    categorical_x: bool  # line / scatter で X が数値でも日時でもない列（文字列）のまま使う
    marker_size: float
    has_points: bool
    secondary: bool
    datetime_x: bool = False  # X が日時の列（読み込み時に日時に変換済み）
    data_id: str = ""  # データ元のファイル id
    data_var: str = "df"  # 生成コードでこの系列が使う DataFrame の変数名（複数ファイルのときは df1, df2, ...）
    y_err: ErrorPlan | None = None  # Y 方向のエラーバー（指定が無ければ None）
    x_err: ErrorPlan | None = None  # X 方向のエラーバー（line / scatter のみ）
    cap_size: float = 3.0  # エラーバーの端の線の長さ
    marker: str = ""  # line は描く点の形（"" = 点なし）、scatter は "" = 既定の丸（引数を足さない）
    alpha: float = 1.0  # 不透明度（1 のときはコードに書かない）
    fill: FillPlan | None = None  # 塗りつぶし帯（line / step / scatter / scatterColor のみ）
    color_index: int | None = None  # scatterColor の色分けの列番号
    color_label: str = ""  # scatterColor の色分けの列の表示（「名前 [番号]」）


@dataclass(frozen=True)
class HistPlan:
    """ヒストグラム（hist）。区間の端は生成コードが np.histogram_bin_edges で決める（ここでは検査と軸の範囲の見積もりだけ）。"""

    bins: int | None  # None = 自動（"auto"）
    density: bool
    bin_count: int  # 実際の区間の数
    max_height: float  # 度数（density なら確率密度）の最大


@dataclass(frozen=True)
class ColorbarPlan:
    """色分け散布図（scatterColor）のカラーマップとカラーバーのラベル。"""

    colormap: str
    label: str  # 実際に使うラベル（設定が空なら系列1の色分けの列の表示）


@dataclass(frozen=True)
class PlanSource:
    """描画に使うデータ元（load.files の並びの順）。"""

    id: str
    number: int  # 「データN」の N（load.files の位置。ファイルの一覧が空なら 1）
    var: str  # DataFrame の変数名（"df" または "dfN"）
    name: str  # ファイル名（load.files の name。無ければ空）


@dataclass(frozen=True)
class AxisPlan:
    """1つの軸に、設定のどれが効くか（dataprep が決める。codegen は文字列にするだけ）。

    設定の値は軸の種類で使えないことがある（画面で隠す項目）。使えない項目は、ここで既定値（効かない値）にする。"""

    kind: str = "number"  # number / log / datetime / category
    major_step: float | None = None  # 実際に使う値（datetime / category は整数）。None = 自動
    major_step_unit: str = "day"  # 日時の軸だけ
    minor: str = "auto"  # auto / on / off（category は常に auto）
    minor_divisions: int | None = None  # 副目盛が on の、対数軸でない軸だけ
    tick_format: str = "auto"  # number / log だけ（それ以外は auto）
    tick_decimals: int = 1
    inverted: bool = False
    date_min: str = ""  # 日時の X だけ（正規化済み）
    date_max: str = ""

    @property
    def customized(self) -> bool:
        """既定（自動）と違う目盛の設定があるか。"""
        return self != AxisPlan(kind=self.kind)


@dataclass(frozen=True)
class AxesPlan:
    x: AxisPlan = field(default_factory=AxisPlan)
    y: AxisPlan = field(default_factory=AxisPlan)
    y2: AxisPlan | None = None  # 第2Y軸を作るときだけ


@dataclass(frozen=True)
class PlotPlan:
    skip_rows: int
    plot_type: str
    series: tuple[SeriesPlan, ...]
    x_label: str  # 既定の X ラベル
    y_label: str  # 既定の Y ラベル
    y2_label: str | None  # 第2Y軸を作るときだけ
    bar_x_index: int | None  # bar の X 列（None = 行番号）
    plotted_count: int
    uses_secondary: bool  # 第2Y軸（ax2）を作る（描ける点のある第2軸の系列がある）
    warnings: tuple[dict, ...]  # [{"series": 1始まり, "message": str}]
    datetime_x: bool = False  # 日時の X 軸（line / scatter は日時の軸、bar は日時を文字列にしたカテゴリ）
    thin_categorical_x: bool = False  # line / scatter で X が文字列の列。カテゴリが多いので目盛を間引く
    bar_date_format: str | None = None  # bar で X が日時のときの strftime の書式
    sources: tuple[PlanSource, ...] = ()  # 描画に使うデータ元だけ（load.files の順）
    multi_source: bool = False  # load.files が2つ以上（生成コードで DATA_FILE_N / dfN と書く）
    axes: AxesPlan = field(default_factory=AxesPlan)  # 軸ごとの目盛の設定（効くものだけ）
    annotations: tuple[AnnotationPlan, ...] = ()
    fits: tuple[FitPlan, ...] = ()  # 近似曲線（line / step / scatter / scatterColor のみ）
    hist: HistPlan | None = None  # hist のときだけ
    colorbar: ColorbarPlan | None = None  # scatterColor のときだけ
    computed: tuple["ComputedPlan", ...] = ()  # 計算した列（描画に使うデータ元のものだけ。カードの順）

    @property
    def plotted(self) -> tuple[SeriesPlan, ...]:
        return tuple(s for s in self.series if s.has_points)


@dataclass(frozen=True)
class ComputedPlan:
    """計算した列1つ（描画に使うデータ元のものだけ）。codegen が「計算した列」の節を書くのに使う。"""

    number: int  # カード番号（computed の位置 + 1）
    name: str  # 列の見出し（名前、無ければ「計算N」）
    expr: str  # 利用者が書いた式（コメントにだけ使う）
    node: object  # expr.parse の結果
    data_id: str
    data_var: str  # "df" または "dfN"
    index: int  # 計算後の列番号（ファイルの列の後ろ）
    refs: tuple[tuple[int, str], ...] = ()  # 式が使うファイルの列（番号、コメント用の「列 [i]: 名前」）


MAX_CATEGORY_TICKS = 25  # X が文字列の列のとき、目盛に出すカテゴリの最大数
Y_DATETIME_MESSAGE = "系列{n}: Y列（{name}）は日時の列です。Y列には数値の列を選んでください。"


def _is_datetime(series: pd.Series) -> bool:
    return pd.api.types.is_datetime64_any_dtype(series.dtype)


def auto_bar_date_format(x: pd.Series) -> str:
    """棒グラフの X が日時のときの、自動の書式。全部 0 時なら日付だけ、秒がすべて 0 なら分まで、それ以外は秒まで。"""
    valid = x.dropna()
    if valid.empty or (valid == valid.dt.normalize()).all():
        return "%Y-%m-%d"
    if (valid.dt.second == 0).all() and (valid.dt.microsecond == 0).all():
        return "%Y-%m-%d %H:%M"
    return "%Y-%m-%d %H:%M:%S"


def _label_for(df: pd.DataFrame, idx: int) -> tuple[str, str]:
    name = str(df.columns[idx])
    return name, f"{name} [{idx}]"


# ---------------------------------------------------------------- error bars (G1)

X_ERR_DATETIME = "系列{n}: X が日時の列のときは、X方向のエラーバーは付けられません。"
X_ERR_CATEGORY = "系列{n}: X が文字列の列のときは、X方向のエラーバーは付けられません。"


def _error_values(
    df: pd.DataFrame, idx: int, mask: pd.Series, n: int, what: str, load, warnings: list[dict]
) -> pd.Series:
    """誤差の列を数値にする（数値にできない値・負の値は NaN。空欄も NaN で、警告しない）。

    警告の件数と例は、実際に描く行（mask）だけで数える。"""
    raw = df.iloc[:, idx]
    mask = mask.reindex(df.index, fill_value=False)
    name = str(df.columns[idx])
    numeric, _, _ = coerce_numeric(raw)
    _, count, examples = coerce_numeric(raw[mask])
    where = f"系列{n}: {what}の列「{name}」[{idx}]"
    if count:
        ex = ", ".join(f'"{e}"' for e in examples)
        message = f"{where} に数値にできない値が{count}件あったため、その点のエラーバーは描きません（例: {ex}）。{load_hint(examples, load)}"
        warnings.append({"series": n, "message": message})
    negative = (numeric < 0) & mask
    neg_count = int(negative.sum())
    if neg_count:
        shown: list[str] = []
        for v in numeric[negative].tolist():
            text = f"{v:g}"
            if text not in shown:
                shown.append(text)
            if len(shown) >= MAX_EXAMPLES:
                break
        ex = ", ".join(f'"{e}"' for e in shown)
        warnings.append(
            {"series": n, "message": f"{where} に負の値が{neg_count}件あったため、その点のエラーバーは描きません（例: {ex}）。"}
        )
    return numeric.where(numeric >= 0)


def _error_column(df: pd.DataFrame, requested: str, n: int, direction: str) -> int:
    idx = parse_column_index(requested)
    label = f"系列{n}の{direction.upper()}誤差の列"
    if idx is None:
        raise UserError(f"系列{n}の{direction.upper()}誤差の列の指定が正しくありません。列を選び直してください。", field=label)
    if idx >= len(df.columns):
        raise UserError(_column_out_of_range(idx, len(df.columns)), field=label)
    return idx


def _plan_error(
    df: pd.DataFrame, spec: ErrorSpec, direction: str, n: int, mask: pd.Series, load, warnings: list[dict]
) -> tuple[ErrorPlan | None, object, object]:
    """誤差の指定 → (ErrorPlan, 上（右）の誤差, 下（左）の誤差)。誤差は数値（fixed）か、df と同じ並びの Series（column）。"""
    if spec.mode == "none":
        return None, None, None
    what = f"{direction.upper()}誤差"
    if spec.mode == "fixed":
        minus = spec.value if spec.symmetric else spec.value_minus
        plan = ErrorPlan(direction, "fixed", spec.symmetric, value=spec.value, value_minus=None if spec.symmetric else spec.value_minus)
        return plan, spec.value, minus
    idx = _error_column(df, spec.column, n, direction)
    label = _label_for(df, idx)[1]
    suffix = "" if spec.symmetric else "（上）" if direction == "y" else "（右）"
    plus = _error_values(df, idx, mask, n, what + suffix, load, warnings)
    if spec.symmetric:
        return ErrorPlan(direction, "column", True, index=idx, label=label), plus, plus
    idx_minus = _error_column(df, spec.column_minus, n, direction)
    minus_suffix = "（下）" if direction == "y" else "（左）"
    minus = _error_values(df, idx_minus, mask, n, what + minus_suffix, load, warnings)
    plan = ErrorPlan(direction, "column", False, index=idx, index_minus=idx_minus, label=label, label_minus=_label_for(df, idx_minus)[1])
    return plan, plus, minus


def _take(value, mask: pd.Series):
    """誤差（数値か Series）の、描く行だけ。"""
    return value.loc[mask.index[mask]] if isinstance(value, pd.Series) else value


def _add_error_extent(ext: "_Extents", axis: str, base: pd.Series, plus, minus) -> None:
    """エラーバーの両端（base - 下、base + 上）を、軸の範囲に加える（欠けた誤差の点は加えない）。"""
    ext.add_values(axis, base - minus)
    ext.add_values(axis, base + plus)


# ---------------------------------------------------------------- series style (G3)

DEFAULT_BAND_NOTE = "塗りつぶし帯"


def _marker_plan(series, plot_type: str) -> tuple[str, float]:
    """点の形と点サイズ（面積）。line の「自動」は今までどおり（点サイズが 0 より大きいときだけ丸）。

    形を選んで点サイズが自動のときは、散布図と同じ面積 24 で描く。scatter の「自動」は引数を足さない。"""
    shape = series.marker
    if plot_type in {"scatter", "scatterColor"}:
        return ("" if shape == "auto" else shape), series.effective_marker_size("scatter")
    size = series.effective_marker_size("line")  # line と step
    if shape == "auto":
        return ("o" if size > 0 else ""), size
    if shape == "none":
        return "", 0.0
    return shape, size if size > 0 else 24.0


def _band_column(df: pd.DataFrame, requested: str, n: int) -> int:
    field_name = f"系列{n}の塗りつぶし帯"
    idx = parse_column_index(requested)
    if idx is None:
        raise UserError(f"系列{n}の塗りつぶし帯の列の指定が正しくありません。列を選び直してください。", field=field_name)
    if idx >= len(df.columns):
        raise UserError(_column_out_of_range(idx, len(df.columns)), field=field_name)
    return idx


def _band_values(df: pd.DataFrame, idx: int, mask: pd.Series, n: int, what: str, load, warnings: list[dict]) -> pd.Series:
    """帯の端の列を数値にする（数値にできない値は NaN。空欄も NaN で、警告しない）。警告の件数と例は、実際に描く行（mask）だけで数える。"""
    raw = df.iloc[:, idx]
    mask = mask.reindex(df.index, fill_value=False)
    numeric, _, _ = coerce_numeric(raw)
    _, count, examples = coerce_numeric(raw[mask])
    if count:
        ex = ", ".join(f'"{e}"' for e in examples)
        message = (
            f"系列{n}: 塗りつぶし帯（{what}）の列「{df.columns[idx]}」[{idx}] に数値にできない値が{count}件あったため、"
            f"その点の帯は描きません（例: {ex}）。{load_hint(examples, load)}"
        )
        warnings.append({"series": n, "message": message})
    return numeric


def _plan_fill(df: pd.DataFrame, series, n: int, ok: pd.Series, y_axis: str, ext: "_Extents", load, warnings: list[dict]):
    fill = series.fill
    if not fill.enabled:
        return None
    lo_idx = _band_column(df, fill.lower, n)
    hi_idx = _band_column(df, fill.upper, n)
    lower = _band_values(df, lo_idx, ok, n, "下端", load, warnings)
    upper = _band_values(df, hi_idx, ok, n, "上端", load, warnings)
    both = lower.notna() & upper.notna() & ok.reindex(df.index, fill_value=False)
    ext.add_values(y_axis, lower[both])
    ext.add_values(y_axis, upper[both])
    return FillPlan(lo_idx, hi_idx, _label_for(df, lo_idx)[1], _label_for(df, hi_idx)[1], fill.alpha)


# ---------------------------------------------------------------- fits (G5)


def _plan_fits(settings: Settings) -> list[tuple[int, object]]:
    """(近似曲線の番号, FitSettings) を、系列の番号ごとに引けるように並べる。棒グラフでは使わない。"""
    if settings.plot.type in BAR_LIKE_TYPES:
        return []
    return list(enumerate(settings.fits, start=1))


def _fit_error(n: int, message: str) -> UserError:
    return UserError(f"近似曲線{n}: {message}", field=f"近似曲線{n}の系列")


def _check_fit_data(n: int, fit, p: "SeriesPlan", x: pd.Series, y: pd.Series) -> None:
    """近似に使う点（x, y は描く行だけ）の検査。"""
    if p.datetime_x:
        raise _fit_error(n, "X が日時の列の系列は近似できません。")
    if p.categorical_x:
        raise _fit_error(n, "X が文字列の列の系列は近似できません。")
    distinct = int(pd.Series(x).nunique())
    need = fit.degree + 1
    if distinct < need:
        raise _fit_error(n, f"{fit.degree}次式で近似するには、X の異なる値が{need}個以上必要です（今は{distinct}個）。")
    if int(pd.Series(y).nunique()) < 2:
        raise _fit_error(n, "Y の値がすべて同じなので、近似できません（決定係数 R² を計算できません）。")


def _build_fit_plans(settings: Settings, plans: list["SeriesPlan"]) -> tuple[FitPlan, ...]:
    ids = {s.id: i for i, s in enumerate(settings.series)}
    out = []
    text_index = 0
    for n, fit in _plan_fits(settings):
        i = ids[fit.series]
        sp, ss = plans[i], settings.series[i]
        if not sp.has_points:
            raise _fit_error(n, "近似する系列に、描ける点がありません。")
        base = sp.legend_label if not sp.legend_label.startswith("_") else f"系列{sp.number}"
        out.append(
            FitPlan(
                number=n,
                series_number=sp.number,
                series_label=sp.legend_label,
                degree=fit.degree,
                show=fit.show,
                color=fit.color or ss.color,
                line_style=fit.line_style,
                line_width=ss.line_width,
                label_prefix=f"{base}の近似",
                text_index=text_index if fit.show == "text" else -1,
                target="ax2" if sp.secondary else "ax",
            )
        )
        if fit.show == "text":
            text_index += 1
    return tuple(out)


# ---------------------------------------------------------------- annotations (G4)

_ANNOTATION_DATE_HELP = f"年が先頭の日付か日時で入力してください（例: {_DATE_EXAMPLE}）"


def _annotation_value(text: str, n: int, what: str, *, kind: str, log: bool) -> float | str:
    """注釈の位置の入力 → 値。kind は軸の種類（number / log / datetime / category）。datetime は正規化した日付の文字列、それ以外は float。"""
    field_name = f"注釈{n}の{what}"  # 「注釈1のX」「注釈1の開始」
    if not text.strip():
        raise UserError(f"{field_name}を入力してください。", field=field_name)
    if kind == "datetime":
        try:
            return _date_range_value(text, "")
        except UserError:
            raise UserError(
                f"{field_name}が正しくありません。X が日時の列なので、{_ANNOTATION_DATE_HELP}。", field=field_name
            ) from None
    value = _to_float(text)
    if value is None:
        if _looks_like_date(text):
            raise UserError(f"{field_name}に日付は使えません。X が日時の列ではないので、数値で入力してください。", field=field_name)
        hint = "（文字列の列では、何番目のカテゴリか（0 始まり）を数で指定します）" if kind == "category" else ""
        raise UserError(f"{field_name}は数値で入力してください。{hint}", field=field_name)
    if kind == "log" or log:
        if value <= 0:
            raise UserError(f"{field_name}は、対数軸では0より大きい値で入力してください。", field=field_name)
    return value


def _looks_like_date(text: str) -> bool:
    try:
        _date_range_value(text, "")
    except UserError:
        return False
    return True


def _plan_annotations(
    settings: Settings, x_kind: str, uses_secondary: bool, ext: "_Extents", y_kind: str | None = None
) -> tuple[AnnotationPlan, ...]:
    """y_kind は Y 軸の種類（横棒の縦軸は category / number）。None なら Y のスケール（number / log）から決める。"""
    out = []
    y_log = {"y": settings.axes.y.scale == "log", "y2": settings.axes.y2.scale == "log"}
    for n, a in enumerate(settings.annotations, start=1):
        use_y2 = a.axis == "y2" and uses_secondary
        target = "ax2" if use_y2 else "ax"
        y_axis = "y2" if use_y2 else "y"
        common = dict(
            number=n, kind=a.kind, target=target, color=a.color, alpha=a.alpha, label=a.label, line_style=a.line_style,
            line_width=a.line_width,
        )

        def xval(text: str, what: str = "X") -> float | str:
            return _annotation_value(text, n, what, kind=x_kind, log=False)

        def yval(text: str, what: str = "Y") -> float:
            kind = y_kind or ("log" if y_log[y_axis] else "number")
            return _annotation_value(text, n, what, kind=kind, log=False)  # type: ignore[return-value]

        def add_x(*values) -> None:
            if x_kind in {"number", "log"}:
                nums = [float(v) for v in values]
                ext.add("x", min(nums), max(nums))
            elif x_kind == "datetime":
                secs = [_timestamp_seconds(v) for v in values]
                ext.add("x", min(secs), max(secs))

        def add_y(*values) -> None:
            ext.add(y_axis, min(values), max(values))

        if a.kind == "text":
            if not a.text.strip():
                raise UserError(f"注釈{n}の文字を入力してください。", field=f"注釈{n}の文字")
            if a.coords == "axes":
                x = _annotation_value(a.x, n, "X", kind="number", log=False)
                y = _annotation_value(a.y, n, "Y", kind="number", log=False)
                out.append(AnnotationPlan(**common, text=a.text, x=x, y=y, coords="axes", font_size=a.font_size))
            else:
                x = xval(a.x)
                y = yval(a.y)
                out.append(
                    AnnotationPlan(**common, text=a.text, x=x, y=y, coords="data", date=x_kind == "datetime", font_size=a.font_size)
                )
        elif a.kind == "hline":
            y = yval(a.y)
            add_y(y)
            out.append(AnnotationPlan(**common, y=y))
        elif a.kind == "vline":
            x = xval(a.x)
            add_x(x)
            out.append(AnnotationPlan(**common, x=x, date=x_kind == "datetime"))
        elif a.kind == "hspan":
            lo, hi = yval(a.start, "開始"), yval(a.end, "終了")
            add_y(lo, hi)
            out.append(AnnotationPlan(**common, start=lo, end=hi))
        else:  # vspan
            lo, hi = xval(a.start, "開始"), xval(a.end, "終了")
            add_x(lo, hi)
            out.append(AnnotationPlan(**common, start=lo, end=hi, date=x_kind == "datetime"))
    return tuple(out)


NOT_LOADED_MESSAGE = "データ{n}（{name}）を読み込めていません。読込設定やファイルを確認してください。"
BAR_SOURCE_MESSAGE = "棒グラフでは、すべての系列に同じデータ元を選んでください。"


COMPUTED_REF_COMPUTED = "計算した列{n}の式: {pos}文字目: 計算した列（[{k}]）は、ほかの計算した列の式には使えません。"
COMPUTED_REF_MISSING = "計算した列{n}の式: {pos}文字目: 列 [{k}] はありません（データの列は [0]〜[{last}] です）。"
COMPUTED_REF_DATETIME = "計算した列{n}の式: {pos}文字目: 列 [{k}]（{name}）は日時の列なので、計算に使えません。"
COMPUTED_INVALID = "計算した列{n}（{name}）: 0 での割り算・負の数の平方根などで計算できなかった値が{count}件あったため、欠損として扱います。"


def _apply_computed(
    frames: dict[str, pd.DataFrame], default_id: str, settings: Settings, var_of: dict[str, str]
) -> tuple[tuple[ComputedPlan, ...], list[dict]]:
    """データ元ごとに（skipRows を除いた）DataFrame の末尾へ、計算した列をカードの順に足す（frames を書き換える）。

    描画に使わないデータ元の計算した列は計算しない。計算した列は、ファイルの列だけを参照できる。"""
    items = [(n, c, c.source or default_id) for n, c in enumerate(settings.computed, start=1)]
    file_count = {sid: frame.shape[1] for sid, frame in frames.items()}
    count_of: dict[str, int] = {}
    for _, _, sid in items:
        count_of[sid] = count_of.get(sid, 0) + 1
    plans: list[ComputedPlan] = []
    warnings: list[dict] = []
    done: dict[str, int] = {}
    for n, c, sid in items:
        if sid not in frames:
            continue
        frame = frames[sid]
        total = file_count[sid]
        index = total + done.get(sid, 0)
        done[sid] = done.get(sid, 0) + 1
        name = c.name or f"計算{n}"
        field_name = f"計算した列{n}の式"
        refs = expr_module.column_refs(c.expr_node)
        for k, pos in sorted(refs, key=lambda r: r[1]):
            if k >= total + count_of[sid]:
                raise UserError(COMPUTED_REF_MISSING.format(n=n, pos=pos, k=k, last=total - 1), field=field_name)
            if k >= total:
                raise UserError(COMPUTED_REF_COMPUTED.format(n=n, pos=pos, k=k), field=field_name)
            if _is_datetime(frame.iloc[:, k]):
                raise UserError(
                    COMPUTED_REF_DATETIME.format(n=n, pos=pos, k=k, name=str(frame.columns[k])), field=field_name
                )
        columns: dict[int, pd.Series] = {}
        for k in expr_module.column_indices(c.expr_node):
            raw = frame.iloc[:, k]
            _, count, examples = coerce_numeric(raw)
            if count:
                ex = ", ".join(f'"{e}"' for e in examples)
                warnings.append(
                    {
                        "series": 0,
                        "message": f"計算した列{n}（{name}）: 列「{frame.columns[k]}」[{k}] に数値にできない値が{count}件あったため、"
                        f"欠損として計算します（例: {ex}）。{load_hint(examples, settings.load)}",
                    }
                )
            columns[k] = pd.to_numeric(raw, errors="coerce").astype(float)
        result, invalid = expr_module.evaluate(c.expr_node, columns, frame.index)
        if invalid:
            warnings.append({"series": 0, "message": COMPUTED_INVALID.format(n=n, name=name, count=invalid)})
        frame.insert(frame.shape[1], name, result, allow_duplicates=True)
        plans.append(
            ComputedPlan(
                number=n,
                name=name,
                expr=c.expr,
                node=c.expr_node,
                data_id=sid,
                data_var=var_of[sid],
                index=index,
                refs=tuple((k, f"列 [{k}]: {frame.columns[k]}") for k in expr_module.column_indices(c.expr_node)),
            )
        )
    return tuple(plans), warnings


def plan_plot(data, settings: Settings) -> PlotPlan:
    """データと設定から描画計画を作る。データ由来の問題は UserError にする。

    data は DataFrame（1つ）または {ファイル id: DataFrame}（読み込めたファイルだけ）。"""
    plot = settings.plot
    files = settings.load.files
    numbers = {f.id: i + 1 for i, f in enumerate(files)}
    names = {f.id: f.name for f in files}
    if isinstance(data, pd.DataFrame):
        data = {files[0].id if files else "d1": data}
    if not data:
        raise UserError("先にファイルを読み込んでください。")
    default_id = files[0].id if files else next(iter(data))
    multi = len(files) >= 2

    ids: list[str] = []  # 系列ごとのデータ元
    for n, s in enumerate(settings.series, start=1):
        sid = s.source or default_id
        if sid not in data:
            raise UserError(
                NOT_LOADED_MESSAGE.format(n=numbers.get(sid, 1), name=names.get(sid, "")), field=f"系列{n}のデータ元"
            )
        ids.append(sid)
    if plot.type in {"bar", "barh", "barStacked"} and len(set(ids)) > 1:
        raise UserError(BAR_SOURCE_MESSAGE, field="データ元")

    order = [f.id for f in files if f.id in set(ids)] if files else list(dict.fromkeys(ids))
    frames = {
        sid: slice_skip_rows(data[sid], plot.skip_rows, f"データ{numbers.get(sid, 1)}（{names.get(sid, '')}）" if multi else "")
        for sid in order
    }
    sources = tuple(
        PlanSource(id=sid, number=numbers.get(sid, 1), var=f"df{numbers[sid]}" if multi else "df", name=names.get(sid, ""))
        for sid in order
    )
    var_of = {src.id: src.var for src in sources}

    y_requests = [""] * len(settings.series)
    for sid in order:  # Y の自動割り当ては、ファイルの列だけを見る（計算した列を足す前）
        idx = [i for i, x in enumerate(ids) if x == sid]
        resolved = resolve_y_indices(frames[sid], [settings.series[i].y for i in idx])
        for i, r in zip(idx, resolved):
            y_requests[i] = r
    computed, computed_warnings = _apply_computed(frames, default_id, settings, var_of)
    dfs = [frames[sid] for sid in ids]
    if plot.type in {"line", "step", "scatter", "scatterColor"}:
        plan = _plan_xy(dfs, settings, y_requests)
    elif plot.type == "hist":
        plan = _plan_hist(dfs, settings, y_requests)
    else:
        plan = _plan_bar(dfs[0], settings, y_requests)
    series = tuple(replace(sp, data_id=sid, data_var=var_of[sid]) for sp, sid in zip(plan.series, ids))
    return replace(
        plan,
        series=series,
        sources=sources,
        multi_source=multi,
        computed=computed,
        warnings=tuple(computed_warnings) + tuple(plan.warnings),
    )


# ---------------------------------------------------------------- axes (ticks)

MAX_MAJOR_TICKS = 100  # 主目盛の間隔を指定したときの、目盛の本数の上限
_UNIT_SECONDS = {
    "year": 365.25 * 86400,
    "month": 30.44 * 86400,
    "day": 86400.0,
    "hour": 3600.0,
    "minute": 60.0,
    "second": 1.0,
}


class _Extents:
    """軸ごとに、描くものの範囲（最小, 最大）を集める（主目盛の本数の見積もり用）。

    X が日時のときの X は、1970 年からの秒数。エラーバーの端なども、ここに add すれば範囲に入る。"""

    def __init__(self) -> None:
        self._ranges: dict[str, list[tuple[float, float]]] = {"x": [], "y": [], "y2": []}

    def add(self, axis: str, lo, hi) -> None:
        lo, hi = float(lo), float(hi)
        if math.isfinite(lo) and math.isfinite(hi):
            self._ranges[axis].append((lo, hi))

    def add_values(self, axis: str, values: pd.Series) -> None:
        values = values.dropna()
        if len(values):
            self.add(axis, values.min(), values.max())

    def bounds(self, axis: str) -> tuple[float, float] | None:
        r = self._ranges[axis]
        if not r:
            return None
        return min(lo for lo, _ in r), max(hi for _, hi in r)


def _seconds(values: pd.Series) -> pd.Series:
    """日時の列 → 1970 年からの秒数。"""
    return (values - pd.Timestamp(0)).dt.total_seconds()


def _timestamp_seconds(text: str) -> float:
    return (pd.Timestamp(text) - pd.Timestamp(0)).total_seconds()


def _estimate_ticks(bounds, lo_limit, hi_limit, step: float) -> int:
    """主目盛の本数の見積もり。範囲は、指定が両方あればそれ、無ければデータの範囲（片方だけ指定ならそれと組み合わせ）に 10% を足す。"""
    if lo_limit is not None and hi_limit is not None:
        span = hi_limit - lo_limit
    else:
        if bounds is None:
            return 0
        lo, hi = bounds
        if lo_limit is not None:
            lo = lo_limit
        if hi_limit is not None:
            hi = hi_limit
        span = abs(hi - lo) * 1.1
    return math.floor(span / step + 1e-9) + 1


def _too_many_ticks(label: str, count: int) -> UserError:
    field_name = f"{label}軸の主目盛の間隔"
    return UserError(
        f"{field_name}が小さすぎます（目盛が約{count}本になります。{MAX_MAJOR_TICKS}本まで）。間隔を大きくするか、空欄（自動）にしてください。",
        field=field_name,
    )


def _plan_axis(
    axis: AxisSettings, kind: str, label: str, ext: _Extents, which: str, *, categories: int = 0, include_zero: bool = False
) -> AxisPlan:
    """設定の目盛の項目のうち、この軸の種類で効くものを決める。使えない組み合わせは UserError。"""
    step_field = f"{label}軸の主目盛の間隔"
    date_min = date_max = ""
    if kind == "datetime":
        date_min, date_max = validate_date_range(axis)  # 日時の X のときだけ検証する（隠れているときは使わない）
    elif which == "x":
        check_axis_range(axis, label)  # 数値の範囲は、X が日時でないときだけ検査する（日時のときは隠れていて使わない）
    major_step = None
    unit = "day"
    lo_limit = hi_limit = None
    if axis.major_step is not None and kind != "log":
        step = axis.major_step
        bounds = ext.bounds(which)
        if kind in {"category", "datetime"}:
            if not float(step).is_integer():
                if kind == "category":
                    raise UserError(
                        f"{label} が文字列の列のときは、{label}軸の主目盛の間隔は整数（何個おきに目盛を付けるか）で指定してください。",
                        field=step_field,
                    )
                raise UserError(
                    f"{label} が日時の列のときは、{label}軸の主目盛の間隔は整数（単位の何個おきに目盛を付けるか）で指定してください。",
                    field=step_field,
                )
            step = int(step)
        if kind == "category":
            count = math.ceil(categories / step)
        elif kind == "datetime":
            unit = axis.major_step_unit
            lo_limit = _timestamp_seconds(date_min) if date_min else None
            hi_limit = _timestamp_seconds(date_max) if date_max else None
            count = _estimate_ticks(bounds, lo_limit, hi_limit, step * _UNIT_SECONDS[unit])
        else:
            if include_zero and bounds is not None:
                bounds = (min(bounds[0], 0.0), max(bounds[1], 0.0))
            count = _estimate_ticks(bounds, axis.min, axis.max, step)
        if count > MAX_MAJOR_TICKS:
            raise _too_many_ticks(label, count)
        major_step = step
    minor = "auto" if kind == "category" else axis.minor_ticks
    divisions = axis.minor_divisions if minor == "on" and kind in {"number", "datetime"} else None
    formatted = kind in {"number", "log"} and axis.tick_format != "auto"
    return AxisPlan(
        kind=kind,
        major_step=major_step,
        major_step_unit=unit if kind == "datetime" and major_step is not None else "day",
        minor=minor,
        minor_divisions=divisions,
        tick_format=axis.tick_format if formatted else "auto",
        tick_decimals=axis.tick_decimals if formatted else 1,
        inverted=axis.inverted,
        date_min=date_min,
        date_max=date_max,
    )


def _plan_axes(
    settings: Settings, x_kind: str, uses_secondary: bool, ext: _Extents, categories: int, y_kind: str | None = None
) -> AxesPlan:
    """y_kind は Y 軸の種類（横棒の縦軸は category / number。そのとき categories は Y 軸のカテゴリ数）。None なら Y のスケールから決める。"""
    axes = settings.axes
    plot_type = settings.plot.type
    bar = plot_type in {"bar", "barStacked", "hist"}  # 縦向きの棒: Y 軸（値）の範囲に 0 を含める

    def num_kind(axis: AxisSettings) -> str:
        return "log" if axis.scale == "log" else "number"

    return AxesPlan(
        x=_plan_axis(axes.x, x_kind, "X", ext, "x", categories=0 if y_kind else categories, include_zero=plot_type == "barh"),
        y=_plan_axis(axes.y, y_kind or num_kind(axes.y), "Y", ext, "y", categories=categories if y_kind == "category" else 0, include_zero=bar),
        y2=_plan_axis(axes.y2, num_kind(axes.y2), "第2Y", ext, "y2", include_zero=plot_type == "bar") if uses_secondary else None,
    )


def _color_column(df: pd.DataFrame, requested: str, n: int) -> int:
    field_name = f"系列{n}の色分けの列"
    idx = parse_column_index(requested)
    if idx is None:
        raise UserError(f"系列{n}の色分けの列を選んでください。", field=field_name)
    if idx >= len(df.columns):
        raise UserError(_column_out_of_range(idx, len(df.columns)), field=field_name)
    return idx


def _color_values(df: pd.DataFrame, idx: int, mask: pd.Series, n: int, load, warnings: list[dict]) -> pd.Series:
    """色分けの列を数値にする（数値にできない値は NaN。空欄も NaN で、警告しない）。警告の件数と例は、描く行（mask）だけで数える。"""
    raw = df.iloc[:, idx]
    numeric, _, _ = coerce_numeric(raw)
    _, count, examples = coerce_numeric(raw[mask.reindex(df.index, fill_value=False)])
    if count:
        ex = ", ".join(f'"{e}"' for e in examples)
        message = (
            f"系列{n}: 色分けの列「{df.columns[idx]}」[{idx}] に数値にできない値が{count}件あったため、"
            f"その点は描きません（例: {ex}）。{load_hint(examples, load)}"
        )
        warnings.append({"series": n, "message": message})
    return numeric


def _plan_xy(dfs: list[pd.DataFrame], settings: Settings, y_requests: list[str]) -> PlotPlan:
    plot_type = settings.plot.type
    plans: list[SeriesPlan] = []
    warnings: list[dict] = []
    category_values: set = set()
    ext = _Extents()
    fit_settings = _plan_fits(settings)
    fits_of = {settings.series[i].id: [(k, f) for k, f in fit_settings if f.series == settings.series[i].id] for i in range(len(settings.series))}
    for n, (df, series, y_request) in enumerate(zip(dfs, settings.series, y_requests), start=1):
        x_index = resolve_column_index(df, series.x) if series.x else None
        x_label = str(df.columns[x_index]) if x_index is not None else "index"
        y_index = resolve_column_index(df, y_request)
        y_name, data_label = _label_for(df, y_index)

        if _is_datetime(df.iloc[:, y_index]):
            raise UserError(Y_DATETIME_MESSAGE.format(n=n, name=y_name), field=f"系列{n}のY列")
        x_series = df.iloc[:, x_index] if x_index is not None else pd.Series(df.index)
        datetime_x = _is_datetime(x_series)
        convert_x = False
        if x_index is not None and not datetime_x and not pd.api.types.is_numeric_dtype(x_series.dtype) and _looks_numeric(x_series):
            convert_x = True
            x_series, x_dropped, x_examples = coerce_numeric(x_series)
            if x_dropped:
                warnings.append(dropped_warning(n, f"系列{n}のX列（{x_label}）", x_dropped, x_examples, settings.load))
        y_numeric, y_dropped, y_examples = coerce_numeric(df.iloc[:, y_index])
        if y_dropped:
            warnings.append(dropped_warning(n, f"系列{n}（{y_name}）", y_dropped, y_examples, settings.load))

        point_ok = y_numeric.notna() & pd.notna(x_series)
        color_index = None
        color_label = ""
        color_numeric = None
        if plot_type == "scatterColor":
            color_index = _color_column(df, series.color_column, n)
            color_label = _label_for(df, color_index)[1]
            if _is_datetime(df.iloc[:, color_index]):
                raise UserError(
                    f"系列{n}の色分けの列（{df.columns[color_index]}）は日時の列です。色分けの列には数値の列を選んでください。",
                    field=f"系列{n}の色分けの列",
                )
            color_numeric = _color_values(df, color_index, point_ok, n, settings.load, warnings)
            point_ok = point_ok & color_numeric.notna()
        has_points = bool(point_ok.any())
        marker, marker_size = _marker_plan(series, plot_type)
        plans.append(
            SeriesPlan(
                number=n,
                y_index=y_index,
                y_name=y_name,
                x_index=x_index,
                x_label=x_label,
                data_label=data_label,
                legend_label=series.label or data_label,
                convert_x=convert_x,
                categorical_x=x_index is not None
                and not datetime_x
                and not convert_x
                and not pd.api.types.is_numeric_dtype(x_series.dtype),
                marker_size=marker_size,
                has_points=has_points,
                secondary=series.secondary_axis,
                datetime_x=datetime_x,
                marker=marker,
                alpha=series.alpha,
                color_index=color_index,
                color_label=color_label,
            )
        )
        if has_points:
            ok = point_ok
            y_axis = "y2" if series.secondary_axis else "y"
            fill_plan = _plan_fill(df, series, n, ok, y_axis, ext, settings.load, warnings)
            for k, fit in fits_of[series.id]:
                _check_fit_data(k, fit, plans[-1], x_series[ok], y_numeric[ok])
            ext.add_values(y_axis, y_numeric[ok])
            if datetime_x:
                ext.add_values("x", _seconds(x_series[ok]))
            elif not plans[-1].categorical_x:
                ext.add_values("x", x_series[ok])
            bars = series.error_bars
            y_err, y_plus, y_minus = _plan_error(df, bars.y, "y", n, ok, settings.load, warnings)
            if bars.x.mode != "none":
                if datetime_x:
                    raise UserError(X_ERR_DATETIME.format(n=n), field=f"系列{n}のX誤差の方式")
                if plans[-1].categorical_x:
                    raise UserError(X_ERR_CATEGORY.format(n=n), field=f"系列{n}のX誤差の方式")
            x_err, x_plus, x_minus = _plan_error(df, bars.x, "x", n, ok, settings.load, warnings)
            if y_err is not None:
                _add_error_extent(ext, y_axis, y_numeric[ok], _take(y_plus, ok), _take(y_minus, ok))
            if x_err is not None:
                _add_error_extent(ext, "x", x_series[ok], _take(x_plus, ok), _take(x_minus, ok))
            plans[-1] = replace(plans[-1], y_err=y_err, x_err=x_err, cap_size=bars.cap_size, fill=fill_plan)
        if has_points and x_index is not None and plans[-1].categorical_x:
            shown = x_series[y_numeric.notna() & x_series.notna()]
            category_values.update(shown.tolist())

    if not any(p.has_points for p in plans):
        raise UserError(_no_data_message(warnings))

    _check_datetime_x(settings, plans)
    x_labels = [p.x_label for p in plans]
    common_x = x_labels[0] if len(set(x_labels)) == 1 else "x"
    plotted = [p for p in plans if p.has_points]
    if any(p.datetime_x for p in plotted):
        x_kind = "datetime"
    elif any(p.categorical_x for p in plotted):
        x_kind = "category"
    else:
        x_kind = "log" if settings.axes.x.scale == "log" else "number"
    return _finish(
        settings, plans, warnings, common_x, None,
        datetime_x=any(p.datetime_x and p.has_points for p in plans),
        thin_categorical_x=len(category_values) > MAX_CATEGORY_TICKS,
        axes_args=(x_kind, ext, len(category_values)),
        fits=_build_fit_plans(settings, plans),
    )


def _check_datetime_x(settings: Settings, plans: list[SeriesPlan]) -> None:
    """日時の X 軸の組み合わせの検査（日時と日時でない X の混在、対数軸、範囲の指定）。"""
    kinds = {p.datetime_x for p in plans}
    if kinds == {True, False}:
        raise UserError("X が日時の系列と、日時でない系列を同じ図に描くことはできません。X列をそろえてください。", field="X列")
    if kinds != {True}:
        return
    axis = settings.axes.x
    if axis.scale == "log":
        raise UserError("X が日時の列のときは、X軸を対数にできません。", field="X軸スケール")


def _plan_bar(df: pd.DataFrame, settings: Settings, y_requests: list[str]) -> PlotPlan:
    """bar / barh / barStacked。barh は軸を入れ替えて描く（値は横軸 = X 軸、カテゴリは縦軸 = Y 軸）。"""
    plot = settings.plot
    horizontal = plot.type == "barh"
    stacked = plot.type == "barStacked"
    val_axis, cat_axis = ("x", "y") if horizontal else ("y", "x")  # 値の軸・カテゴリの軸（物理的な軸）
    x_req = plot.x_column.strip()
    if x_req:
        bar_x_index = resolve_column_index(df, x_req)
        x = df.iloc[:, bar_x_index]
        x_label = str(df.columns[bar_x_index])
        datetime_x = _is_datetime(x)
    else:
        bar_x_index = None
        x = pd.Series(df.index)
        x_label = "index"
        datetime_x = False

    frame = pd.DataFrame({"x": x})
    plans: list[SeriesPlan] = []
    warnings: list[dict] = []
    for i, (series, y_request) in enumerate(zip(settings.series, y_requests)):
        n = i + 1
        y_index = resolve_column_index(df, y_request)
        y_name, data_label = _label_for(df, y_index)
        if _is_datetime(df.iloc[:, y_index]):
            raise UserError(Y_DATETIME_MESSAGE.format(n=n, name=y_name), field=f"系列{n}のY列")
        numeric, dropped, examples = coerce_numeric(df.iloc[:, y_index])
        frame[f"y_{i}"] = numeric
        if dropped:
            warnings.append(dropped_warning(n, f"系列{n}（{y_name}）", dropped, examples, settings.load))
        plans.append(
            SeriesPlan(
                number=n,
                y_index=y_index,
                y_name=y_name,
                x_index=bar_x_index,
                x_label=x_label,
                data_label=data_label,
                legend_label=series.label or data_label,
                convert_x=False,
                categorical_x=False,
                marker_size=series.effective_marker_size("bar"),
                has_points=True,
                secondary=series.secondary_axis,
                datetime_x=datetime_x,
                alpha=series.alpha,
            )
        )

    y_keys = [f"y_{i}" for i in range(len(plans))]
    frame = frame.dropna(subset=y_keys, how="all")
    if frame.empty:
        raise UserError(_no_data_message(warnings))

    positions_form = stacked or len(plans) > 1  # 棒の位置（0, 1, 2, …）にカテゴリのラベルを付ける形
    if len(plans) == 1 and not stacked:
        has_points = bool((frame["y_0"].notna() & pd.notna(frame["x"])).any())
        if not has_points:
            raise UserError(NO_DRAWABLE_DATA)
    bar_date_format = None
    if datetime_x:
        bar_date_format = settings.axes.x.date_format or auto_bar_date_format(x)
    # 棒の位置（複数系列・積み上げ）か、文字列・日時の X はカテゴリの軸。数値の X・X なしの1系列は数値の軸
    ext = _Extents()
    if not positions_form:
        ok = frame["y_0"].notna() & frame["x"].notna()  # 描く棒の行
    else:
        ok = frame[y_keys].notna().any(axis=1)
    if stacked:
        values = frame[y_keys][ok].fillna(0.0)  # 欠けた値は 0 として積む
        positive = values.where(values > 0, 0.0).sum(axis=1)
        negative = values.where(values < 0, 0.0).sum(axis=1)
        ext.add(val_axis, min(float(negative.min()), 0.0), max(float(positive.max()), 0.0))
    else:
        for k in y_keys:
            ext.add_values(val_axis if horizontal else ("y2" if plans[int(k[2:])].secondary else "y"), frame[k][ok])
    for i, series in enumerate(settings.series):
        spec = series.error_bars.y
        if spec.mode == "none":
            continue
        k = f"y_{i}"
        rows = ok & frame[k].notna()  # 棒を描く行（欠けた行は棒も誤差も描かない）
        y_err, plus, minus = _plan_error(df, spec, "y", i + 1, rows, settings.load, warnings)
        axis = val_axis if horizontal else ("y2" if plans[i].secondary else "y")
        _add_error_extent(ext, axis, frame[k][rows], _take(plus, rows), _take(minus, rows))
        plans[i] = replace(plans[i], y_err=y_err, cap_size=series.error_bars.cap_size)
    x_text = datetime_x or not pd.api.types.is_numeric_dtype(x.dtype)
    if positions_form or x_text:
        cat_kind = "category"
        categories = len(frame) if positions_form else int(frame["x"][ok].nunique())
    else:
        cat_kind = "number" if horizontal else ("log" if settings.axes.x.scale == "log" else "number")
        categories = 0
        ext.add_values(cat_axis, frame["x"][ok])
    if horizontal:
        axes_args = ("log" if settings.axes.x.scale == "log" else "number", ext, categories, cat_kind)  # 縦軸はカテゴリ。Y のスケールは使わない
    else:
        axes_args = (cat_kind, ext, categories)
    return _finish(
        settings, plans, warnings, x_label, bar_x_index, datetime_x=datetime_x, bar_date_format=bar_date_format,
        axes_args=axes_args,
    )


HIST_AUTO_BINS_MESSAGE = "区間の数が自動で{n} 個になりました（{limit} 個まで）。「区間の数」を指定してください。"


def _plan_hist(dfs: list[pd.DataFrame], settings: Settings, y_requests: list[str]) -> PlotPlan:
    """ヒストグラム。各系列の Y 列の値の分布（X 列は使わない）。区間は全系列で共通。"""
    plot = settings.plot
    plans: list[SeriesPlan] = []
    warnings: list[dict] = []
    values: list[pd.Series] = []
    for n, (df, series, y_request) in enumerate(zip(dfs, settings.series, y_requests), start=1):
        y_index = resolve_column_index(df, y_request)
        y_name, data_label = _label_for(df, y_index)
        if _is_datetime(df.iloc[:, y_index]):
            raise UserError(Y_DATETIME_MESSAGE.format(n=n, name=y_name), field=f"系列{n}のY列")
        numeric, dropped, examples = coerce_numeric(df.iloc[:, y_index])
        if dropped:
            warnings.append(dropped_warning(n, f"系列{n}（{y_name}）", dropped, examples, settings.load))
        vals = numeric.dropna()
        if len(vals):
            values.append(vals)
        plans.append(
            SeriesPlan(
                number=n,
                y_index=y_index,
                y_name=y_name,
                x_index=None,
                x_label="",
                data_label=data_label,
                legend_label=series.label or data_label,
                convert_x=False,
                categorical_x=False,
                marker_size=series.effective_marker_size("bar"),
                has_points=bool(len(vals)),
                secondary=False,
                alpha=series.alpha,
            )
        )
    if not values:
        raise UserError(_no_data_message(warnings))
    bins = plot.hist_bins
    try:
        edges = np.histogram_bin_edges(np.concatenate([v.to_numpy(dtype=float) for v in values]), bins=bins or "auto")
    except ValueError as exc:
        raise UserError(
            "ヒストグラムの区間を決められませんでした（無限大の値が含まれていないか確認してください）。", field="区間の数", detail=str(exc)
        ) from exc
    bin_count = len(edges) - 1
    if bins is None and bin_count > MAX_HIST_BINS:
        raise UserError(HIST_AUTO_BINS_MESSAGE.format(n=bin_count, limit=MAX_HIST_BINS), field="区間の数")
    max_height = max(float(np.histogram(v.to_numpy(dtype=float), bins=edges, density=plot.hist_density)[0].max()) for v in values)
    ext = _Extents()
    ext.add("x", float(edges[0]), float(edges[-1]))
    ext.add("y", 0.0, max_height)
    return _finish(
        settings, plans, warnings, "", None, axes_args=("log" if settings.axes.x.scale == "log" else "number", ext, 0),
        hist=HistPlan(bins=bins, density=plot.hist_density, bin_count=bin_count, max_height=max_height),
    )


def _finish(
    settings: Settings,
    plans: list[SeriesPlan],
    warnings: list[dict],
    x_label: str,
    bar_x_index,
    *,
    datetime_x: bool = False,
    thin_categorical_x: bool = False,
    bar_date_format: str | None = None,
    axes_args: tuple | None = None,  # (X の軸の種類, _Extents, カテゴリ数[, Y の軸の種類（横棒の縦軸）])
    fits: tuple[FitPlan, ...] = (),
    hist: HistPlan | None = None,
) -> PlotPlan:
    primary = [p.data_label for p in plans if not p.secondary]
    secondary = [p.data_label for p in plans if p.secondary]
    uses_secondary = any(p.secondary and p.has_points for p in plans)
    x_kind, ext, categories, *rest = axes_args or ("number", _Extents(), 0)
    y_kind = rest[0] if rest else None
    annotations = _plan_annotations(settings, x_kind, uses_secondary, ext, y_kind)  # 範囲を ext に足すので、軸の計画より前
    plot_type = settings.plot.type
    y_label = primary[0] if len(primary) == 1 else "values"
    colorbar = None
    if plot_type == "barh":  # 軸ラベルの自動の値だけ入れ替える: 横軸 = 系列1のY列、縦軸 = X列
        x_label, y_label = plans[0].data_label, x_label
    elif plot_type == "hist":
        x_label, y_label = plans[0].data_label, "確率密度" if settings.plot.hist_density else "度数"
    elif plot_type == "scatterColor":
        colorbar = ColorbarPlan(settings.plot.colormap, settings.plot.colorbar_label or plans[0].color_label)
    return PlotPlan(
        skip_rows=settings.plot.skip_rows,
        plot_type=settings.plot.type,
        series=tuple(plans),
        x_label=x_label,
        y_label=y_label,
        y2_label=(secondary[0] if len(secondary) == 1 else "values") if uses_secondary else None,
        bar_x_index=bar_x_index,
        plotted_count=sum(1 for p in plans if p.has_points),
        uses_secondary=uses_secondary,
        warnings=tuple(warnings),
        datetime_x=datetime_x,
        thin_categorical_x=thin_categorical_x,
        bar_date_format=bar_date_format,
        axes=_plan_axes(settings, x_kind, uses_secondary, ext, categories, y_kind),
        annotations=annotations,
        fits=fits,
        hist=hist,
        colorbar=colorbar,
    )
