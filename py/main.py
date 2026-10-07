import io
import base64
import asyncio
import traceback
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
warnings.simplefilter("ignore", DeprecationWarning)
warnings.filterwarnings(
    "ignore",
    message=".*Pyarrow will become a required dependency of pandas.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*missing from current font.*",
    category=UserWarning,
)
import pandas as pd
from js import Uint8Array, document, window, fetch
from pyodide.ffi import create_proxy

from mplgui.fonts import configure_rcparams, register_font_file
from mplgui.loader import load_dataframe
from mplgui.runner import build_filename, figure_to_data_uri

PREVIEW_ROWS = 100
CURRENT_DF = None
_EVENT_PROXIES = []
JP_FONT_URL = "https://cdn.jsdelivr.net/gh/googlefonts/noto-cjk@main/Sans/OTF/Japanese/NotoSansCJKjp-Regular.otf"
JP_FONT_PATH = "/tmp/NotoSansCJKjp-Regular.otf"
_JP_FONT_READY = False
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

configure_rcparams()


async def _ensure_japanese_font() -> None:
    global _JP_FONT_READY
    if _JP_FONT_READY:
        return
    try:
        target = Path(JP_FONT_PATH)
        if not target.exists():
            response = await fetch(JP_FONT_URL)
            if not bool(response.ok):
                return
            buffer = await response.arrayBuffer()
            data = Uint8Array.new(buffer)
            target.write_bytes(bytes(data.to_py()))

        register_font_file(target)
        _JP_FONT_READY = True
    except Exception:
        # フォント取得に失敗しても描画処理は継続する
        return


def set_status(message: str, is_error: bool = False, detail: str = "") -> None:
    status = document.getElementById("status")
    if status is not None:
        status.textContent = message or ""
        status.style.color = "var(--status-error)" if is_error else "var(--status-ok)"

    detail_wrap = document.getElementById("statusDetailWrap")
    detail_area = document.getElementById("statusDetail")
    if detail_wrap is None or detail_area is None:
        return

    detail_text = str(detail or "").strip()
    if detail_text:
        detail_area.textContent = detail_text
        detail_wrap.classList.remove("hidden")
        detail_wrap.open = True
    else:
        detail_area.textContent = ""
        detail_wrap.classList.add("hidden")
        detail_wrap.open = False


def _format_internal_error_detail(exc: Exception, context: str) -> str:
    lines = [
        f"context: {context}",
        f"type: {type(exc).__name__}",
        f"message: {exc}",
    ]
    trace = traceback.format_exc().strip()
    if trace and trace != "NoneType: None":
        lines.append("")
        lines.append("traceback:")
        lines.append(trace)
    return "\n".join(lines)


def _safe_close_figure(fig) -> None:
    if fig is not None:
        plt.close(fig)


def _switch_tab(tab_name: str) -> None:
    plot_btn = document.getElementById("tabPlotBtn")
    data_btn = document.getElementById("tabDataBtn")
    code_btn = document.getElementById("tabCodeBtn")
    plot_panel = document.getElementById("plotPanel")
    data_panel = document.getElementById("dataPanel")
    code_panel = document.getElementById("codePanel")

    selected = tab_name if tab_name in {"plot", "data", "code"} else "plot"
    tab_items = [
        ("plot", plot_btn, plot_panel),
        ("data", data_btn, data_panel),
        ("code", code_btn, code_panel),
    ]
    for name, btn, panel in tab_items:
        if btn is not None:
            if name == selected:
                btn.classList.add("active")
            else:
                btn.classList.remove("active")
        if panel is not None:
            if name == selected:
                panel.classList.remove("hidden")
            else:
                panel.classList.add("hidden")


def _spawn_task(coro) -> None:
    task = asyncio.create_task(coro)

    def _consume_done(finished_task):
        try:
            finished_task.result()
        except Exception as exc:
            detail = _format_internal_error_detail(exc, "async task callback")
            set_status("内部エラーが発生しました。もう一度操作してください。", True, detail)

    task.add_done_callback(_consume_done)


def _set_data_ready(ready: bool) -> None:
    try:
        if hasattr(window, "setMatplotDataReady"):
            window.setMatplotDataReady(bool(ready))
    except Exception:
        pass


def _init_custom_code_editor() -> None:
    editor = document.getElementById("customPyCode")
    if editor is None:
        return
    default_code = DEFAULT_CUSTOM_PLOT_CODE.strip() + "\n"
    editor.dataset.defaultCode = default_code
    current = str(editor.value or "").strip()
    if not current:
        editor.value = default_code


def _is_custom_code_enabled() -> bool:
    element = document.getElementById("useCustomCode")
    return bool(element.checked) if element is not None else False


def _get_custom_code_text() -> str:
    element = document.getElementById("customPyCode")
    if element is None:
        return ""
    return str(element.value or "")


def _get_text_value(element_id: str, fallback: str = "") -> str:
    element = document.getElementById(element_id)
    if element is None:
        return fallback
    return str(element.value or "").strip()


def _get_optional_float_value(element_id: str, label: str) -> float | None:
    element = document.getElementById(element_id)
    raw = element.value.strip() if element is not None else ""
    if not raw:
        return None
    try:
        return float(raw)
    except Exception:
        raise ValueError(f"{label}は数値で指定してください。")


def _get_subplot_margin_settings() -> dict:
    left = _get_optional_float_value("subplotLeft", "余白 左(left)")
    right = _get_optional_float_value("subplotRight", "余白 右(right)")
    bottom = _get_optional_float_value("subplotBottom", "余白 下(bottom)")
    top = _get_optional_float_value("subplotTop", "余白 上(top)")

    for value, label in (
        (left, "余白 左(left)"),
        (right, "余白 右(right)"),
        (bottom, "余白 下(bottom)"),
        (top, "余白 上(top)"),
    ):
        if value is not None and (value < 0 or value > 1):
            raise ValueError(f"{label}は0〜1で指定してください。")

    if left is not None and right is not None and left >= right:
        raise ValueError("余白は left < right になるように指定してください。")
    if bottom is not None and top is not None and bottom >= top:
        raise ValueError("余白は bottom < top になるように指定してください。")

    return {
        "left": left,
        "right": right,
        "bottom": bottom,
        "top": top,
    }


def _apply_subplot_margin_settings(fig, margins: dict, use_tight_layout_if_auto: bool = False) -> None:
    provided = {
        key: value
        for key, value in (margins or {}).items()
        if value is not None
    }
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
            raise ValueError(f"余白設定の適用に失敗しました: {exc}")
    elif use_tight_layout_if_auto:
        fig.tight_layout()


def _apply_axis_scale_and_limits(
    target_ax,
    axis_kind: str,
    axis_label: str,
    scale: str,
    min_value: float | None,
    max_value: float | None,
) -> None:
    if scale not in {"linear", "log"}:
        raise ValueError(f"{axis_label}軸スケールが不正です。")
    if min_value is not None and max_value is not None and min_value >= max_value:
        raise ValueError(f"{axis_label}軸の範囲は最小値 < 最大値で指定してください。")
    if scale == "log":
        if (min_value is not None and min_value <= 0) or (max_value is not None and max_value <= 0):
            raise ValueError(f"{axis_label}軸を対数にする場合、範囲は0より大きい値で指定してください。")

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
            raise ValueError(f"軸種別が不正です: {axis_kind}")
    except Exception as exc:
        raise ValueError(f"{axis_label}軸設定の適用に失敗しました: {exc}")


def _get_skip_rows_for_preview() -> int:
    raw = document.getElementById("skipRows").value.strip()
    if not raw:
        return 0
    try:
        skip_rows = int(raw)
    except Exception:
        return 0
    return max(skip_rows, 0)


def _get_skip_rows() -> int:
    raw = document.getElementById("skipRows").value.strip()
    if not raw:
        return 0
    skip_rows = int(raw)
    if skip_rows < 0:
        raise ValueError("スキップ行数は0以上で指定してください。")
    return skip_rows


def _resolve_column(df: pd.DataFrame, requested: str):
    if requested.startswith("__idx__"):
        idx_text = requested.replace("__idx__", "", 1)
        if not idx_text.isdigit():
            raise ValueError(f"列指定が不正です: {requested}")
        idx = int(idx_text)
        if idx < 0 or idx >= len(df.columns):
            raise ValueError(f"列インデックスが範囲外です: {idx}")
        return df.columns[idx]

    if requested in df.columns:
        return requested
    matched = [col for col in df.columns if str(col) == requested]
    if len(matched) == 1:
        return matched[0]
    raise ValueError(f"列が見つかりません: {requested}")


def _parse_column_index(requested: str) -> int | None:
    if not requested.startswith("__idx__"):
        return None
    idx_text = requested.replace("__idx__", "", 1)
    if not idx_text.isdigit():
        return None
    return int(idx_text)


def _get_series_from_request(df: pd.DataFrame, requested: str) -> tuple[pd.Series, str, int]:
    idx = _parse_column_index(requested)
    if idx is not None:
        if idx < 0 or idx >= len(df.columns):
            raise ValueError(f"列インデックスが範囲外です: {idx}")
        return df.iloc[:, idx], str(df.columns[idx]), idx

    resolved = _resolve_column(df, requested)
    found_idx = -1
    for i, col in enumerate(df.columns):
        if col == resolved:
            found_idx = i
            break
    return df[resolved], str(resolved), found_idx


async def _read_upload() -> tuple[bytes, str]:
    file_input = document.getElementById("fileInput")
    if file_input.files.length == 0:
        raise ValueError("ファイルを選択してください。")

    js_file = file_input.files.item(0)
    buffer = await js_file.arrayBuffer()
    data = Uint8Array.new(buffer)
    return bytes(data.to_py()), str(js_file.name)


def _collect_series_settings() -> list[dict]:
    series_list = document.getElementById("seriesList")
    if series_list is None:
        raise ValueError("系列設定UIが見つかりません。")

    rows = series_list.querySelectorAll(".series-item")
    if rows.length == 0:
        raise ValueError("描画系列を1つ以上追加してください。")

    allowed_line_styles = {"solid", "dashed", "dashdot", "dotted"}
    plot_type = document.getElementById("plotType").value
    default_marker = "0" if plot_type == "line" else "24"
    settings = []
    for i in range(rows.length):
        row = rows.item(i)
        y_select = row.querySelector(".series-y")
        x_select = row.querySelector(".series-x")
        color_input = row.querySelector(".series-color")
        line_width_input = row.querySelector(".series-line-width")
        line_style_select = row.querySelector(".series-line-style")
        marker_size_input = row.querySelector(".series-marker-size")
        legend_name_input = row.querySelector(".series-legend-name")
        use_y2_input = row.querySelector(".series-use-y2")

        y_request = y_select.value.strip() if y_select is not None else ""
        x_request = x_select.value.strip() if x_select is not None else ""
        color = color_input.value.strip() if color_input is not None else "#FF4B00"
        line_width_text = line_width_input.value.strip() if line_width_input is not None else "2.0"
        line_style = line_style_select.value.strip() if line_style_select is not None else "solid"
        marker_size_text = marker_size_input.value.strip() if marker_size_input is not None else default_marker
        legend_name = legend_name_input.value.strip() if legend_name_input is not None else ""
        use_secondary_axis = bool(use_y2_input.checked) if use_y2_input is not None else False

        line_width = float(line_width_text or "2.0")
        marker_size = float(marker_size_text or default_marker)

        if plot_type == "scatter" and marker_size <= 0:
            marker_size = 24.0

        if line_width <= 0:
            raise ValueError(f"{i + 1}番目の系列: 線幅は0より大きくしてください。")
        if marker_size < 0:
            raise ValueError(f"{i + 1}番目の系列: 点サイズは0以上で指定してください。")
        if line_style not in allowed_line_styles:
            raise ValueError(f"{i + 1}番目の系列: 線種が不正です。")

        settings.append(
            {
                "y_request": y_request,
                "x_request": x_request,
                "color": color or "#FF4B00",
                "line_width": line_width,
                "line_style": line_style,
                "marker_size": marker_size,
                "legend_name": legend_name,
                "use_secondary_axis": use_secondary_axis,
            }
        )

    return settings


def _resolve_series_requests(df: pd.DataFrame, settings: list[dict]) -> list[str]:
    numeric_indices = [i for i, dtype in enumerate(df.dtypes) if pd.api.types.is_numeric_dtype(dtype)]
    candidates = numeric_indices if numeric_indices else [0]
    used_indices = set()
    resolved = []

    for setting in settings:
        request = setting["y_request"]
        if request:
            idx = _parse_column_index(request)
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


def _get_plot_data(df: pd.DataFrame, series_settings: list[dict]) -> tuple[pd.Series, str, list[dict]]:
    x_req = document.getElementById("xColumn").value.strip()
    y_requests = _resolve_series_requests(df, series_settings)

    if x_req:
        x, x_label, _ = _get_series_from_request(df, x_req)
    else:
        x = pd.Series(df.index, name="index")
        x_label = "index"

    plot_df = pd.DataFrame({"x": x})
    series_entries = []
    for i, (setting, request) in enumerate(zip(series_settings, y_requests)):
        y_series, y_name, y_idx = _get_series_from_request(df, request)
        y_key = f"y_{i}"
        label_suffix = f" [{y_idx}]" if y_idx >= 0 else ""
        data_label = f"{y_name}{label_suffix}"
        plot_df[y_key] = pd.to_numeric(y_series, errors="coerce")
        entry = dict(setting)
        entry["y_key"] = y_key
        entry["data_label"] = data_label
        entry["legend_label"] = setting.get("legend_name") or data_label
        series_entries.append(entry)

    y_keys = [entry["y_key"] for entry in series_entries]
    plot_df = plot_df.dropna(subset=y_keys, how="all")
    if plot_df.empty:
        raise ValueError("描画可能な数値データがありません。")

    for entry in series_entries:
        entry["y_series"] = plot_df[entry["y_key"]]

    return plot_df["x"], x_label, series_entries


def _get_per_series_xy_data(df: pd.DataFrame, series_settings: list[dict]) -> tuple[list[dict], str]:
    y_requests = _resolve_series_requests(df, series_settings)
    entries = []
    x_labels = []

    for setting, y_request in zip(series_settings, y_requests):
        x_request = setting.get("x_request", "").strip()
        if x_request:
            x_series, x_label, _ = _get_series_from_request(df, x_request)
        else:
            x_series = pd.Series(df.index, name="index")
            x_label = "index"

        y_series, y_name, y_idx = _get_series_from_request(df, y_request)
        label_suffix = f" [{y_idx}]" if y_idx >= 0 else ""
        data_label = f"{y_name}{label_suffix}"

        entry = dict(setting)
        entry["x_series"] = x_series.reset_index(drop=True)
        entry["y_series"] = pd.to_numeric(y_series, errors="coerce").reset_index(drop=True)
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
        raise ValueError("描画可能な数値データがありません。")

    common_x_label = x_labels[0] if len(set(x_labels)) == 1 else "x"
    return entries, common_x_label


def _fill_columns(df: pd.DataFrame) -> None:
    x_select = document.getElementById("xColumn")

    x_select.innerHTML = ""

    x_default = document.createElement("option")
    x_default.value = ""
    x_default.textContent = "(index)"
    x_select.appendChild(x_default)

    for idx, col in enumerate(df.columns):
        text = str(col)
        value = f"__idx__{idx}"
        label = f"{text} [{idx}]"

        x_opt = document.createElement("option")
        x_opt.value = value
        x_opt.textContent = label
        x_select.appendChild(x_opt)

    if hasattr(window, "refreshSeriesColumnOptions"):
        window.refreshSeriesColumnOptions()


def _render_data_preview(df: pd.DataFrame, skip_rows: int = 0) -> None:
    data_area = document.getElementById("dataArea")
    if data_area is None:
        return

    preview_df = df.head(PREVIEW_ROWS)
    rows = len(df)
    cols = len(df.columns)
    truncated = "（先頭100行のみ表示）" if rows > PREVIEW_ROWS else ""
    table_html = preview_df.to_html(index=False, border=0, classes=["data-table"])

    data_area.innerHTML = (
        f'<div class="data-meta">行数: {rows} / 列数: {cols} {truncated}</div>'
        f'<div class="table-wrap">{table_html}</div>'
    )


def _render_plot_image(fig) -> None:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=100)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    plot_area = document.getElementById("plotArea")
    plot_area.innerHTML = f'<img alt="plot" src="data:image/png;base64,{encoded}" />'


def on_tab_plot(event=None):
    _switch_tab("plot")


def on_tab_data(event=None):
    _switch_tab("data")


def on_tab_code(event=None):
    _switch_tab("code")


def _figure_has_visible_artists(fig) -> bool:
    if fig is None or not hasattr(fig, "axes"):
        return False
    for axis in fig.axes:
        if len(axis.lines) > 0:
            return True
        if len(axis.collections) > 0:
            return True
        if len(axis.patches) > 0:
            return True
        if len(axis.images) > 0:
            return True
        if hasattr(axis, "containers") and len(axis.containers) > 0:
            return True
    return False


def _collect_custom_plot_settings(skip_rows: int) -> dict:
    font_size = float(_get_text_value("fontSize", "15") or "15")
    fig_width = float(_get_text_value("figWidth", "8") or "8")
    fig_height = float(_get_text_value("figHeight", "6") or "6")
    subplot_margins = _get_subplot_margin_settings()
    if fig_width <= 0 or fig_height <= 0:
        raise ValueError("図幅・図高さは0より大きくしてください。")
    if font_size <= 0:
        raise ValueError("フォントサイズは0より大きくしてください。")

    series_settings = []
    series_settings_error = ""
    try:
        series_settings = _collect_series_settings()
    except Exception as exc:
        series_settings_error = str(exc)

    return {
        "skip_rows": skip_rows,
        "plot_type": _get_text_value("plotType", "line") or "line",
        "title": _get_text_value("title", ""),
        "x_label": _get_text_value("xLabel", ""),
        "y_label": _get_text_value("yLabel", ""),
        "y2_label": _get_text_value("y2Label", ""),
        "x_scale": _get_text_value("xScale", "linear") or "linear",
        "y_scale": _get_text_value("yScale", "linear") or "linear",
        "y2_scale": _get_text_value("y2Scale", "linear") or "linear",
        "x_min": _get_optional_float_value("xMin", "X最小値"),
        "x_max": _get_optional_float_value("xMax", "X最大値"),
        "y_min": _get_optional_float_value("yMin", "Y最小値"),
        "y_max": _get_optional_float_value("yMax", "Y最大値"),
        "y2_min": _get_optional_float_value("y2Min", "第2Y最小値"),
        "y2_max": _get_optional_float_value("y2Max", "第2Y最大値"),
        "show_major_grid": bool(document.getElementById("showMajorGrid").checked),
        "show_minor_grid": bool(document.getElementById("showMinorGrid").checked),
        "legend_location": _get_text_value("legendLocation", "best") or "best",
        "font_size": font_size,
        "fig_width": fig_width,
        "fig_height": fig_height,
        "subplot_margins": subplot_margins,
        "subplot_left": subplot_margins["left"],
        "subplot_right": subplot_margins["right"],
        "subplot_bottom": subplot_margins["bottom"],
        "subplot_top": subplot_margins["top"],
        "x_column_request": _get_text_value("xColumn", ""),
        "series_settings": series_settings,
        "series_settings_error": series_settings_error,
    }


def _create_plot_figure_with_custom_code() -> tuple[object, int, int]:
    if CURRENT_DF is None:
        raise ValueError("先にファイルを読み込んでください。")

    skip_rows = _get_skip_rows()
    if skip_rows >= len(CURRENT_DF):
        raise ValueError("スキップ行数がデータ行数以上です。")

    code = _get_custom_code_text()
    if not code.strip():
        raise ValueError("カスタムコードが空です。")

    df = CURRENT_DF.iloc[skip_rows:].reset_index(drop=True)
    settings = _collect_custom_plot_settings(skip_rows)
    context = {
        "df": df,
        "current_df": CURRENT_DF,
        "settings": settings,
        "series_settings": settings.get("series_settings", []),
        "helpers": {
            "get_plot_data": _get_plot_data,
            "get_per_series_xy_data": _get_per_series_xy_data,
            "resolve_series_requests": _resolve_series_requests,
        },
    }

    local_scope = {
        "df": df.copy(),
        "current_df": CURRENT_DF.copy(),
        "settings": settings,
        "ctx": context,
        "series_settings": settings.get("series_settings", []),
        "get_plot_data": _get_plot_data,
        "get_per_series_xy_data": _get_per_series_xy_data,
        "resolve_series_requests": _resolve_series_requests,
        "plt": plt,
        "pd": pd,
        "fig": None,
        "plotted_count": None,
        "skip_rows": skip_rows,
    }
    global_scope = {
        "__builtins__": __builtins__,
        "plt": plt,
        "pd": pd,
    }
    try:
        exec(code, global_scope, local_scope)
    except Exception as exc:
        raise ValueError(f"カスタムコードの実行に失敗しました: {exc}") from exc

    fig = local_scope.get("fig")
    if fig is None:
        raise ValueError("カスタムコードで fig を生成してください。")
    if not hasattr(fig, "savefig"):
        raise ValueError("fig には matplotlib.figure.Figure を設定してください。")
    _apply_gui_overrides_to_custom_figure(fig, settings)
    _apply_subplot_margin_settings(fig, settings.get("subplot_margins", {}), use_tight_layout_if_auto=True)

    plotted_count_raw = local_scope.get("plotted_count")
    if plotted_count_raw is None:
        plotted_count = 1 if _figure_has_visible_artists(fig) else 0
    else:
        try:
            plotted_count = int(plotted_count_raw)
        except Exception:
            raise ValueError("plotted_count は整数で指定してください。")

    if plotted_count <= 0 and _figure_has_visible_artists(fig):
        plotted_count = 1
    if plotted_count <= 0:
        raise ValueError("描画可能なデータがありません。")

    custom_skip_rows = local_scope.get("skip_rows", skip_rows)
    try:
        custom_skip_rows = int(custom_skip_rows)
    except Exception:
        custom_skip_rows = skip_rows
    if custom_skip_rows < 0:
        custom_skip_rows = skip_rows

    return fig, plotted_count, custom_skip_rows


def _apply_gui_overrides_to_custom_figure(fig, settings: dict) -> None:
    if fig is None or not hasattr(fig, "axes") or len(fig.axes) == 0:
        return

    ax = fig.axes[0]
    ax2 = fig.axes[1] if len(fig.axes) >= 2 else None
    font_size = float(settings.get("font_size", 15) or 15)
    x_label_override = str(settings.get("x_label", "") or "").strip()
    y_label_override = str(settings.get("y_label", "") or "").strip()
    y2_label_override = str(settings.get("y2_label", "") or "").strip()
    title = str(settings.get("title", "") or "").strip()
    x_scale = str(settings.get("x_scale", "linear") or "linear").strip()
    y_scale = str(settings.get("y_scale", "linear") or "linear").strip()
    y2_scale = str(settings.get("y2_scale", "linear") or "linear").strip()
    x_min = settings.get("x_min")
    x_max = settings.get("x_max")
    y_min = settings.get("y_min")
    y_max = settings.get("y_max")
    y2_min = settings.get("y2_min")
    y2_max = settings.get("y2_max")
    show_major_grid = bool(settings.get("show_major_grid", False))
    show_minor_grid = bool(settings.get("show_minor_grid", False))
    legend_location = str(settings.get("legend_location", "best") or "best").strip()
    allowed_legend_locations = {
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
    }
    if legend_location not in allowed_legend_locations:
        raise ValueError("凡例位置が不正です。")

    if title:
        ax.set_title(title, fontsize=font_size + 2)

    current_x_label = ax.get_xlabel()
    current_y_label = ax.get_ylabel()
    ax.set_xlabel(x_label_override or current_x_label, fontsize=font_size)
    ax.set_ylabel(y_label_override or current_y_label, fontsize=font_size)
    if ax2 is not None:
        current_y2_label = ax2.get_ylabel()
        ax2.set_ylabel(y2_label_override or current_y2_label, fontsize=font_size)

    _apply_axis_scale_and_limits(ax, "x", "X", x_scale, x_min, x_max)
    _apply_axis_scale_and_limits(ax, "y", "Y", y_scale, y_min, y_max)
    if ax2 is not None:
        _apply_axis_scale_and_limits(ax2, "y", "第2Y", y2_scale, y2_min, y2_max)

    ax.tick_params(
        axis="x",
        which="both",
        direction="in",
        bottom=True,
        top=False,
        labelsize=max(font_size - 1, 1),
    )
    ax.tick_params(
        axis="y",
        which="both",
        direction="in",
        left=True,
        right=False,
        labelsize=max(font_size - 1, 1),
    )
    if ax2 is not None:
        ax2.tick_params(
            axis="y",
            which="both",
            direction="in",
            left=False,
            right=True,
            labelsize=max(font_size - 1, 1),
        )

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

    for axis in fig.axes:
        existing_legend = axis.get_legend()
        if existing_legend is not None:
            existing_legend.remove()

    if legend_location == "none":
        return

    handles = []
    labels = []
    for axis in fig.axes:
        h, l = axis.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(l)

    if not labels:
        return

    series_settings = settings.get("series_settings", [])
    for i, setting in enumerate(series_settings):
        if i >= len(labels):
            break
        legend_name = str(setting.get("legend_name", "") or "").strip()
        if legend_name:
            labels[i] = legend_name

    ax.legend(
        handles,
        labels,
        loc=legend_location,
        fontsize=max(font_size - 1, 1),
        edgecolor="black",
    )


async def on_load_columns(event=None):
    global CURRENT_DF
    try:
        _set_data_ready(False)
        file_bytes, filename = await _read_upload()
        delimiter = document.getElementById("delimiter").value
        has_header = document.getElementById("hasHeader").checked

        df = load_dataframe(file_bytes, filename, delimiter, has_header)
        CURRENT_DF = df
        _fill_columns(df)
        _render_data_preview(df, _get_skip_rows_for_preview())
        _set_data_ready(True)
        set_status("")
        await on_render()
    except Exception as exc:
        CURRENT_DF = None
        _set_data_ready(False)
        set_status(str(exc), True)


def _create_plot_figure() -> tuple[object, int, int]:
    if _is_custom_code_enabled():
        return _create_plot_figure_with_custom_code()

    if CURRENT_DF is None:
        raise ValueError("先にファイルを読み込んでください。")

    skip_rows = _get_skip_rows()
    if skip_rows >= len(CURRENT_DF):
        raise ValueError("スキップ行数がデータ行数以上です。")

    df = CURRENT_DF.iloc[skip_rows:].reset_index(drop=True)
    plot_type = document.getElementById("plotType").value

    title = document.getElementById("title").value.strip()
    x_label_override = document.getElementById("xLabel").value.strip()
    y_label_override = document.getElementById("yLabel").value.strip()
    y2_label_override = document.getElementById("y2Label").value.strip()
    x_scale = (document.getElementById("xScale").value or "linear").strip()
    y_scale = (document.getElementById("yScale").value or "linear").strip()
    y2_scale = (document.getElementById("y2Scale").value or "linear").strip()
    x_min = _get_optional_float_value("xMin", "X最小値")
    x_max = _get_optional_float_value("xMax", "X最大値")
    y_min = _get_optional_float_value("yMin", "Y最小値")
    y_max = _get_optional_float_value("yMax", "Y最大値")
    y2_min = _get_optional_float_value("y2Min", "第2Y最小値")
    y2_max = _get_optional_float_value("y2Max", "第2Y最大値")
    show_major_grid = bool(document.getElementById("showMajorGrid").checked)
    show_minor_grid = bool(document.getElementById("showMinorGrid").checked)
    legend_location = document.getElementById("legendLocation").value

    series_settings = _collect_series_settings()
    font_size = float(document.getElementById("fontSize").value or "15")
    fig_width = float(document.getElementById("figWidth").value or "8")
    fig_height = float(document.getElementById("figHeight").value or "6")
    subplot_margins = _get_subplot_margin_settings()
    allowed_legend_locations = {
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
    }

    if fig_width <= 0 or fig_height <= 0:
        raise ValueError("図幅・図高さは0より大きくしてください。")
    if font_size <= 0:
        raise ValueError("フォントサイズは0より大きくしてください。")
    if plot_type not in {"line", "scatter", "bar"}:
        raise ValueError("プロット種別が不正です。")
    if legend_location not in allowed_legend_locations:
        raise ValueError("凡例位置が不正です。")

    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=100)
    ax2 = None
    plotted_labels = []
    all_entries = []

    if plot_type in {"line", "scatter"}:
        per_series_entries, x_label = _get_per_series_xy_data(df, series_settings)
        all_entries = per_series_entries
        for entry in per_series_entries:
            x_series = entry["x_series"]
            y_series = entry["y_series"]
            mask = y_series.notna() & pd.notna(x_series)
            if not bool(mask.any()):
                continue

            target_ax = ax
            if entry.get("use_secondary_axis", False):
                if ax2 is None:
                    ax2 = ax.twinx()
                target_ax = ax2

            if plot_type == "line":
                marker = "o" if entry["marker_size"] > 0 else ""
                marker_size_for_line = entry["marker_size"] ** 0.5 if entry["marker_size"] > 0 else 0
                target_ax.plot(
                    x_series[mask],
                    y_series[mask],
                    color=entry["color"],
                    linewidth=entry["line_width"],
                    linestyle=entry["line_style"],
                    marker=marker,
                    markersize=marker_size_for_line,
                    label=entry["legend_label"],
                )
            else:
                target_ax.scatter(
                    x_series[mask],
                    y_series[mask],
                    color=entry["color"],
                    s=entry["marker_size"],
                    label=entry["legend_label"],
                )
            plotted_labels.append(entry["legend_label"])
    else:
        x, x_label, series_entries = _get_plot_data(df, series_settings)
        all_entries = series_entries
        if len(series_entries) == 1:
            entry = series_entries[0]
            y_series = entry["y_series"]
            mask = y_series.notna() & pd.notna(x)
            if bool(mask.any()):
                target_ax = ax
                if entry.get("use_secondary_axis", False):
                    if ax2 is None:
                        ax2 = ax.twinx()
                    target_ax = ax2
                target_ax.bar(
                    x[mask],
                    y_series[mask],
                    color=entry["color"],
                    linewidth=entry["line_width"],
                    linestyle=entry["line_style"],
                    label=entry["legend_label"],
                )
                plotted_labels.append(entry["legend_label"])
        else:
            x_labels = [str(v) for v in x.tolist()]
            positions = list(range(len(x_labels)))
            width = 0.8 / len(series_entries)

            for i, entry in enumerate(series_entries):
                y_series = entry["y_series"]
                y_values = [float(v) if pd.notna(v) else 0.0 for v in y_series.tolist()]
                offset = -0.4 + (width / 2.0) + (i * width)
                x_positions = [p + offset for p in positions]

                target_ax = ax
                if entry.get("use_secondary_axis", False):
                    if ax2 is None:
                        ax2 = ax.twinx()
                    target_ax = ax2
                target_ax.bar(
                    x_positions,
                    y_values,
                    width=width,
                    color=entry["color"],
                    linewidth=entry["line_width"],
                    linestyle=entry["line_style"],
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
        raise ValueError("描画可能なデータがありません。")

    primary_labels = [entry["data_label"] for entry in all_entries if not entry.get("use_secondary_axis", False)]
    secondary_labels = [entry["data_label"] for entry in all_entries if entry.get("use_secondary_axis", False)]

    if title:
        ax.set_title(title, fontsize=font_size + 2)
    ax.set_xlabel(x_label_override or x_label, fontsize=font_size)

    if y_label_override:
        ax.set_ylabel(y_label_override, fontsize=font_size)
    else:
        left_default = primary_labels[0] if len(primary_labels) == 1 else "values"
        ax.set_ylabel(left_default, fontsize=font_size)

    if ax2 is not None:
        right_default = secondary_labels[0] if len(secondary_labels) == 1 else "values"
        ax2.set_ylabel(y2_label_override or right_default, fontsize=font_size)

    _apply_axis_scale_and_limits(ax, "x", "X", x_scale, x_min, x_max)
    _apply_axis_scale_and_limits(ax, "y", "Y", y_scale, y_min, y_max)
    if ax2 is not None:
        _apply_axis_scale_and_limits(ax2, "y", "第2Y", y2_scale, y2_min, y2_max)

    ax.tick_params(
        axis="x",
        which="both",
        direction="in",
        bottom=True,
        top=False,
        labelsize=max(font_size - 1, 1),
    )
    ax.tick_params(
        axis="y",
        which="both",
        direction="in",
        left=True,
        right=False,
        labelsize=max(font_size - 1, 1),
    )
    if ax2 is not None:
        ax2.tick_params(
            axis="y",
            which="both",
            direction="in",
            left=False,
            right=True,
            labelsize=max(font_size - 1, 1),
        )

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

    if legend_location != "none" and len(plotted_labels) >= 1:
        if ax2 is None:
            ax.legend(
                loc=legend_location,
                fontsize=max(font_size - 1, 1),
                edgecolor="black",
            )
        else:
            handles1, labels1 = ax.get_legend_handles_labels()
            handles2, labels2 = ax2.get_legend_handles_labels()
            merged_handles = handles1 + handles2
            merged_labels = labels1 + labels2
            if len(merged_labels) >= 1:
                ax.legend(
                    merged_handles,
                    merged_labels,
                    loc=legend_location,
                    fontsize=max(font_size - 1, 1),
                    edgecolor="black",
                )
    _apply_subplot_margin_settings(fig, subplot_margins, use_tight_layout_if_auto=True)
    return fig, len(plotted_labels), skip_rows


async def on_render(event=None):
    fig = None
    try:
        if CURRENT_DF is not None:
            _render_data_preview(CURRENT_DF, _get_skip_rows_for_preview())
        await _ensure_japanese_font()
        fig, plotted_count, skip_rows = _create_plot_figure()
        _render_plot_image(fig)
        _set_data_ready(True)
        set_status(f"描画に成功しました（{plotted_count}系列、スキップ{skip_rows}行）。")
    except Exception as exc:
        set_status(str(exc), True)
    finally:
        _safe_close_figure(fig)


async def on_save_plot(event=None):
    fig = None
    try:
        await _ensure_japanese_font()
        save_format = document.getElementById("saveFormat").value.strip().lower()
        transparent = bool(document.getElementById("saveTransparent").checked)
        raw_filename = document.getElementById("saveFilename").value.strip()
        fig, plotted_count, skip_rows = _create_plot_figure()
        data_uri, ext = figure_to_data_uri(fig, save_format, transparent=transparent)
        filename = build_filename(raw_filename, ext)
        if not hasattr(window, "downloadDataUri"):
            raise ValueError("ダウンロード機能の初期化に失敗しました。")
        window.downloadDataUri(filename, data_uri)
        set_status(f"描画データを保存しました: {filename}")
    except Exception as exc:
        set_status(str(exc), True)
    finally:
        _safe_close_figure(fig)


def _bind_click(element_id: str, handler, is_async: bool = False) -> None:
    element = document.getElementById(element_id)
    if element is None:
        raise ValueError(f"UI要素が見つかりません: {element_id}")

    if is_async:
        def wrapped(event):
            _spawn_task(handler(event))
    else:
        def wrapped(event):
            handler(event)

    proxy = create_proxy(wrapped)
    _EVENT_PROXIES.append(proxy)
    element.addEventListener("click", proxy)


def _bind_events() -> None:
    _bind_click("tabPlotBtn", on_tab_plot)
    _bind_click("tabDataBtn", on_tab_data)
    _bind_click("tabCodeBtn", on_tab_code)
    _bind_click("savePlotBtn", on_save_plot, is_async=True)


def _register_js_api() -> None:
    def trigger_load(event=None):
        _spawn_task(on_load_columns())

    def trigger_render(event=None):
        _spawn_task(on_render())

    load_proxy = create_proxy(trigger_load)
    render_proxy = create_proxy(trigger_render)
    _EVENT_PROXIES.append(load_proxy)
    _EVENT_PROXIES.append(render_proxy)
    window.requestLoadColumns = load_proxy
    window.requestRender = render_proxy


set_status("")
_set_data_ready(False)
_init_custom_code_editor()
_switch_tab("plot")
if hasattr(window, "ensureSeriesItems"):
    window.ensureSeriesItems()
_register_js_api()
_bind_events()
