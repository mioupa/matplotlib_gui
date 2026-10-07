"""TRANSITIONAL: 設定 → matplotlib Figure（Phase 2 で codegen に置き換える）。

DOM / js には依存しない。呼び出し側が戻り値の Figure を必ず plt.close() すること。
列指定は "__idx__N"（列番号）形式を使う。同名列があっても区別できる。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import pandas as pd

from .errors import UserError
from .settings import MarginSettings, Settings, series_to_legacy


@dataclass
class FigureResult:
    fig: object
    plotted_count: int
    skip_rows: int
    warnings: list = field(default_factory=list)  # [{"series": 1始まり, "message": str}]（A7 で使用）


# ---------------------------------------------------------------- dropped (non-numeric) values (A7)

MAX_EXAMPLES = 3


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
    """数値に変換する。戻り値は (変換後, 変換できなかった非空欄のセル数, 例（最大3件・重複なし）)。空欄は数えない。"""
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


def _no_data_message(entries: list[dict]) -> str:
    base = "描画可能な数値データがありません。"
    hints = [w["message"] for e in entries for w in e.get("warnings", [])]
    if hints:
        return base + "数値に変換できない値は除外されます。" + hints[0]
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


# ---------------------------------------------------------------- column helpers (legacy-dict based)


def parse_column_index(requested: str) -> int | None:
    if not requested.startswith("__idx__"):
        return None
    idx_text = requested.replace("__idx__", "", 1)
    if not idx_text.isdigit():
        return None
    return int(idx_text)


def resolve_column(df: pd.DataFrame, requested: str):
    if requested.startswith("__idx__"):
        idx_text = requested.replace("__idx__", "", 1)
        if not idx_text.isdigit():
            raise UserError(f"列の指定が不正です: {requested}")
        idx = int(idx_text)
        if idx < 0 or idx >= len(df.columns):
            raise UserError(f"列番号 {idx} がデータの列数を超えています。")
        return df.columns[idx]

    if requested in df.columns:
        return requested
    matched = [col for col in df.columns if str(col) == requested]
    if len(matched) == 1:
        return matched[0]
    raise UserError(f"列が見つかりません: {requested}")


def get_series_from_request(df: pd.DataFrame, requested: str) -> tuple[pd.Series, str, int]:
    idx = parse_column_index(requested)
    if idx is not None:
        if idx < 0 or idx >= len(df.columns):
            raise UserError(f"列番号 {idx} がデータの列数を超えています。")
        return df.iloc[:, idx], str(df.columns[idx]), idx

    resolved = resolve_column(df, requested)
    found_idx = -1
    for i, col in enumerate(df.columns):
        if col == resolved:
            found_idx = i
            break
    return df[resolved], str(resolved), found_idx


def resolve_series_requests(df: pd.DataFrame, settings: list[dict]) -> list[str]:
    """Y列が自動("")の系列に、未使用の最初の数値列を割り当てる。"""
    numeric_indices = [i for i, dtype in enumerate(df.dtypes) if pd.api.types.is_numeric_dtype(dtype)]
    candidates = numeric_indices if numeric_indices else [0]
    used_indices = set()
    resolved = []

    for setting in settings:
        request = setting["y_request"]
        if request:
            idx = parse_column_index(request)
            if idx is not None:
                used_indices.add(idx)
            resolved.append(request)
            continue

        chosen = None
        for idx in candidates:
            if idx not in used_indices:
                chosen = idx
                break
        if chosen is None:
            chosen = candidates[0]
        used_indices.add(chosen)
        resolved.append(f"__idx__{chosen}")

    return resolved


def get_plot_data(df: pd.DataFrame, series_settings: list[dict], x_request: str = "") -> tuple[pd.Series, str, list[dict]]:
    """共通X列を使うデータ整形（bar 用）。x_request が空なら index。"""
    x_req = (x_request or "").strip()
    y_requests = resolve_series_requests(df, series_settings)

    if x_req:
        x, x_label, _ = get_series_from_request(df, x_req)
    else:
        x = pd.Series(df.index, name="index")
        x_label = "index"

    plot_df = pd.DataFrame({"x": x})
    series_entries = []
    for i, (setting, request) in enumerate(zip(series_settings, y_requests)):
        y_series, y_name, y_idx = get_series_from_request(df, request)
        y_key = f"y_{i}"
        label_suffix = f" [{y_idx}]" if y_idx >= 0 else ""
        data_label = f"{y_name}{label_suffix}"
        numeric, dropped, examples = coerce_numeric(y_series)
        plot_df[y_key] = numeric
        entry = dict(setting)
        entry["warnings"] = [dropped_warning(i + 1, f"系列{i + 1}（{y_name}）", dropped, examples)] if dropped else []
        entry["y_key"] = y_key
        entry["data_label"] = data_label
        entry["legend_label"] = setting.get("legend_name") or data_label
        series_entries.append(entry)

    y_keys = [entry["y_key"] for entry in series_entries]
    plot_df = plot_df.dropna(subset=y_keys, how="all")
    if plot_df.empty:
        raise UserError(_no_data_message(series_entries))

    for entry in series_entries:
        entry["y_series"] = plot_df[entry["y_key"]]

    return plot_df["x"], x_label, series_entries


def get_per_series_xy_data(df: pd.DataFrame, series_settings: list[dict]) -> tuple[list[dict], str]:
    """系列ごとにX列を指定できるデータ整形（line / scatter 用）。"""
    y_requests = resolve_series_requests(df, series_settings)
    entries = []
    x_labels = []

    for setting, y_request in zip(series_settings, y_requests):
        x_request = setting.get("x_request", "").strip()
        if x_request:
            x_series, x_label, _ = get_series_from_request(df, x_request)
        else:
            x_series = pd.Series(df.index, name="index")
            x_label = "index"

        y_series, y_name, y_idx = get_series_from_request(df, y_request)
        label_suffix = f" [{y_idx}]" if y_idx >= 0 else ""
        data_label = f"{y_name}{label_suffix}"

        i = len(entries)
        warnings_list = []
        x_series = x_series.reset_index(drop=True)
        if x_request and not pd.api.types.is_numeric_dtype(x_series.dtype) and _looks_numeric(x_series):
            x_series, x_dropped, x_examples = coerce_numeric(x_series)
            if x_dropped:
                warnings_list.append(dropped_warning(i + 1, f"系列{i + 1}のX列（{x_label}）", x_dropped, x_examples))
        y_numeric, y_dropped, y_examples = coerce_numeric(y_series)
        if y_dropped:
            warnings_list.append(dropped_warning(i + 1, f"系列{i + 1}（{y_name}）", y_dropped, y_examples))

        entry = dict(setting)
        entry["warnings"] = warnings_list
        entry["x_series"] = x_series
        entry["y_series"] = y_numeric.reset_index(drop=True)
        entry["data_label"] = data_label
        entry["legend_label"] = setting.get("legend_name") or data_label
        entry["x_label"] = x_label
        entries.append(entry)
        x_labels.append(x_label)

    has_points = False
    for entry in entries:
        mask = entry["y_series"].notna() & pd.notna(entry["x_series"])
        if bool(mask.any()):
            has_points = True
            break
    if not has_points:
        raise UserError(_no_data_message(entries))

    common_x_label = x_labels[0] if len(set(x_labels)) == 1 else "x"
    return entries, common_x_label


# ---------------------------------------------------------------- styling shared with the legacy override


def apply_axis_scale_and_limits(target_ax, axis_kind: str, axis_label: str, scale: str,
                                min_value: float | None, max_value: float | None) -> None:
    if scale not in {"linear", "log"}:
        raise UserError(f"{axis_label}軸スケールが不正です。")
    if min_value is not None and max_value is not None and min_value >= max_value:
        raise UserError(f"{axis_label}軸の範囲は最小値 < 最大値で指定してください。")
    if scale == "log" and ((min_value is not None and min_value <= 0) or (max_value is not None and max_value <= 0)):
        raise UserError(f"{axis_label}軸を対数にする場合、範囲は0より大きい値で指定してください。")

    try:
        if axis_kind == "x":
            target_ax.set_xscale(scale)
            if min_value is not None or max_value is not None:
                target_ax.set_xlim(left=min_value, right=max_value)
        elif axis_kind == "y":
            target_ax.set_yscale(scale)
            if min_value is not None or max_value is not None:
                target_ax.set_ylim(bottom=min_value, top=max_value)
        else:
            raise UserError(f"軸種別が不正です: {axis_kind}")
    except UserError:
        raise
    except Exception as exc:
        raise UserError(f"{axis_label}軸設定の適用に失敗しました。", detail=str(exc)) from exc


def apply_subplot_margins(fig, margins: dict, use_tight_layout_if_auto: bool = False) -> None:
    provided = {k: v for k, v in (margins or {}).items() if v is not None}
    if provided:
        if use_tight_layout_if_auto and len(provided) < 4:
            try:
                fig.tight_layout()
                auto_margins = {
                    "left": fig.subplotpars.left,
                    "right": fig.subplotpars.right,
                    "bottom": fig.subplotpars.bottom,
                    "top": fig.subplotpars.top,
                }
                auto_margins.update(provided)
                fig.subplots_adjust(**auto_margins)
                return
            except Exception:
                pass
        try:
            fig.subplots_adjust(**provided)
        except Exception as exc:
            raise UserError("余白設定の適用に失敗しました。", detail=str(exc)) from exc
    elif use_tight_layout_if_auto:
        fig.tight_layout()


def apply_axes_decoration(ax, ax2, *, font_size: float, scales: dict, limits: dict,
                          show_major_grid: bool, show_minor_grid: bool) -> None:
    """スケール・範囲・目盛（内向き）・グリッドを設定する。

    scales / limits は {"x","y","y2"} をキーにし、limits の値は (min, max)。
    """
    apply_axis_scale_and_limits(ax, "x", "X", scales["x"], *limits["x"])
    apply_axis_scale_and_limits(ax, "y", "Y", scales["y"], *limits["y"])
    if ax2 is not None:
        apply_axis_scale_and_limits(ax2, "y", "第2Y", scales["y2"], *limits["y2"])

    label_size = max(font_size - 1, 1)
    ax.tick_params(axis="x", which="both", direction="in", bottom=True, top=False, labelsize=label_size)
    ax.tick_params(axis="y", which="both", direction="in", left=True, right=False, labelsize=label_size)
    if ax2 is not None:
        ax2.tick_params(axis="y", which="both", direction="in", left=False, right=True, labelsize=label_size)

    if show_minor_grid:
        ax.minorticks_on()
        if ax2 is not None:
            ax2.minorticks_on()
    else:
        ax.minorticks_off()
        if ax2 is not None:
            ax2.minorticks_off()

    ax.grid(False, which="both", axis="both")
    if show_major_grid:
        ax.grid(True, which="major", axis="both", alpha=0.3)
    if show_minor_grid:
        ax.grid(True, which="minor", axis="both", alpha=0.2, linestyle=":")
    if ax2 is not None:
        ax2.grid(False, which="both", axis="y")
        if show_major_grid:
            ax2.grid(True, which="major", axis="y", alpha=0.3)
        if show_minor_grid:
            ax2.grid(True, which="minor", axis="y", alpha=0.2, linestyle=":")


def settings_scales_and_limits(settings: Settings) -> tuple[dict, dict]:
    a = settings.axes
    scales = {"x": a.x.scale, "y": a.y.scale, "y2": a.y2.scale}
    limits = {"x": (a.x.min, a.x.max), "y": (a.y.min, a.y.max), "y2": (a.y2.min, a.y2.max)}
    return scales, limits


def figure_has_visible_artists(fig) -> bool:
    if fig is None or not hasattr(fig, "axes"):
        return False
    for axis in fig.axes:
        if len(axis.lines) > 0 or len(axis.collections) > 0 or len(axis.patches) > 0 or len(axis.images) > 0:
            return True
        if hasattr(axis, "containers") and len(axis.containers) > 0:
            return True
    return False


# ---------------------------------------------------------------- figure creation


def slice_skip_rows(df_full: pd.DataFrame, skip_rows: int) -> pd.DataFrame:
    if skip_rows >= len(df_full):
        raise UserError("スキップ行数がデータ行数以上です。「除外する先頭行数」を小さくしてください。", field="除外する先頭行数")
    return df_full.iloc[skip_rows:].reset_index(drop=True)


def create_figure(df_full: pd.DataFrame, settings: Settings) -> FigureResult:
    """設定どおりの Figure を作る。失敗時は作りかけの Figure を閉じて例外を送出する。"""
    plot = settings.plot
    skip_rows = plot.skip_rows
    df = slice_skip_rows(df_full, skip_rows)
    series_settings = series_to_legacy(settings)
    plot_type = plot.type
    font_size = plot.font_size

    fig, ax = plt.subplots(figsize=(plot.figure.width, plot.figure.height), dpi=100)
    try:
        ax2 = None
        plotted_labels = []

        def target_axis(entry):
            nonlocal ax2
            if entry.get("use_secondary_axis", False):
                if ax2 is None:
                    ax2 = ax.twinx()
                return ax2
            return ax

        if plot_type in {"line", "scatter"}:
            all_entries, x_label = get_per_series_xy_data(df, series_settings)
            for entry in all_entries:
                x_series = entry["x_series"]
                y_series = entry["y_series"]
                mask = y_series.notna() & pd.notna(x_series)
                if not bool(mask.any()):
                    continue
                target_ax = target_axis(entry)
                if plot_type == "line":
                    marker = "o" if entry["marker_size"] > 0 else ""
                    marker_size_for_line = entry["marker_size"] ** 0.5 if entry["marker_size"] > 0 else 0
                    target_ax.plot(
                        x_series[mask], y_series[mask],
                        color=entry["color"], linewidth=entry["line_width"], linestyle=entry["line_style"],
                        marker=marker, markersize=marker_size_for_line, label=entry["legend_label"],
                    )
                else:
                    target_ax.scatter(
                        x_series[mask], y_series[mask],
                        color=entry["color"], s=entry["marker_size"], label=entry["legend_label"],
                    )
                plotted_labels.append(entry["legend_label"])
        else:
            x, x_label, all_entries = get_plot_data(df, series_settings, plot.x_column)
            if len(all_entries) == 1:
                entry = all_entries[0]
                y_series = entry["y_series"]
                mask = y_series.notna() & pd.notna(x)
                if bool(mask.any()):
                    target_axis(entry).bar(
                        x[mask], y_series[mask],
                        color=entry["color"], linewidth=entry["line_width"], linestyle=entry["line_style"],
                        label=entry["legend_label"],
                    )
                    plotted_labels.append(entry["legend_label"])
            else:
                x_labels = [str(v) for v in x.tolist()]
                positions = list(range(len(x_labels)))
                width = 0.8 / len(all_entries)
                for i, entry in enumerate(all_entries):
                    y_values = [float(v) if pd.notna(v) else 0.0 for v in entry["y_series"].tolist()]
                    offset = -0.4 + (width / 2.0) + (i * width)
                    target_axis(entry).bar(
                        [p + offset for p in positions], y_values, width=width,
                        color=entry["color"], linewidth=entry["line_width"], linestyle=entry["line_style"],
                        label=entry["legend_label"],
                    )
                    plotted_labels.append(entry["legend_label"])
                if positions:
                    if len(positions) > 25:
                        step = max(1, len(positions) // 25)
                        tick_positions = [positions[i] for i in range(0, len(positions), step)]
                        tick_labels = [x_labels[i] for i in range(0, len(x_labels), step)]
                    else:
                        tick_positions = positions
                        tick_labels = x_labels
                    ax.set_xticks(tick_positions)
                    ax.set_xticklabels(tick_labels, rotation=45, ha="right")

        if not plotted_labels:
            raise UserError("描画可能なデータがありません。")

        primary_labels = [e["data_label"] for e in all_entries if not e.get("use_secondary_axis", False)]
        secondary_labels = [e["data_label"] for e in all_entries if e.get("use_secondary_axis", False)]
        axes = settings.axes

        if plot.title:
            ax.set_title(plot.title, fontsize=font_size + 2)
        ax.set_xlabel(axes.x.label or x_label, fontsize=font_size)
        if axes.y.label:
            ax.set_ylabel(axes.y.label, fontsize=font_size)
        else:
            ax.set_ylabel(primary_labels[0] if len(primary_labels) == 1 else "values", fontsize=font_size)
        if ax2 is not None:
            right_default = secondary_labels[0] if len(secondary_labels) == 1 else "values"
            ax2.set_ylabel(axes.y2.label or right_default, fontsize=font_size)

        scales, limits = settings_scales_and_limits(settings)
        apply_axes_decoration(
            ax, ax2, font_size=font_size, scales=scales, limits=limits,
            show_major_grid=plot.grid_major, show_minor_grid=plot.grid_minor,
        )

        if plot.legend_location != "none" and plotted_labels:
            handles, labels = ax.get_legend_handles_labels()
            if ax2 is not None:
                h2, l2 = ax2.get_legend_handles_labels()
                handles, labels = handles + h2, labels + l2
            if labels:
                ax.legend(handles, labels, loc=plot.legend_location, fontsize=max(font_size - 1, 1), edgecolor="black")

        m: MarginSettings = plot.margins
        apply_subplot_margins(
            fig, {"left": m.left, "right": m.right, "bottom": m.bottom, "top": m.top}, use_tight_layout_if_auto=True,
        )
    except BaseException:
        plt.close(fig)
        raise
    collected = [w for entry in all_entries for w in entry.get("warnings", [])]
    return FigureResult(fig=fig, plotted_count=len(plotted_labels), skip_rows=skip_rows, warnings=collected)
