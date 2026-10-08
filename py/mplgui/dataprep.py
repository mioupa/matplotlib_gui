"""DataFrame の中身を見て決める処理（codegen に渡す描画計画 PlotPlan を作る）。

js / pyodide には依存しない。列指定は "__idx__N"（列番号）形式。
ここで決めるのは「データを見ないと分からないこと」だけ（Y 列の自動割り当て、X の数値変換の要否、
描ける点があるか、数値に変換できず除外した値の警告、データ由来のエラー）。コードの組み立ては codegen が行う。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

import pandas as pd

from .errors import UserError
from .settings import Settings

MAX_EXAMPLES = 3
NO_DRAWABLE_DATA = "描画可能なデータがありません。"

# ---------------------------------------------------------------- dropped (non-numeric) values (A7)


def _is_blank_cell(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() == ""


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


def _looks_numeric(raw: pd.Series) -> bool:
    """文字列を含む列でも、空欄以外の半数以上が数値に変換できるなら数値列として扱う。"""
    if pd.api.types.is_numeric_dtype(raw.dtype):
        return True
    non_blank = [v for v in raw.tolist() if not _is_blank_cell(v)]
    if not non_blank:
        return False
    ok = pd.to_numeric(pd.Series(non_blank, dtype=object), errors="coerce").notna().sum()
    return ok * 2 >= len(non_blank)


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


@dataclass(frozen=True)
class PlanSource:
    """描画に使うデータ元（load.files の並びの順）。"""

    id: str
    number: int  # 「データN」の N（load.files の位置。ファイルの一覧が空なら 1）
    var: str  # DataFrame の変数名（"df" または "dfN"）
    name: str  # ファイル名（load.files の name。無ければ空）


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

    @property
    def plotted(self) -> tuple[SeriesPlan, ...]:
        return tuple(s for s in self.series if s.has_points)


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


NOT_LOADED_MESSAGE = "データ{n}（{name}）を読み込めていません。読込設定やファイルを確認してください。"
BAR_SOURCE_MESSAGE = "棒グラフでは、すべての系列に同じデータ元を選んでください。"


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
    if plot.type == "bar" and len(set(ids)) > 1:
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
    for sid in order:
        idx = [i for i, x in enumerate(ids) if x == sid]
        resolved = resolve_y_indices(frames[sid], [settings.series[i].y for i in idx])
        for i, r in zip(idx, resolved):
            y_requests[i] = r
    dfs = [frames[sid] for sid in ids]
    if plot.type in {"line", "scatter"}:
        plan = _plan_xy(dfs, settings, y_requests)
    else:
        plan = _plan_bar(dfs[0], settings, y_requests)
    series = tuple(replace(sp, data_id=sid, data_var=var_of[sid]) for sp, sid in zip(plan.series, ids))
    return replace(plan, series=series, sources=sources, multi_source=multi)


def _plan_xy(dfs: list[pd.DataFrame], settings: Settings, y_requests: list[str]) -> PlotPlan:
    plot_type = settings.plot.type
    plans: list[SeriesPlan] = []
    warnings: list[dict] = []
    category_values: set = set()
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

        has_points = bool((y_numeric.notna() & pd.notna(x_series)).any())
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
                marker_size=series.effective_marker_size(plot_type),
                has_points=has_points,
                secondary=series.secondary_axis,
                datetime_x=datetime_x,
            )
        )
        if has_points and x_index is not None and plans[-1].categorical_x:
            shown = x_series[y_numeric.notna() & x_series.notna()]
            category_values.update(shown.tolist())

    if not any(p.has_points for p in plans):
        raise UserError(_no_data_message(warnings))

    _check_datetime_x(settings, plans)
    x_labels = [p.x_label for p in plans]
    common_x = x_labels[0] if len(set(x_labels)) == 1 else "x"
    return _finish(
        settings, plans, warnings, common_x, None,
        datetime_x=any(p.datetime_x and p.has_points for p in plans),
        thin_categorical_x=len(category_values) > MAX_CATEGORY_TICKS,
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
    if axis.min is not None or axis.max is not None:
        raise UserError("X が日時の列のときは、X軸の最小値・最大値は指定できません。空欄にしてください。", field="X軸の範囲")


def _plan_bar(df: pd.DataFrame, settings: Settings, y_requests: list[str]) -> PlotPlan:
    plot = settings.plot
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
            )
        )

    y_keys = [f"y_{i}" for i in range(len(plans))]
    frame = frame.dropna(subset=y_keys, how="all")
    if frame.empty:
        raise UserError(_no_data_message(warnings))

    if len(plans) == 1:
        has_points = bool((frame["y_0"].notna() & pd.notna(frame["x"])).any())
        if not has_points:
            raise UserError(NO_DRAWABLE_DATA)
    bar_date_format = None
    if datetime_x:
        bar_date_format = settings.axes.x.date_format or auto_bar_date_format(x)
    return _finish(settings, plans, warnings, x_label, bar_x_index, datetime_x=datetime_x, bar_date_format=bar_date_format)


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
) -> PlotPlan:
    primary = [p.data_label for p in plans if not p.secondary]
    secondary = [p.data_label for p in plans if p.secondary]
    uses_secondary = any(p.secondary and p.has_points for p in plans)
    return PlotPlan(
        skip_rows=settings.plot.skip_rows,
        plot_type=settings.plot.type,
        series=tuple(plans),
        x_label=x_label,
        y_label=primary[0] if len(primary) == 1 else "values",
        y2_label=(secondary[0] if len(secondary) == 1 else "values") if uses_secondary else None,
        bar_x_index=bar_x_index,
        plotted_count=sum(1 for p in plans if p.has_points),
        uses_secondary=uses_secondary,
        warnings=tuple(warnings),
        datetime_x=datetime_x,
        thin_categorical_x=thin_categorical_x,
        bar_date_format=bar_date_format,
    )
