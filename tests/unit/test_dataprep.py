from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mplgui.dataprep import (
    NO_DRAWABLE_DATA,
    coerce_numeric,
    plan_plot,
    resolve_column_index,
    resolve_y_indices,
)
from mplgui.errors import UserError
from mplgui.loader import load_file
from mplgui.settings import default_settings, parse_settings

pytestmark = pytest.mark.unit


@pytest.fixture
def df():
    t = np.arange(20, dtype=float)
    return pd.DataFrame({"t": t, "a": np.sin(t), "b": t * 2.0, "name": [f"n{i}" for i in range(20)]})


def settings_with(mutator=None, series=None):
    raw = default_settings()
    if series is not None:
        raw["series"] = series
    if mutator:
        mutator(raw)
    return parse_settings(raw)


def plan(df, mutator=None, series=None):
    return plan_plot(df, settings_with(mutator, series))


def _csv_df(name="non_numeric.csv"):
    path = Path(__file__).resolve().parents[1] / "fixtures" / name
    return load_file(path.read_bytes(), name, "", True).df


# ---------------------------------------------------------------- plan content


def test_plan_line_defaults(df):
    p = plan(df, series=[{"x": "__idx__0", "y": "__idx__1"}])
    s = p.series[0]
    assert (s.y_index, s.x_index, s.x_label, s.data_label, s.legend_label) == (1, 0, "t", "a [1]", "a [1]")
    assert s.has_points and not s.convert_x and not s.categorical_x and s.marker_size == 0.0
    assert (p.x_label, p.y_label, p.y2_label, p.plotted_count, p.uses_secondary) == ("t", "a [1]", None, 1, False)


def test_plan_x_index_and_custom_legend(df):
    p = plan(df, series=[{"y": "__idx__1", "label": "電圧"}])
    s = p.series[0]
    assert s.x_index is None and s.x_label == "index" and p.x_label == "index" and s.legend_label == "電圧"


def test_plan_common_x_label_falls_back_to_x(df):
    p = plan(df, series=[{"x": "__idx__0", "y": "__idx__1"}, {"x": "__idx__2", "y": "__idx__2"}])
    assert p.x_label == "x"


def test_plan_labels_multiple_series_are_values(df):
    p = plan(df, series=[{"y": "__idx__1"}, {"y": "__idx__2"}, {"y": "__idx__2", "secondaryAxis": True}, {"y": "__idx__1", "secondaryAxis": True}])
    assert p.y_label == "values" and p.y2_label == "values" and p.uses_secondary


def test_plan_secondary_label_single(df):
    p = plan(df, series=[{"y": "__idx__1"}, {"y": "__idx__2", "secondaryAxis": True}])
    assert p.y_label == "a [1]" and p.y2_label == "b [2]"


def test_plan_marker_sizes(df):
    def kind(t):
        return lambda s: s["plot"].__setitem__("type", t)

    assert plan(df, kind("line"), [{"y": "__idx__1"}]).series[0].marker_size == 0.0
    assert plan(df, kind("scatter"), [{"y": "__idx__1"}]).series[0].marker_size == 24.0
    assert plan(df, kind("scatter"), [{"y": "__idx__1", "markerSize": 0}]).series[0].marker_size == 24.0
    assert plan(df, kind("line"), [{"y": "__idx__1", "markerSize": 9}]).series[0].marker_size == 9.0


def test_plan_series_without_points_is_skipped_but_counted_for_labels():
    d = pd.DataFrame({"t": [1.0, 2.0], "bad": ["x", "y"], "ok": [1.0, 2.0]})
    p = plan(d, series=[{"x": "__idx__0", "y": "__idx__1"}, {"x": "__idx__0", "y": "__idx__2", "secondaryAxis": True}])
    assert [s.has_points for s in p.series] == [False, True]
    assert p.plotted_count == 1 and p.uses_secondary


def test_plan_secondary_without_points_creates_no_second_axis():
    d = pd.DataFrame({"t": [1.0, 2.0], "bad": ["x", "y"], "ok": [1.0, 2.0]})
    p = plan(d, series=[{"x": "__idx__0", "y": "__idx__2"}, {"x": "__idx__0", "y": "__idx__1", "secondaryAxis": True}])
    assert not p.uses_secondary and p.y2_label is None


def test_plan_x_conversion_flags():
    d = pd.DataFrame({"x": ["1", "2", "3"], "d": ["a", "b", "c"], "n": [1, 2, 3], "y": [1.0, 2.0, 3.0]})
    s = plan(d, series=[{"x": "__idx__0", "y": "__idx__3"}, {"x": "__idx__1", "y": "__idx__3"}, {"x": "__idx__2", "y": "__idx__3"}]).series
    assert (s[0].convert_x, s[0].categorical_x) == (True, False)
    assert (s[1].convert_x, s[1].categorical_x) == (False, True)
    assert (s[2].convert_x, s[2].categorical_x) == (False, False)


def test_plan_bar_single_and_multi(df):
    p = plan(df, lambda s: s["plot"].update(type="bar", xColumn="__idx__3"), [{"y": "__idx__1"}])
    assert p.bar_x_index == 3 and p.x_label == "name" and p.plotted_count == 1
    p = plan(df, lambda s: s["plot"].update(type="bar"), [{"y": "__idx__1"}, {"y": "__idx__2"}])
    assert p.bar_x_index is None and p.x_label == "index" and p.plotted_count == 2 and p.y_label == "values"


def test_skip_rows_are_applied_before_resolution():
    d = pd.DataFrame({"a": ["x", "y", "1", "2"]})
    p = plan(d, lambda s: s["plot"].__setitem__("skipRows", 2), [{"y": "__idx__0"}])
    assert p.skip_rows == 2 and p.warnings == ()


# ---------------------------------------------------------------- errors (same messages as before)


def test_skip_rows_too_large(df):
    with pytest.raises(UserError) as info:
        plan(df, lambda s: s["plot"].__setitem__("skipRows", 20))
    assert "スキップ" in info.value.message and info.value.field == "除外する先頭行数"


def test_no_plottable_data_raises():
    with pytest.raises(UserError) as info:
        plan(pd.DataFrame({"a": ["x", "y", "z"]}), series=[{"y": "__idx__0"}])
    assert info.value.message.startswith("描画可能な数値データがありません。")


def test_bar_single_without_points_raises():
    d = pd.DataFrame({"x": [None, None], "y": [1.0, 2.0]})
    with pytest.raises(UserError) as info:
        plan(d, lambda s: s["plot"].update(type="bar", xColumn="__idx__0"), [{"y": "__idx__1"}])
    assert info.value.message == NO_DRAWABLE_DATA


def test_column_out_of_range_is_user_error(df):
    with pytest.raises(UserError) as info:
        plan(df, series=[{"y": "__idx__99"}])
    assert "100列目" in info.value.message
    with pytest.raises(UserError) as info:
        plan(df, series=[{"x": "__idx__50", "y": "__idx__1"}])
    assert "51列目" in info.value.message


def test_malformed_and_unknown_column(df):
    with pytest.raises(UserError) as info:
        plan(df, series=[{"y": "__idx__x"}])
    assert info.value.message == "列の指定が正しくありません。列を選び直してください。"
    with pytest.raises(UserError) as info:
        plan(df, series=[{"y": "nonexistent"}])
    assert "「nonexistent」" in info.value.message
    assert resolve_column_index(df, "b") == 2


def test_duplicate_column_names_resolved_by_index():
    d = pd.DataFrame([[1, 10, 100], [2, 20, 200], [3, 30, 300]], columns=["温度", "温度", "値"])
    p = plan(d, series=[{"y": "__idx__0"}, {"y": "__idx__1"}])
    assert [s.y_index for s in p.series] == [0, 1] and [s.data_label for s in p.series] == ["温度 [0]", "温度 [1]"]


# ---------------------------------------------------------------- Y auto


def test_auto_y_assigns_unused_numeric_columns(df):
    p = plan(df, series=[{}, {}])
    assert [s.y_index for s in p.series] == [0, 1]


def test_resolve_y_indices(df):
    assert resolve_y_indices(df, ["", "__idx__2", ""]) == ["__idx__0", "__idx__2", "__idx__1"]
    assert resolve_y_indices(pd.DataFrame({"a": ["x"]}), ["", ""]) == ["__idx__0", "__idx__0"]


# ---------------------------------------------------------------- coerce_numeric / A7 warnings


def test_coerce_numeric_numeric_dtype_returns_immediately():
    s = pd.Series([1.0, np.nan, 3.0])
    out, count, examples = coerce_numeric(s)
    assert out is s and count == 0 and examples == []
    out, count, _ = coerce_numeric(pd.Series(["1", "x", ""]))
    assert count == 1 and out.isna().sum() == 2


def test_dropped_values_are_reported_per_series():
    d = _csv_df()
    p = plan(d, series=[
        {"x": "__idx__0", "y": "__idx__2"},   # 電圧: 数値列（空欄・N/A は欠損値でありカウントしない）
        {"x": "__idx__0", "y": "__idx__1"},   # 金額: "1,234" 形式 → 全件変換不可
        {"x": "__idx__0", "y": "__idx__3"},   # 単位付き: "1 mV"
    ])
    assert p.plotted_count == 1
    msgs = {w["series"]: w["message"] for w in p.warnings}
    assert set(msgs) == {2, 3}
    assert msgs[2].startswith("系列2（金額）: 数値に変換できない値が20件あったため、その行を除外しました（例: ")
    assert '"1,234"' in msgs[2] and '"2,468"' in msgs[2] and '"3,702"' in msgs[2] and '"4,936"' not in msgs[2]
    assert '"1 mV"' in msgs[3] and msgs[3].endswith("）。")


def test_blank_cells_are_not_counted_as_dropped():
    d = pd.DataFrame({"t": [1, 2, 3, 4], "v": ["1", "", "  ", "x"]})
    p = plan(d, series=[{"x": "__idx__0", "y": "__idx__1"}])
    assert len(p.warnings) == 1
    assert "1件" in p.warnings[0]["message"] and '"x"' in p.warnings[0]["message"] and p.warnings[0]["series"] == 1


def test_no_warning_for_clean_data(df):
    assert plan(df).warnings == ()


def test_x_column_dropped_values_are_reported():
    d = pd.DataFrame({"x": ["1", "2", "3", "oops", "5"], "y": [1.0, 2.0, 3.0, 4.0, 5.0]})
    p = plan(d, series=[{"x": "__idx__0", "y": "__idx__1"}])
    assert p.plotted_count == 1
    assert "系列1のX列（x）" in p.warnings[0]["message"] and '"oops"' in p.warnings[0]["message"]


def test_all_values_dropped_error_mentions_cause():
    d = _csv_df()
    with pytest.raises(UserError) as info:
        plan(d, series=[{"x": "__idx__0", "y": "__idx__1"}])
    assert "数値に変換できない値" in info.value.message


def test_bar_reports_dropped_values():
    d = pd.DataFrame({"x": list("abcd"), "y": ["1", "2", "bad", "4"]})
    p = plan(d, lambda s: s["plot"].update(type="bar"), [{"y": "__idx__1"}])
    assert "系列1（y）" in p.warnings[0]["message"]
