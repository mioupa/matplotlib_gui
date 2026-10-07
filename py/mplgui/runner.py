"""Figure → 画像バイト列、保存ファイル名、旧 Pythonコード(beta) タブの実行（DOM / js には依存しない）。

カスタムコードは設定とは別の引数で受け取る。GUI 設定による上書き（A8）は従来どおり残している（Phase 2 で変更予定）。
"""
from __future__ import annotations

import base64
import builtins
import io
import traceback
from functools import partial

import matplotlib.pyplot as plt
import pandas as pd

from .errors import UserError
from .plotting import (
    FigureResult,
    apply_axes_decoration,
    apply_subplot_margins,
    create_figure,
    figure_has_visible_artists,
    get_per_series_xy_data,
    get_plot_data,
    resolve_series_requests,
    settings_scales_and_limits,
    slice_skip_rows,
)
from .settings import Settings, to_legacy_dict

DEFAULT_CUSTOM_PLOT_CODE = """# 利用可能オブジェクト:
# - df: skipRows適用後のDataFrame
# - current_df: 読み込み直後のDataFrame（skipRows未適用）
# - settings: GUI設定(dict)
# - plt, pd
# 必須:
# - fig に Figure を代入
# 任意:
# - plotted_count (int) を設定（未設定時は自動判定）

fig, ax = plt.subplots(figsize=(settings["fig_width"], settings["fig_height"]), dpi=100)

if df.shape[1] < 2:
    raise ValueError("2列以上のデータが必要です。")

x = pd.to_numeric(df.iloc[:, 0], errors="coerce")
y = pd.to_numeric(df.iloc[:, 1], errors="coerce")
mask = x.notna() & y.notna()
if not bool(mask.any()):
    raise ValueError("先頭2列に描画可能な数値データがありません。")

series_settings = settings.get("series_settings", [])
default_legend = ""
if isinstance(series_settings, list) and len(series_settings) > 0:
    default_legend = str(series_settings[0].get("legend_name", "") or "").strip()
if not default_legend:
    default_legend = str(df.columns[1])

ax.plot(
    x[mask],
    y[mask],
    color="#005AFF",
    linewidth=2.0,
    marker="o",
    markersize=4,
    label=default_legend,
)
ax.set_title(settings["title"])
ax.set_xlabel(settings["x_label"] or str(df.columns[0]))
ax.set_ylabel(settings["y_label"] or str(df.columns[1]))
ax.grid(True, alpha=0.3)
ax.legend(loc="best", edgecolor="black")
fig.tight_layout()

plotted_count = 1
"""

_FORMATS = {
    "png": ("png", "image/png", "png"),
    "jpg": ("jpeg", "image/jpeg", "jpg"),
    "svg": ("svg", "image/svg+xml", "svg"),
    "pdf": ("pdf", "application/pdf", "pdf"),
}


def figure_to_bytes(fig, file_format: str, transparent: bool = False, dpi: int = 120) -> tuple[bytes, str, str]:
    """Figure を指定形式のバイト列にする。戻り値は (bytes, mime, 拡張子)。"""
    fmt = (file_format or "").lower()
    if fmt not in _FORMATS:
        raise UserError("保存形式が不正です。", field="保存形式")
    if transparent and fmt not in {"png", "svg"}:
        raise UserError("背景透過を有効にした場合、保存形式はpngまたはsvgを選択してください。", field="保存形式")
    save_format, mime, ext = _FORMATS[fmt]

    save_kwargs = {}
    if save_format in {"png", "jpeg"}:
        save_kwargs["dpi"] = dpi
    if save_format == "jpeg":
        save_kwargs["facecolor"] = "white"
    if transparent:
        save_kwargs["transparent"] = True

    buffer = io.BytesIO()
    fig.savefig(buffer, format=save_format, **save_kwargs)
    return buffer.getvalue(), mime, ext


def figure_to_data_uri(fig, file_format: str, transparent: bool = False, dpi: int = 120) -> tuple[str, str]:
    data, mime, ext = figure_to_bytes(fig, file_format, transparent, dpi)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", ext


def build_filename(raw_filename: str, ext: str) -> str:
    """保存ファイル名を作る。空欄時は plot.<ext>。入力中の拡張子は取り除いて ext を付ける。"""
    raw_filename = (raw_filename or "").strip()
    if raw_filename:
        filename_base = raw_filename.rstrip(".")
        if "." in filename_base:
            filename_base = filename_base.rsplit(".", 1)[0]
        filename_base = filename_base.strip() or "plot"
        return f"{filename_base}.{ext}"
    return f"plot.{ext}"


# ---------------------------------------------------------------- legacy custom code


def _apply_gui_overrides_to_custom_figure(fig, legacy: dict, settings: Settings) -> None:
    """従来どおり、GUI設定（タイトル・ラベル・スケール・目盛・グリッド・凡例）でカスタムコードの図を上書きする。"""
    if fig is None or not hasattr(fig, "axes") or len(fig.axes) == 0:
        return

    ax = fig.axes[0]
    ax2 = fig.axes[1] if len(fig.axes) >= 2 else None
    font_size = float(legacy.get("font_size", 15) or 15)
    legend_location = legacy["legend_location"]

    if legacy["title"]:
        ax.set_title(legacy["title"], fontsize=font_size + 2)
    ax.set_xlabel(legacy["x_label"] or ax.get_xlabel(), fontsize=font_size)
    ax.set_ylabel(legacy["y_label"] or ax.get_ylabel(), fontsize=font_size)
    if ax2 is not None:
        ax2.set_ylabel(legacy["y2_label"] or ax2.get_ylabel(), fontsize=font_size)

    scales, limits = settings_scales_and_limits(settings)
    apply_axes_decoration(
        ax, ax2, font_size=font_size, scales=scales, limits=limits,
        show_major_grid=legacy["show_major_grid"], show_minor_grid=legacy["show_minor_grid"],
    )

    for axis in fig.axes:
        existing_legend = axis.get_legend()
        if existing_legend is not None:
            existing_legend.remove()

    if legend_location == "none":
        return

    handles = []
    labels = []
    for axis in fig.axes:
        h, lab = axis.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(lab)
    if not labels:
        return

    for i, setting in enumerate(legacy.get("series_settings", [])):
        if i >= len(labels):
            break
        legend_name = str(setting.get("legend_name", "") or "").strip()
        if legend_name:
            labels[i] = legend_name

    ax.legend(handles, labels, loc=legend_location, fontsize=max(font_size - 1, 1), edgecolor="black")


def run_custom_code(code: str, df_full: pd.DataFrame, settings: Settings) -> FigureResult:
    """Pythonコード(beta)を実行し、fig を取り出す。名前空間は従来と同じ。"""
    skip_rows = settings.plot.skip_rows
    df = slice_skip_rows(df_full, skip_rows)
    if not (code or "").strip():
        raise UserError("カスタムコードが空です。", field="カスタムコード")

    legacy = to_legacy_dict(settings)
    series_legacy = legacy["series_settings"]
    x_request = settings.plot.x_column
    helper_plot_data = partial(get_plot_data, x_request=x_request)
    context = {
        "df": df,
        "current_df": df_full,
        "settings": legacy,
        "series_settings": series_legacy,
        "helpers": {
            "get_plot_data": helper_plot_data,
            "get_per_series_xy_data": get_per_series_xy_data,
            "resolve_series_requests": resolve_series_requests,
        },
    }
    local_scope = {
        "df": df.copy(),
        "current_df": df_full.copy(),
        "settings": legacy,
        "ctx": context,
        "series_settings": series_legacy,
        "get_plot_data": helper_plot_data,
        "get_per_series_xy_data": get_per_series_xy_data,
        "resolve_series_requests": resolve_series_requests,
        "plt": plt,
        "pd": pd,
        "fig": None,
        "plotted_count": None,
        "skip_rows": skip_rows,
    }
    global_scope = {"__builtins__": builtins, "plt": plt, "pd": pd}

    before = set(plt.get_fignums())

    def close_new_figures(keep=None):
        for num in set(plt.get_fignums()) - before:
            if keep is not None and getattr(keep, "number", None) == num:
                continue
            plt.close(num)

    fig = None
    try:
        try:
            exec(code, global_scope, local_scope)
        except UserError:
            raise
        except Exception as exc:
            raise UserError(
                f"カスタムコードの実行に失敗しました: {exc}", field="カスタムコード", detail=traceback.format_exc()
            ) from exc

        fig = local_scope.get("fig")
        if fig is None:
            raise UserError("カスタムコードで fig を生成してください。", field="カスタムコード")
        if not hasattr(fig, "savefig"):
            raise UserError("fig には matplotlib.figure.Figure を設定してください。", field="カスタムコード")
        _apply_gui_overrides_to_custom_figure(fig, legacy, settings)
        m = settings.plot.margins
        apply_subplot_margins(
            fig, {"left": m.left, "right": m.right, "bottom": m.bottom, "top": m.top}, use_tight_layout_if_auto=True
        )

        plotted_raw = local_scope.get("plotted_count")
        if plotted_raw is None:
            plotted_count = 1 if figure_has_visible_artists(fig) else 0
        else:
            try:
                plotted_count = int(plotted_raw)
            except Exception:
                raise UserError("plotted_count は整数で指定してください。", field="カスタムコード")
        if plotted_count <= 0 and figure_has_visible_artists(fig):
            plotted_count = 1
        if plotted_count <= 0:
            raise UserError("描画可能なデータがありません。")

        custom_skip_rows = local_scope.get("skip_rows", skip_rows)
        try:
            custom_skip_rows = int(custom_skip_rows)
        except Exception:
            custom_skip_rows = skip_rows
        if custom_skip_rows < 0:
            custom_skip_rows = skip_rows
    except BaseException:
        close_new_figures()
        if fig is not None and hasattr(fig, "number"):
            plt.close(fig)
        raise
    close_new_figures(keep=fig)
    return FigureResult(fig=fig, plotted_count=plotted_count, skip_rows=custom_skip_rows)


def make_figure(df_full: pd.DataFrame, settings: Settings, custom_code: str | None = None) -> FigureResult:
    """custom_code が None なら GUI 設定で、文字列ならそのコードで Figure を作る。"""
    if custom_code is not None:
        return run_custom_code(custom_code, df_full, settings)
    return create_figure(df_full, settings)
