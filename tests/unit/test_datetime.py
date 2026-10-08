"""Phase 4 D5（日時の列）の単体テスト: 認識、読込部と loader の一致、描画計画、生成コード、注入対策。"""
import json
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mplgui import api, loader
from mplgui.codegen import generate_script
from mplgui.dataprep import auto_bar_date_format, plan_plot
from mplgui.errors import UserError
from mplgui.loader import DatetimeColumn, SourceInfo, build_preview, column_options, detect_datetime_columns, load_file
from mplgui.runner import figure_summary, run_script
from mplgui.settings import default_settings, parse_settings

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def csv(values, header="t", extra=None):
    """1 列（values）の CSV を読み込む。"""
    text = header + "\n" + "\n".join(values) + "\n"
    return load_file(text.encode("utf-8"), "a.csv", "", True)


def fmts(result):
    return [(c.index, c.format) for c in result.source.datetime_columns]


def hourly(fmt, n=12):
    base = datetime(2025, 12, 31, 22, 0)
    return [(base + timedelta(hours=i)).strftime(fmt) for i in range(n)]


# ---------------------------------------------------------------- recognition


@pytest.mark.parametrize(
    "fmt, value_fmt",
    [
        ("%Y-%m-%d", "%Y-%m-%d"),
        ("%Y/%m/%d", "%Y/%m/%d"),
        ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M"),
        ("%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M"),
        ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"),
        ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f"),
        ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M"),
        ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S"),
        ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"),
    ],
)
def test_each_format_family_is_recognized(fmt, value_fmt):
    r = csv(hourly(value_fmt))
    assert fmts(r) == [(0, fmt)]
    assert pd.api.types.is_datetime64_any_dtype(r.df.iloc[:, 0].dtype)
    assert r.df.iloc[0, 0] == pd.Timestamp(2025, 12, 31, 22, 0) or "%H" not in fmt


def test_japanese_dates_with_and_without_padding():
    r = csv(["2026年1月5日", "2026年1月6日", "2026年12月10日"])
    assert fmts(r) == [(0, "%Y年%m月%d日")]
    assert list(r.df.iloc[:, 0]) == [pd.Timestamp(2026, 1, 5), pd.Timestamp(2026, 1, 6), pd.Timestamp(2026, 12, 10)]


def test_japanese_date_with_time_is_recognized():
    r = csv(["2026年1月5日 09:30", "2026年1月5日 10:30"])
    assert fmts(r) == [(0, "%Y年%m月%d日 %H:%M")]


def test_iso_offsets_same_offset_keep_wall_time():
    r = csv(["2026-01-05T09:00:00+09:00", "2026-01-05T10:00:00+09:00"])
    assert fmts(r) == [(0, "%Y-%m-%dT%H:%M:%S%z")]
    spec = r.source.datetime_columns[0]
    assert spec.has_tz and not spec.utc
    assert list(r.df.iloc[:, 0]) == [pd.Timestamp(2026, 1, 5, 9), pd.Timestamp(2026, 1, 5, 10)]
    assert r.df.iloc[:, 0].dt.tz is None and r.warnings == []


def test_z_only_is_utc_wall_time():
    r = csv(["2026-01-05 09:00Z", "2026-01-05 10:00Z"])
    assert fmts(r) == [(0, "%Y-%m-%d %H:%M%z")]
    assert list(r.df.iloc[:, 0])[0] == pd.Timestamp(2026, 1, 5, 9)


def test_mixed_offsets_become_utc_with_warning():
    r = csv(["2026-01-05T09:00:00Z", "2026-01-05T09:00:00+09:00"], header="混在")
    spec = r.source.datetime_columns[0]
    assert spec.utc and spec.has_tz
    assert list(r.df.iloc[:, 0]) == [pd.Timestamp(2026, 1, 5, 9), pd.Timestamp(2026, 1, 5, 0)]
    assert r.warnings == ["列「混在」[0]: タイムゾーンの異なる日時が混在しているため、UTC の時刻にそろえました。"]


def test_z_and_plus_zero_are_the_same_offset():
    r = csv(["2026-01-05T09:00:00Z", "2026-01-05T09:00:00+00:00"])
    assert not r.source.datetime_columns[0].utc


def test_leading_and_trailing_spaces_are_stripped():
    r = csv(["  2026-01-05 ", "2026-01-06", "2026-01-07  "])
    spec = r.source.datetime_columns[0]
    assert spec.strip and r.df.iloc[0, 0] == pd.Timestamp(2026, 1, 5)
    r = csv(["2026-01-05", "2026-01-06"])
    assert not r.source.datetime_columns[0].strip


def _rows(n_good, n_bad, bad="x"):
    return hourly("%Y-%m-%d %H:%M", n_good) + [bad] * n_bad


def test_ninety_percent_threshold_boundary():
    # 先頭 100 個はすべて読めなければならないので、90% の境界は 100 個より多い列でだけ意味を持つ
    def column(n_bad, total=1000):
        good = [f"2026-01-{(i % 28) + 1:02d}" for i in range(total - n_bad)]
        return good + ["x"] * n_bad

    r = csv(column(100))  # 900 / 1000 = ちょうど 90%: 採用
    assert fmts(r) == [(0, "%Y-%m-%d")]
    assert r.warnings == ['列「t」[0]: 日時として読めない値が100件あったため、欠損として扱います（例: "x"）。']
    assert fmts(csv(column(101))) == []  # 899 / 1000: 採用しない


def test_short_columns_need_every_value_to_parse():
    good = [f"2026-01-{d:02d}" for d in range(1, 10)]
    assert fmts(csv(good)) == [(0, "%Y-%m-%d")]
    assert fmts(csv(good + ["x"])) == []  # 先頭 100 個（ここでは全部）に読めない値がある


def test_first_100_values_must_all_parse():
    good = [f"2026-01-01 {i % 24:02d}:00" for i in range(150)]
    bad_early = list(good)
    bad_early[50] = "x"  # 先頭 100 個の中に読めない値: 採用しない（全体の 99% が読めても）
    assert fmts(csv(bad_early)) == []
    bad_late = list(good)
    bad_late[120] = "x"  # 100 個より後ろ: 採用し、NaT + 警告
    r = csv(bad_late)
    assert fmts(r) == [(0, "%Y-%m-%d %H:%M")] and len(r.warnings) == 1


def test_blank_values_are_not_counted_and_not_warned():
    r = csv([f"2026-01-{d:02d}" for d in range(1, 10)] + ["", "  "])
    assert fmts(r) == [(0, "%Y-%m-%d")] and r.warnings == []


def test_warning_examples_are_capped_at_three_and_distinct():
    values = [f"2026-01-{(i % 28) + 1:02d}" for i in range(100)] + ["a", "a", "b", "c", "d"] + [f"2026-01-{(i % 28) + 1:02d}" for i in range(100)]
    r = csv(values)
    assert r.warnings == ['列「t」[0]: 日時として読めない値が5件あったため、欠損として扱います（例: "a", "b", "c"）。']


@pytest.mark.parametrize(
    "values",
    [
        ["A-001", "A-002", "A-003"],
        ["2024-001", "2024-002", "2024-003"],
        ["1.2.3", "1.2.4", "1.3.0"],
        ["v2024.1", "v2024.2", "v2024.3"],
        ["01/02/2024", "02/02/2024", "03/02/2024"],
        ["13:45", "14:45", "15:45"],
        ["2024-01", "2024-02", "2024-03"],
        ["2024", "2025", "2026"],
        ["2024/1", "2024/2", "2024/3"],
        ["1月5日", "1月6日", "1月7日"],
        ["2024-01-05 (月)", "2024-01-06 (火)", "2024-01-07 (水)"],
    ],
)
def test_non_dates_are_not_recognized(values):
    r = csv(values)
    assert r.source.datetime_columns == () and not pd.api.types.is_datetime64_any_dtype(r.df.iloc[:, 0].dtype)


def test_numeric_yyyymmdd_is_not_recognized():
    r = csv(["20240101", "20240102", "20240103"])
    assert r.source.datetime_columns == ()


def test_numeric_looking_strings_are_not_recognized():
    r = csv(['"20240101"', '"20240102"', "x"])
    assert r.source.datetime_columns == ()


def test_mixed_formats_in_one_column_are_not_recognized():
    r = csv(["2026-01-05", "2026/01/06", "2026-01-07 10:00", "2026年1月8日"] * 3)
    assert r.source.datetime_columns == ()


def test_no_date_with_non_string_cells_is_recognized():
    df = pd.DataFrame({"a": ["2026-01-05", 3.5, None, pd.Timestamp(2026, 1, 6)]}, dtype=object)
    assert detect_datetime_columns(df) == ()


def test_parse_dates_false_disables_string_recognition():
    text = "t,v\n2026-01-05,1\n2026-01-06,2\n"
    r = load_file(text.encode(), "a.csv", "", True, parse_dates=False)
    assert r.source.datetime_columns == () and not pd.api.types.is_datetime64_any_dtype(r.df.iloc[:, 0].dtype)


def test_excel_datetime_cells_are_datetime_even_without_parse_dates():
    raw = (FIXTURES / "datetime.xlsx").read_bytes()
    for flag in (True, False):
        r = load_file(raw, "datetime.xlsx", parse_dates=flag)
        assert pd.api.types.is_datetime64_any_dtype(r.df.iloc[:, 0].dtype)
        assert r.source.datetime_columns == () and r.warnings == []  # 変換の行は要らない


def test_excel_string_date_cells_go_through_recognition(tmp_path):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["日付", "値"])
    for i in range(5):
        ws.append([f"2026/01/{i + 1:02d}", i])
    path = tmp_path / "s.xlsx"
    wb.save(path)
    r = load_file(path.read_bytes(), "s.xlsx")
    assert fmts(r) == [(0, "%Y/%m/%d")] and pd.api.types.is_datetime64_any_dtype(r.df.iloc[:, 0].dtype)
    r = load_file(path.read_bytes(), "s.xlsx", parse_dates=False)
    assert r.source.datetime_columns == ()


def test_header_less_file_gets_recognition_after_rename():
    r = load_file(b"2026-01-05,1\n2026-01-06,2\n", "a.csv", "", False)
    assert list(r.df.columns) == ["column_0", "column_1"] and fmts(r) == [(0, "%Y-%m-%d")]
    assert r.source.datetime_columns[0].name == "column_0"


def test_datetime_fixture_recognition_and_warning():
    r = load_file((FIXTURES / "datetime.csv").read_bytes(), "datetime.csv")
    assert fmts(r) == [(0, "%Y/%m/%d %H:%M")]
    kinds = [o["kind"] for o in column_options(r.df)]
    assert kinds == ["datetime", "text", "number", "number", "number"]  # ID（A-001）は文字列、通番は数値
    assert build_preview(r.df)["columnKinds"] == kinds
    assert r.warnings == ['列「日時」[0]: 日時として読めない値が1件あったため、欠損として扱います（例: "測定エラー"）。']
    col = r.df.iloc[:, 0]
    assert col.iloc[0] == pd.Timestamp(2025, 12, 31, 22) and col.iloc[3] == pd.Timestamp(2026, 1, 1, 1)
    assert col.isna().sum() == 2  # 読めない値 1 件 + 空欄 1 件


def test_iso_tz_fixture():
    r = load_file((FIXTURES / "datetime_iso_tz.csv").read_bytes(), "datetime_iso_tz.csv")
    a, b = r.source.datetime_columns
    assert (a.utc, a.has_tz) == (False, True) and (b.utc, b.has_tz) == (True, True)
    assert r.df.iloc[0, 0] == pd.Timestamp(2026, 1, 5, 9)  # 書かれた時刻のまま
    assert r.df.iloc[0, 1] == pd.Timestamp(2026, 1, 5, 9) and r.df.iloc[1, 1] == pd.Timestamp(2026, 1, 5, 1)  # UTC にそろえる
    assert len(r.warnings) == 1 and "混在" in r.warnings[0]


def test_api_load_file_reports_kinds_and_warnings():
    out = json.loads(api.load_file_json("datetime.csv", (FIXTURES / "datetime.csv").read_bytes(), json.dumps(default_settings())))
    assert out["ok"] and out["columns"][0]["kind"] == "datetime" and out["preview"]["columnKinds"][0] == "datetime"
    assert any("測定エラー" in w for w in out["warnings"])
    off = default_settings()
    off["load"]["parseDates"] = False
    out = json.loads(api.load_file_json("datetime.csv", (FIXTURES / "datetime.csv").read_bytes(), json.dumps(off)))
    assert out["columns"][0]["kind"] == "text" and out["warnings"] == []


# ---------------------------------------------------------------- generated read section == loader


def exec_load(tmp_path, script):
    start, end = script.load_lines
    code = "import pandas as pd\n" + "\n".join(script.text.split("\n")[start - 1:end])
    ns = {}
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        exec(compile(code, "load.py", "exec"), ns)
    finally:
        os.chdir(cwd)
    return ns["df"]


def plan_script(loaded, mutate=None, series=None):
    raw = default_settings()
    raw["series"] = series or [{"x": "", "y": "__idx__1"}]
    if mutate:
        mutate(raw)
    settings = parse_settings(raw)
    plan = plan_plot(loaded.df, settings)
    return settings, plan, generate_script(settings, loaded.source, plan)


@pytest.mark.parametrize("name", ["datetime.csv", "datetime_iso_tz.csv", "dates_ja.csv", "datetime.xlsx"])
def test_generated_read_section_matches_loader(tmp_path, name):
    shutil.copy(FIXTURES / name, tmp_path / name)
    loaded = load_file((FIXTURES / name).read_bytes(), name)
    y = "__idx__1" if loaded.df.shape[1] > 1 else "__idx__0"
    series = [{"x": "", "y": "__idx__2" if name in {"datetime.csv", "datetime_iso_tz.csv"} else y}]
    _, _, script = plan_script(loaded, series=series)
    pd.testing.assert_frame_equal(exec_load(tmp_path, script), loaded.df)
    auto = script.auto_render_text()
    assert "to_datetime" not in auto and ("isetitem" not in auto)


def test_generated_read_section_lines_for_datetime_fixture(tmp_path):
    shutil.copy(FIXTURES / "datetime.csv", tmp_path / "datetime.csv")
    loaded = load_file((FIXTURES / "datetime.csv").read_bytes(), "datetime.csv")
    _, _, script = plan_script(loaded, series=[{"x": "", "y": "__idx__3"}])
    assert (
        "# 日時の列を日時に変換する（自動で認識した書式。読めない値は NaT（欠損）になる）\n"
        'df.isetitem(0, pd.to_datetime(df.iloc[:, 0], format="%Y/%m/%d %H:%M", errors="coerce"))  # 日時 [0]\n'
    ) in script.text
    start, end = script.load_lines
    assert script.text.split("\n")[end - 1].endswith("# 日時 [0]")


def test_expression_variants_match_loader(tmp_path):
    cases = {
        "strip.csv": ["  2026-01-05 ", "2026-01-06", "2026-01-07  "],
        "tz.csv": ["2026-01-05T09:00:00+09:00", "2026-01-05T10:00:00+09:00", "2026-01-05T11:00:00+09:00"],
        "utc.csv": ["2026-01-05T09:00:00Z", "2026-01-05T09:00:00+09:00", "2026-01-05T09:00:00-05:00"],
        "stripmixed.csv": [" 2026-01-05T09:00:00Z", "2026-01-05T09:00:00+09:00 "],
        "ja.csv": ["2026年1月5日", "2026年01月06日", "2026年12月7日"],
    }
    for name, values in cases.items():
        raw = ("t,v\n" + "\n".join(f"{v},{i}" for i, v in enumerate(values)) + "\n").encode("utf-8")
        (tmp_path / name).write_bytes(raw)
        loaded = load_file(raw, name)
        assert loaded.source.datetime_columns, name
        _, _, script = plan_script(loaded)
        pd.testing.assert_frame_equal(exec_load(tmp_path, script), loaded.df)


# ---------------------------------------------------------------- dataprep


def dt_frame(n=6, freq="D"):
    return pd.DataFrame({"t": pd.date_range("2026-01-01", periods=n, freq=freq), "v": np.arange(n, dtype=float), "w": np.arange(n) * 2.0})


def plan(df, **kw):
    raw = default_settings()
    raw["series"] = kw.pop("series", [{"x": "__idx__0", "y": "__idx__1"}])
    mutate = kw.pop("mutate", None)
    if mutate:
        mutate(raw)
    return plan_plot(df, parse_settings(raw))


def test_plan_flags_datetime_x():
    p = plan(dt_frame())
    assert p.datetime_x and p.series[0].datetime_x and not p.series[0].categorical_x and not p.series[0].convert_x
    assert not plan(dt_frame(), series=[{"x": "", "y": "__idx__1"}]).datetime_x


def test_mixed_datetime_and_other_x_is_an_error():
    df = dt_frame()
    with pytest.raises(UserError) as e:
        plan(df, series=[{"x": "__idx__0", "y": "__idx__1"}, {"x": "__idx__2", "y": "__idx__1"}])
    assert "同じ図に描くことはできません" in str(e.value)
    with pytest.raises(UserError):
        plan(df, series=[{"x": "__idx__0", "y": "__idx__1"}, {"x": "", "y": "__idx__2"}])


def test_datetime_x_with_log_or_range_is_an_error():
    with pytest.raises(UserError) as e:
        plan(dt_frame(), mutate=lambda s: s["axes"]["x"].update(scale="log"))
    assert str(e.value) == "X が日時の列のときは、X軸を対数にできません。" and e.value.field == "X軸スケール"
    for key in ("min", "max"):
        with pytest.raises(UserError) as e:
            plan(dt_frame(), mutate=lambda s, k=key: s["axes"]["x"].update(**{k: 3}))
        assert str(e.value) == "X が日時の列のときは、X軸の最小値・最大値は指定できません。空欄にしてください。"
        assert e.value.field == "X軸の範囲"


def test_datetime_y_is_an_error():
    with pytest.raises(UserError) as e:
        plan(dt_frame(), series=[{"x": "__idx__1", "y": "__idx__0"}])
    assert str(e.value) == "系列1: Y列（t）は日時の列です。Y列には数値の列を選んでください。"
    with pytest.raises(UserError):
        plan(dt_frame(), series=[{"x": "", "y": "__idx__0"}], mutate=lambda s: s["plot"].update(type="bar"))


def test_bar_datetime_formats():
    def fmt(df, **kw):
        return plan(df, mutate=lambda s: (s["plot"].update(type="bar", xColumn="__idx__0"), s["axes"]["x"].update(**kw))).bar_date_format

    assert fmt(dt_frame()) == "%Y-%m-%d"
    assert fmt(dt_frame(freq="h")) == "%Y-%m-%d %H:%M"
    df = dt_frame()
    df["t"] = df["t"] + pd.to_timedelta([0, 1, 2, 3, 4, 5], unit="s")
    assert fmt(df) == "%Y-%m-%d %H:%M:%S"
    assert fmt(dt_frame(), dateFormat="%m/%d") == "%m/%d"
    assert auto_bar_date_format(pd.Series([pd.NaT, pd.Timestamp("2026-01-01")])) == "%Y-%m-%d"
    p = plan(dt_frame(), mutate=lambda s: s["plot"].update(type="bar", xColumn="__idx__0"))
    assert p.datetime_x and p.series[0].datetime_x


def test_thin_categorical_flag_counts_distinct_values_over_25():
    def thin(n):
        df = pd.DataFrame({"k": [f"c{i}" for i in range(n)], "v": np.arange(n, dtype=float)})
        return plan(df, series=[{"x": "__idx__0", "y": "__idx__1"}]).thin_categorical_x

    assert not thin(25) and thin(26)
    df = pd.DataFrame({"k": [f"c{i % 5}" for i in range(100)], "v": np.arange(100, dtype=float)})
    assert not plan(df, series=[{"x": "__idx__0", "y": "__idx__1"}]).thin_categorical_x  # 重複は数えない
    assert not plan(dt_frame()).thin_categorical_x


# ---------------------------------------------------------------- codegen / run


class Run:
    def __init__(self, tmp_path, df, mutate=None, series=None):
        self.df = df
        df.to_csv(tmp_path / "m.csv", index=False)
        self.loaded = load_file((tmp_path / "m.csv").read_bytes(), "m.csv")
        raw = default_settings()
        raw["series"] = series or [{"x": "__idx__0", "y": "__idx__1"}]
        if mutate:
            mutate(raw)
        self.settings = parse_settings(raw)
        self.plan = plan_plot(self.loaded.df, self.settings)
        self.script = generate_script(self.settings, self.loaded.source, self.plan)
        self.dir = tmp_path

    def summaries(self):
        with run_script(self.script.text, cwd=self.dir) as r:
            full = figure_summary(r.fig)
        with run_script(self.script.auto_render_text(), injected={"df": self.loaded.df}) as r:
            auto = figure_summary(r.fig)
        return full, auto


@pytest.fixture
def stamps():
    base = datetime(2025, 12, 31, 20, 0)
    n = 10
    return pd.DataFrame({
        "日時": [(base + timedelta(hours=i)).strftime("%Y/%m/%d %H:%M") for i in range(n)],
        "v": np.arange(n, dtype=float),
        "w": np.arange(n) * 2.0,
    })


@pytest.mark.parametrize("plot_type", ["line", "scatter"])
def test_datetime_axis_script_and_summary(tmp_path, stamps, plot_type):
    r = Run(tmp_path, stamps, lambda s: s["plot"].update(type=plot_type))
    text = r.script.text
    assert "import matplotlib.dates as mdates" in text and "ticker" not in text
    assert "x = df.iloc[:, 0]  # 日時の列（読み込み時に日時に変換済み）" in text
    assert "date_locator = mdates.AutoDateLocator()" in text
    assert "ax.xaxis.set_major_locator(date_locator)" in text
    assert "ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(date_locator))" in text
    assert "set_xscale" not in text
    full, auto = r.summaries()
    assert full == auto
    assert "Date" in full[0]["xconverter"]


def test_datetime_axis_steps_cover_the_formatter_lines(tmp_path, stamps):
    r = Run(tmp_path, stamps)
    lines = r.script.text.split("\n")
    n = next(i for i, line in enumerate(lines, start=1) if "ConciseDateFormatter" in line)
    step = r.script.step_for_line(n)
    assert step is not None and "X軸" in step.message


def test_year_boundary_is_visible_on_the_axis(tmp_path, stamps):
    r = Run(tmp_path, stamps)
    with run_script(r.script.text, cwd=tmp_path) as run:
        run.fig.canvas.draw()
        ax = run.fig.axes[0]
        labels = [t.get_text() for t in ax.get_xticklabels()]
        offset = ax.xaxis.get_offset_text().get_text()
        assert any("2026" in t for t in labels) or "2025" in offset or "2026" in offset
        assert any(t for t in labels)  # 空でない目盛ラベルが出る


def test_explicit_date_format_with_japanese(tmp_path, stamps):
    fmt = "%m月%d日 %H時"
    r = Run(tmp_path, stamps, lambda s: s["axes"]["x"].update(dateFormat=fmt))
    assert f'ax.xaxis.set_major_formatter(mdates.DateFormatter("{fmt}"))  # 日時の表示書式' in r.script.text
    assert "ConciseDateFormatter" not in r.script.text
    full, auto = r.summaries()
    assert full == auto
    with run_script(r.script.text, cwd=tmp_path) as run:
        run.fig.canvas.draw()
        assert any("月" in t.get_text() and "時" in t.get_text() for t in run.fig.axes[0].get_xticklabels())


def test_nat_rows_are_excluded_from_plotting(tmp_path, stamps):
    stamps.loc[3, "日時"] = "測定エラー"
    stamps = pd.concat([stamps] * 12, ignore_index=True)  # 先頭 100 行より後ろに不正値を置くため、行数を増やす
    stamps.loc[:99, "日時"] = [(datetime(2025, 12, 31) + timedelta(hours=i)).strftime("%Y/%m/%d %H:%M") for i in range(100)]
    r = Run(tmp_path, stamps)
    assert r.loaded.warnings
    with run_script(r.script.text, cwd=tmp_path) as run:
        line = run.fig.axes[0].get_lines()[0]
        assert len(line.get_xdata()) == r.loaded.df.iloc[:, 0].notna().sum() - r.loaded.df.iloc[:, 1].isna().sum()


def test_datetime_bar_single_and_multi(tmp_path):
    shutil.copy(FIXTURES / "dates_ja.csv", tmp_path / "dates_ja.csv")
    loaded = load_file((FIXTURES / "dates_ja.csv").read_bytes(), "dates_ja.csv")
    for series, fn in (([{"x": "", "y": "__idx__1"}], "single"), ([{"x": "", "y": "__idx__1"}, {"x": "", "y": "__idx__1"}], "multi")):
        raw = default_settings()
        raw["plot"].update(type="bar", xColumn="__idx__0")
        raw["series"] = series
        settings = parse_settings(raw)
        plan_ = plan_plot(loaded.df, settings)
        script = generate_script(settings, loaded.source, plan_)
        assert 'x = df.iloc[:, 0].dt.strftime("%Y-%m-%d")  # 日時を文字列にして、棒をカテゴリとして並べる' in script.text
        assert "mdates" not in script.text
        with run_script(script.text, cwd=tmp_path) as run:
            labels = [t.get_text() for t in run.fig.axes[0].get_xticklabels()]
            assert labels[0] == "2026-01-05" and len(labels) == 8, fn
        with run_script(script.auto_render_text(), injected={"df": loaded.df}) as run:
            assert [t.get_text() for t in run.fig.axes[0].get_xticklabels()] == labels


def test_datetime_bar_with_custom_format(tmp_path):
    shutil.copy(FIXTURES / "dates_ja.csv", tmp_path / "dates_ja.csv")
    loaded = load_file((FIXTURES / "dates_ja.csv").read_bytes(), "dates_ja.csv")
    raw = default_settings()
    raw["plot"].update(type="bar", xColumn="__idx__0")
    raw["axes"]["x"]["dateFormat"] = "%m月%d日"
    raw["series"] = [{"x": "", "y": "__idx__1"}]
    settings = parse_settings(raw)
    script = generate_script(settings, loaded.source, plan_plot(loaded.df, settings))
    assert '.dt.strftime("%m月%d日")' in script.text
    with run_script(script.text, cwd=tmp_path) as run:
        assert [t.get_text() for t in run.fig.axes[0].get_xticklabels()][0] == "01月05日"


def test_string_x_has_no_linear_scale_and_thins_only_above_25(tmp_path):
    def build(n):
        df = pd.DataFrame({"k": [f"c{i}" for i in range(n)], "v": np.arange(n, dtype=float)})
        return Run(tmp_path, df, series=[{"x": "__idx__0", "y": "__idx__1"}])

    few = build(25)
    assert "set_xscale" not in few.script.text and "ticker" not in few.script.text and "MaxNLocator" not in few.script.text
    full, auto = few.summaries()
    assert full == auto and full[0]["xticklabels"][:2] == ["c0", "c1"]
    many = build(60)
    assert "import matplotlib.ticker as ticker" in many.script.text
    assert "ax.xaxis.set_major_locator(ticker.MaxNLocator(nbins=25, integer=True))" in many.script.text
    assert "# X が文字列の列: 目盛に X の値を出す（25個を超えるので間引く）" in many.script.text
    full, auto = many.summaries()
    assert full == auto and 2 <= len([t for t in full[0]["xticklabels"] if t]) <= 30


def test_ticker_import_absent_for_date_axis_and_numeric(tmp_path, stamps):
    assert "ticker" not in Run(tmp_path, stamps).script.text
    num = pd.DataFrame({"x": np.arange(5.0), "y": np.arange(5.0)})
    t = Run(tmp_path, num).script.text
    assert "mdates" not in t and "ticker" not in t


# ---------------------------------------------------------------- injection


EVIL_FORMATS = ['%Y"); import os #', "%Y'\n%m", '%d" + __import__("os").system("x") + "', "%Y\\"]


@pytest.mark.parametrize("fmt", EVIL_FORMATS)
def test_date_format_cannot_inject_code(tmp_path, stamps, fmt):
    raw_ok = True
    try:
        r = Run(tmp_path, stamps, lambda s: s["axes"]["x"].update(dateFormat=fmt))
    except UserError:
        raw_ok = False  # settings が弾く場合もある
    if raw_ok:
        import ast

        tree = ast.parse(r.script.text)
        assert not any(isinstance(n, ast.Import) and any(a.name == "os" for a in n.names) for n in ast.walk(tree))
        assert "__import__" not in [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
        full, auto = r.summaries()
        assert full == auto


def test_datetime_column_name_cannot_inject_code(tmp_path):
    name = 'x"\nimport os  # '
    spec = DatetimeColumn(index=0, name=name, format="%Y-%m-%d")
    from mplgui.codegen import generate_script as gen

    loaded = load_file(b"a,v\n2026-01-01,1\n2026-01-02,2\n", "a.csv")
    source = SourceInfo(filename="a.csv", kind="csv", encoding="utf-8", separator=",", datetime_columns=(spec,))
    settings = parse_settings({**default_settings(), "series": [{"x": "__idx__0", "y": "__idx__1"}]})
    script = gen(settings, source, plan_plot(loaded.df, settings))
    for line in script.text.split("\n"):
        assert not line.startswith("import os")
    compile(script.text, "plot.py", "exec")


# ---------------------------------------------------------------- performance (informational)


def test_ten_thousand_rows_load_and_render_is_reasonable():
    n = 10000
    base = datetime(2025, 1, 1)
    rng = np.random.default_rng(0)
    cols = {"日時": [(base + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M") for i in range(n)]}
    for k in range(5):
        cols[f"y{k}"] = rng.normal(size=n)
    raw = pd.DataFrame(cols).to_csv(index=False).encode("utf-8")
    t0 = time.perf_counter()
    out = json.loads(api.load_file_json("big.csv", raw, json.dumps(default_settings())))
    t1 = time.perf_counter()
    assert out["ok"] and out["columns"][0]["kind"] == "datetime"
    s = default_settings()
    s["series"] = [{"x": "__idx__0", "y": f"__idx__{k + 1}"} for k in range(5)]
    res = json.loads(api.render_json(json.dumps(s)))
    t2 = time.perf_counter()
    assert res["ok"]
    print(f"\nload_file {t1 - t0:.2f}s, render {t2 - t1:.2f}s")
    assert t1 - t0 < 10 and t2 - t1 < 15
