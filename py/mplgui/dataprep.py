"""DataFrame の中身を見て決める処理（codegen に渡す描画計画 PlotPlan を作る）。

js / pyodide には依存しない。列指定は "__idx__N"（列番号）形式。
ここで決めるのは「データを見ないと分からないこと」だけ（Y 列の自動割り当て、X の数値変換の要否、
描ける点があるか、数値に変換できず除外した値の警告、データ由来のエラー）。コードの組み立ては codegen が行う。
"""
from __future__ import annotations

from dataclasses import dataclass

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


def dropped_warning(series_no: int, what: str, count: int, examples: list[str]) -> dict:
    ex = ", ".join(f'"{e}"' for e in examples)
    message = f"{what}: 数値に変換できない値が{count}件あったため、その行を除外しました（例: {ex}）。"
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


def slice_skip_rows(df_full: pd.DataFrame, skip_rows: int) -> pd.DataFrame:
    if skip_rows >= len(df_full):
        raise UserError("スキップ行数がデータ行数以上です。「除外する先頭行数」を小さくしてください。", field="除外する先頭行数")
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
    categorical_x: bool  # line / scatter で X が数値でない列（文字列・日時）のまま使う
    marker_size: float
    has_points: bool
    secondary: bool


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

    @property
    def plotted(self) -> tuple[SeriesPlan, ...]:
        return tuple(s for s in self.series if s.has_points)


def _label_for(df: pd.DataFrame, idx: int) -> tuple[str, str]:
    name = str(df.columns[idx])
    return name, f"{name} [{idx}]"


def plan_plot(df_full: pd.DataFrame, settings: Settings) -> PlotPlan:
    """データと設定から描画計画を作る。データ由来の問題は UserError にする。"""
    plot = settings.plot
    df = slice_skip_rows(df_full, plot.skip_rows)
    y_requests = resolve_y_indices(df, [s.y for s in settings.series])
    if plot.type in {"line", "scatter"}:
        return _plan_xy(df, settings, y_requests)
    return _plan_bar(df, settings, y_requests)


def _plan_xy(df: pd.DataFrame, settings: Settings, y_requests: list[str]) -> PlotPlan:
    plot_type = settings.plot.type
    plans: list[SeriesPlan] = []
    warnings: list[dict] = []
    for n, (series, y_request) in enumerate(zip(settings.series, y_requests), start=1):
        x_index = resolve_column_index(df, series.x) if series.x else None
        x_label = str(df.columns[x_index]) if x_index is not None else "index"
        y_index = resolve_column_index(df, y_request)
        y_name, data_label = _label_for(df, y_index)

        x_series = df.iloc[:, x_index] if x_index is not None else pd.Series(df.index)
        convert_x = False
        if x_index is not None and not pd.api.types.is_numeric_dtype(x_series.dtype) and _looks_numeric(x_series):
            convert_x = True
            x_series, x_dropped, x_examples = coerce_numeric(x_series)
            if x_dropped:
                warnings.append(dropped_warning(n, f"系列{n}のX列（{x_label}）", x_dropped, x_examples))
        y_numeric, y_dropped, y_examples = coerce_numeric(df.iloc[:, y_index])
        if y_dropped:
            warnings.append(dropped_warning(n, f"系列{n}（{y_name}）", y_dropped, y_examples))

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
                categorical_x=x_index is not None and not convert_x and not pd.api.types.is_numeric_dtype(x_series.dtype),
                marker_size=series.effective_marker_size(plot_type),
                has_points=has_points,
                secondary=series.secondary_axis,
            )
        )

    if not any(p.has_points for p in plans):
        raise UserError(_no_data_message(warnings))

    x_labels = [p.x_label for p in plans]
    common_x = x_labels[0] if len(set(x_labels)) == 1 else "x"
    return _finish(settings, plans, warnings, common_x, None)


def _plan_bar(df: pd.DataFrame, settings: Settings, y_requests: list[str]) -> PlotPlan:
    plot = settings.plot
    x_req = plot.x_column.strip()
    if x_req:
        bar_x_index = resolve_column_index(df, x_req)
        x = df.iloc[:, bar_x_index]
        x_label = str(df.columns[bar_x_index])
    else:
        bar_x_index = None
        x = pd.Series(df.index)
        x_label = "index"

    frame = pd.DataFrame({"x": x})
    plans: list[SeriesPlan] = []
    warnings: list[dict] = []
    for i, (series, y_request) in enumerate(zip(settings.series, y_requests)):
        n = i + 1
        y_index = resolve_column_index(df, y_request)
        y_name, data_label = _label_for(df, y_index)
        numeric, dropped, examples = coerce_numeric(df.iloc[:, y_index])
        frame[f"y_{i}"] = numeric
        if dropped:
            warnings.append(dropped_warning(n, f"系列{n}（{y_name}）", dropped, examples))
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
    return _finish(settings, plans, warnings, x_label, bar_x_index)


def _finish(settings: Settings, plans: list[SeriesPlan], warnings: list[dict], x_label: str, bar_x_index) -> PlotPlan:
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
    )
