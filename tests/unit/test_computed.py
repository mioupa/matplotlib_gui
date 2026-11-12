"""Phase 5c: 計算した列（G6）。設定・列の番号・計算（skipRows の後）・警告とエラー・生成コード・自動描画のコピー。"""
import contextlib
import json
import warnings

import numpy as np
import pandas as pd
import pytest

from mplgui import api, dataprep
from mplgui.codegen import generate_script
from mplgui.dataprep import plan_plot, slice_skip_rows
from mplgui.errors import UserError
from mplgui.loader import load_file
from mplgui.runner import figure_summary, run_script
from mplgui.settings import MAX_COMPUTED, default_computed, default_settings, parse_settings

pytestmark = pytest.mark.unit

N = 10


def frame():
    t = np.arange(N, dtype=float)
    return pd.DataFrame({"t": t, "v": t * 2 + 10, "lo": t * 2 + 8, "hi": t * 2 + 13, "w": 100 - t * 3.0})


def other_frame():
    t = np.arange(N, dtype=float)
    return pd.DataFrame({"a": t, "b": t**2, "c": t + 0.5})


def s(y, x=0, **kw):
    d = {"x": f"__idx__{x}", "y": f"__idx__{y}"}
    d.update(kw)
    return d


def comp(expr, name="", source="", **kw):
    return {"name": name, "expr": expr, "source": source, **kw}


def make_raw(series_list, computed, plot_type="line", files=None, **plot):
    raw = default_settings()
    raw["series"] = series_list
    raw["computed"] = computed
    raw["plot"]["type"] = plot_type
    raw["plot"].update(plot)
    if files:
        raw["load"]["files"] = [{"id": i, "name": n, "sheet": ""} for i, n, _ in files]
    return raw


class Built:
    """1 つ以上の CSV を読み込み、描画計画・スクリプトを作る。files は [(id, ファイル名, DataFrame)]。"""

    def __init__(self, tmp_path, raw, files=None):
        files = files or [("d1", "d.csv", frame())]
        self.dir = tmp_path
        self.loaded = {}
        for fid, name, df in files:
            df.to_csv(tmp_path / name, index=False, encoding="utf-8")
            self.loaded[fid] = load_file((tmp_path / name).read_bytes(), name, "", True)
        self.settings = parse_settings(raw)
        self.plan = plan_plot({fid: ld.df for fid, ld in self.loaded.items()}, self.settings)
        self.script = generate_script(self.settings, {fid: ld.source for fid, ld in self.loaded.items()}, self.plan)

    @contextlib.contextmanager
    def full(self):
        with _strict_warnings(), run_script(self.script.text, cwd=self.dir) as run:
            yield run

    @contextlib.contextmanager
    def auto(self):
        with_computed = {c.data_id for c in self.plan.computed}
        injected = {
            src.var: self.loaded[src.id].df.copy() if src.id in with_computed else self.loaded[src.id].df
            for src in self.plan.sources
        }
        with _strict_warnings(), run_script(self.script.auto_render_text(), injected=injected) as run:
            yield run

    def summaries(self):
        with self.full() as run:
            full = figure_summary(run.fig)
        with self.auto() as run:
            auto = figure_summary(run.fig)
        assert full == auto
        return full


@contextlib.contextmanager
def _strict_warnings():
    """pandas の警告（SettingWithCopy など）を例外にする。フォントの警告だけは無視する。"""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        warnings.filterwarnings("ignore", message=".*missing from.*")
        yield


def ydata(ax, i=0):
    return ax.lines[i].get_ydata()


# ---------------------------------------------------------------- 設定


def test_defaults_and_missing_keys():
    assert default_computed() == {"id": "", "source": "", "name": "", "expr": ""}
    assert default_settings()["computed"] == []
    assert parse_settings(default_settings()).computed == ()
    st = parse_settings(make_raw([s(1)], [{"expr": "[1] * 2"}]))
    c = st.computed[0]
    assert (c.id, c.source, c.name, c.expr) == ("c1", "", "", "[1] * 2")
    assert c.expr_node is not None
    # computed キーが無い設定（v3 や 5b までの設定）は計算した列なし
    raw = default_settings()
    del raw["computed"]
    assert parse_settings(raw).computed == ()


def test_limit_is_twenty():
    ok = [comp("[1]")] * MAX_COMPUTED
    assert len(parse_settings(make_raw([s(1)], ok)).computed) == MAX_COMPUTED
    with pytest.raises(UserError) as e:
        parse_settings(make_raw([s(1)], ok + [comp("[1]")]))
    assert str(e.value) == "計算した列は20個までです。"


def test_ids_are_renumbered_when_blank_or_duplicated():
    raw = make_raw([s(1)], [comp("[1]", id="c5"), comp("[1]", id="c5"), comp("[1]", id=""), comp("[1]", id="c2"), comp("[1]", id=7)])
    ids = [c.id for c in parse_settings(raw).computed]
    assert ids == ["c5", "c2", "c3", "c4", "c5_"]  # 重複・空・文字列でない id は位置で振り直し、それも重なれば「_」を足す
    assert parse_settings(make_raw([s(1)], [comp("[1]", id="c9"), comp("[1]", id="c4")])).computed[1].id == "c4"


def test_name_length_and_strip():
    ok = parse_settings(make_raw([s(1)], [comp("[1]", name="  あ" * 1 + "x" * 49 + "  ")])).computed[0]
    assert len(ok.name) == 50
    with pytest.raises(UserError) as e:
        parse_settings(make_raw([s(1)], [comp("[1]"), comp("[1]", name="x" * 51)]))
    assert e.value.field == "計算した列2の名前"


def test_empty_expression_and_types():
    with pytest.raises(UserError) as e:
        parse_settings(make_raw([s(1)], [comp("[1]"), comp("   ")]))
    assert str(e.value) == "計算した列2の式を入力してください。" and e.value.field == "計算した列2の式"
    with pytest.raises(UserError):
        parse_settings(make_raw([s(1)], [{"expr": 5}]))
    with pytest.raises(UserError):
        parse_settings(make_raw([s(1)], "x"))


def test_syntax_error_message_and_field():
    with pytest.raises(UserError) as e:
        parse_settings(make_raw([s(1)], [comp("max([1]")]))
    assert e.value.field == "計算した列1の式"
    assert str(e.value).startswith("計算した列1の式: ") and "文字目: " in str(e.value)
    assert "閉じ括弧" in str(e.value)


def test_unknown_source():
    raw = make_raw([s(1)], [comp("[1]", source="d9")], files=[("d1", "a.csv", None)])
    with pytest.raises(UserError) as e:
        parse_settings(raw)
    assert e.value.field == "計算した列1のデータ元" and str(e.value).startswith("計算した列1のデータ元が見つかりません。")
    raw["computed"][0]["source"] = "d1"
    assert parse_settings(raw).computed[0].source == "d1"
    raw["load"]["files"] = []  # ファイルの一覧が空なら、空でない source は見つからない
    with pytest.raises(UserError):
        parse_settings(raw)


@pytest.mark.parametrize("plot_type", ["line", "step", "scatter", "scatterColor", "bar", "barh", "barStacked", "hist"])
def test_always_validated_for_every_plot_type(plot_type):
    raw = make_raw([s(1, colorColumn="__idx__2")], [comp("")], plot_type=plot_type)
    with pytest.raises(UserError) as e:
        parse_settings(raw)
    assert e.value.field == "計算した列1の式"


# ---------------------------------------------------------------- 列の番号


def test_single_file_numbering_order_and_names(tmp_path):
    raw = make_raw([s(5), s(6)], [comp("[1] / max([1])", name="比"), comp("[4] * 2")])
    b = Built(tmp_path, raw)
    assert [(c.number, c.name, c.index, c.data_var) for c in b.plan.computed] == [(1, "比", 5, "df"), (2, "計算2", 6, "df")]
    with b.full() as run:
        ax = run.fig.axes[0]
        v = frame()["v"].to_numpy()
        assert np.allclose(ydata(ax, 0), v / v.max())
        assert np.allclose(ydata(ax, 1), frame()["w"].to_numpy() * 2)
        df = run.namespace["df"]
        assert list(df.columns[5:]) == ["比", "計算2"]
    b.summaries()


def test_card_number_is_position_in_whole_list_across_sources(tmp_path):
    files = [("d1", "a.csv", frame()), ("d2", "b.csv", other_frame())]
    raw = make_raw(
        [s(5, source="d1"), s(3, x=0, source="d2"), s(4, x=0, source="d2")],
        [comp("[1] * 2", source="d1"), comp("[1] + [2]", source="d2"), comp("[0] - [1]", source="d1"), comp("[2] * 10", source="d2")],
        files=files,
    )
    b = Built(tmp_path, raw, files)
    got = {(c.number, c.data_id): (c.index, c.name, c.data_var) for c in b.plan.computed}
    assert got == {
        (1, "d1"): (5, "計算1", "df1"),
        (2, "d2"): (3, "計算2", "df2"),
        (3, "d1"): (6, "計算3", "df1"),
        (4, "d2"): (4, "計算4", "df2"),
    }
    with b.full() as run:
        ax = run.fig.axes[0]
        assert np.allclose(ydata(ax, 0), frame()["v"].to_numpy() * 2)
        assert np.allclose(ydata(ax, 1), (other_frame()["b"] + other_frame()["c"]).to_numpy())
        assert np.allclose(ydata(ax, 2), other_frame()["c"].to_numpy() * 10)
    b.summaries()
    assert "df1.insert" in b.script.text and "df2.insert" in b.script.text


def test_all_column_kinds_resolve_to_computed_columns(tmp_path):
    computed = [comp("[0] * 2"), comp("[1] + 1"), comp("[2] + 1"), comp("[3] + 1"), comp("abs([4]) / 10")]
    raw = make_raw(
        [
            s(
                6,
                x=5,
                errorBars={"y": {"mode": "column", "column": "__idx__9"}, "x": {"mode": "column", "column": "__idx__9"}},
                fill={"lower": "__idx__7", "upper": "__idx__8", "alpha": 0.25},
            )
        ],
        computed,
    )
    b = Built(tmp_path, raw)
    assert b.plan.series[0].x_index == 5 and b.plan.series[0].y_index == 6
    summary = b.summaries()[0]
    assert summary["bands"] == 1 and summary["errorbars"] == 2
    with b.full() as run:
        assert np.allclose(run.fig.axes[0].lines[-1].get_xdata(), frame()["t"].to_numpy() * 2)


def test_scatter_color_column_can_be_computed(tmp_path):
    raw = make_raw([s(1, x=0, colorColumn="__idx__5")], [comp("[4] / 2")], plot_type="scatterColor")
    b = Built(tmp_path, raw)
    summary = b.summaries()[0]
    w = frame()["w"].to_numpy() / 2
    assert summary["colorbar"]["vmin"] == pytest.approx(w.min()) and summary["colorbar"]["vmax"] == pytest.approx(w.max())


def test_bar_x_column_can_be_computed(tmp_path):
    raw = make_raw([s(1)], [comp("[0] * 10")], plot_type="bar", xColumn="__idx__5")
    b = Built(tmp_path, raw)
    assert b.plan.bar_x_index == 5
    b.summaries()
    with b.full() as run:  # 数値の X 列の単独の棒は、数値の位置に棒を置く
        centers = sorted(p.get_x() + p.get_width() / 2 for p in run.fig.axes[0].patches)
        assert np.allclose(centers, np.arange(N) * 10.0)


def test_auto_y_assignment_ignores_computed_columns(tmp_path):
    base = Built(tmp_path, make_raw([{"x": "__idx__0", "y": ""}, {"x": "__idx__0", "y": ""}], []))
    with_c = Built(tmp_path, make_raw([{"x": "__idx__0", "y": ""}, {"x": "__idx__0", "y": ""}], [comp("[1] * 2")]))
    assert [p.y_index for p in with_c.plan.series] == [p.y_index for p in base.plan.series]
    # 文字列の列が先頭にあり、計算した列だけが数値、というデータでも、自動の Y はファイルの列から選ぶ
    df = pd.DataFrame({"name": ["a", "b", "c"], "v": [1.0, 2.0, 3.0]})
    raw = make_raw([{"x": "", "y": ""}], [comp("[1] * 2")])
    b = Built(tmp_path, raw, [("d1", "t.csv", df)])
    assert b.plan.series[0].y_index == 1


# ---------------------------------------------------------------- 計算


def test_computed_after_skip_rows_uses_remaining_rows_only(tmp_path):
    raw = make_raw([s(5), s(6)], [comp("[1] / max([1])"), comp("[1] - first([1])")], skipRows=3)
    b = Built(tmp_path, raw)
    v = frame()["v"].to_numpy()[3:]
    with b.full() as run:
        ax = run.fig.axes[0]
        assert np.allclose(ydata(ax, 0), v / v.max()) and ydata(ax, 0)[-1] == pytest.approx(1.0)
        assert np.allclose(ydata(ax, 1), v - v[0]) and ydata(ax, 1)[0] == 0
        assert len(run.namespace["df"]) == N - 3
    b.summaries()


def test_skip_rows_error_comes_before_computation(tmp_path):
    raw = make_raw([s(1)], [comp("[1] / max([1])")], skipRows=N)
    df = frame()
    loaded = load_file(df.to_csv(index=False).encode(), "d.csv", "", True)
    with pytest.raises(UserError) as e:
        plan_plot(loaded.df, parse_settings(raw))
    assert e.value.field == "除外する先頭行数"


def test_non_numeric_values_warn_with_hints_and_become_nan():
    df = pd.DataFrame({"t": [0.0, 1, 2, 3], "x": ["1,234", "2", "abc", ""]})
    raw = make_raw([s(2)], [comp("[1] * 2", name="倍")])
    plan = plan_plot(df, parse_settings(raw))
    (w,) = plan.warnings
    assert w["message"].startswith("計算した列1（倍）: 列「x」[1] に数値にできない値が2件あったため、欠損として計算します（例: ")
    assert '"1,234"' in w["message"] and '"abc"' in w["message"]
    assert "桁区切りのカンマなら" in w["message"]
    # 小数点カンマのヒント
    df2 = pd.DataFrame({"t": [0.0, 1], "x": ["1,5", "2"]})
    (w2,) = plan_plot(df2, parse_settings(make_raw([s(2)], [comp("[1]")]))).warnings
    assert "小数点がカンマなら" in w2["message"]
    # 空欄だけなら警告しない
    df3 = pd.DataFrame({"t": [0.0, 1], "x": ["", "2"]})
    assert plan_plot(df3, parse_settings(make_raw([s(2)], [comp("[1]")]))).warnings == ()


def test_non_numeric_warning_counts_only_rows_after_skip_rows():
    df = pd.DataFrame({"t": [0.0, 1, 2, 3], "x": ["bad", "bad", "2", "3"]})
    raw = make_raw([s(2)], [comp("[1]")], skipRows=2)
    assert plan_plot(df, parse_settings(raw)).warnings == ()


def test_invalid_count_warning():
    df = pd.DataFrame({"t": [0.0, 1, 2, 3], "x": [0.0, 1, 0, -4]})
    raw = make_raw([s(2), s(3)], [comp("1 / [1]", name="逆数"), comp("sqrt([1])")])
    plan = plan_plot(df, parse_settings(raw))
    assert [w["message"] for w in plan.warnings] == [
        "計算した列1（逆数）: 0 での割り算・負の数の平方根などで計算できなかった値が2件あったため、欠損として扱います。",
        "計算した列2（計算2）: 0 での割り算・負の数の平方根などで計算できなかった値が1件あったため、欠損として扱います。",
    ]
    # 入力が欠損のときは数えない
    df2 = pd.DataFrame({"t": [0.0, 1], "x": [np.nan, 2.0]})
    assert plan_plot(df2, parse_settings(make_raw([s(2)], [comp("1 / [1]")]))).warnings == ()


def test_series_using_computed_y_has_no_extra_dropped_warning():
    df = pd.DataFrame({"t": [0.0, 1, 2, 3], "x": ["1", "oops", "3", "4"]})
    plan = plan_plot(df, parse_settings(make_raw([s(2)], [comp("[1] * 2")])))
    assert len(plan.warnings) == 1 and plan.warnings[0]["message"].startswith("計算した列1（計算1）:")
    assert plan.series[0].has_points


def test_datetime_column_reference_is_error():
    df = pd.DataFrame({"when": pd.to_datetime(["2026-01-01", "2026-01-02"]), "v": [1.0, 2.0]})
    with pytest.raises(UserError) as e:
        plan_plot(df, parse_settings(make_raw([s(1)], [comp("[0] + 1")])))
    assert str(e.value) == "計算した列1の式: 1文字目: 列 [0]（when）は日時の列なので、計算に使えません。"
    assert e.value.field == "計算した列1の式"


def test_out_of_range_reference_is_error():
    with pytest.raises(UserError) as e:
        plan_plot(frame(), parse_settings(make_raw([s(1)], [comp("[1] + [7]")])))
    assert str(e.value) == "計算した列1の式: 7文字目: 列 [7] はありません（データの列は [0]〜[4] です）。"
    # 計算した列が 1 つしかないときの [6] は、範囲外
    with pytest.raises(UserError) as e:
        plan_plot(frame(), parse_settings(make_raw([s(1)], [comp("[6]")])))
    assert "列 [6] はありません" in str(e.value)


def test_reference_to_another_computed_column_is_specific_error():
    raw = make_raw([s(1)], [comp("[1] * 2"), comp("[5] + 1")])
    with pytest.raises(UserError) as e:
        plan_plot(frame(), parse_settings(raw))
    assert str(e.value) == "計算した列2の式: 1文字目: 計算した列（[5]）は、ほかの計算した列の式には使えません。"
    assert e.value.field == "計算した列2の式"
    # 自分自身も、後ろの計算した列も同じ
    for expr in ("[5] + 1", "[6] + 1"):
        with pytest.raises(UserError) as e:
            plan_plot(frame(), parse_settings(make_raw([s(1)], [comp(expr), comp("[1]")])))
        assert "ほかの計算した列の式には使えません" in str(e.value)


def test_scalar_expression_broadcasts(tmp_path):
    raw = make_raw([s(5)], [comp("max([1]) - min([1])")])
    b = Built(tmp_path, raw)
    with b.full() as run:
        v = frame()["v"]
        assert np.allclose(ydata(run.fig.axes[0]), v.max() - v.min())
        assert len(run.namespace["df"]) == N and run.namespace["df"].shape[1] == 6
    assert "pd.Series(" in b.script.text
    b.summaries()


# ---------------------------------------------------------------- 生成コード


def test_generated_values_equal_dataprep_values(tmp_path):
    exprs = ["[1] / max([1])", "rolling_mean([4], 3)", "diff([1])", "cumsum([4])", "1 / ([1] - 10)", "sqrt([4] - 90)", "[1] - first([1])", "-2 ** [0] + mean([1])"]
    df = frame()
    df.loc[3, "v"] = np.nan
    raw = make_raw([s(5)], [comp(e) for e in exprs], skipRows=2)
    b = Built(tmp_path, raw, [("d1", "d.csv", df)])
    frames = {"d1": slice_skip_rows(b.loaded["d1"].df, 2)}
    dataprep._apply_computed(frames, "d1", b.settings, {"d1": "df"})
    expected = frames["d1"].iloc[:, 5:]
    with b.full() as run:
        got = run.namespace["df"].iloc[:, 5:]
    assert got.shape == expected.shape == (N - 2, len(exprs))
    for i in range(len(exprs)):
        pd.testing.assert_series_equal(got.iloc[:, i], expected.iloc[:, i], check_names=False)
        assert not np.isinf(got.iloc[:, i].to_numpy()).any()
    b.summaries()


def test_section_only_with_computed_columns_and_numbering(tmp_path):
    none = Built(tmp_path, make_raw([s(1)], []))
    assert "計算した列" not in none.script.text and none.script.text.count("# ==== ") == 8
    some = Built(tmp_path, make_raw([s(5)], [comp("[1] * 2")], skipRows=1))
    t = some.script.text
    assert "# ==== 3. 計算した列 ====" in t and "# ==== 4. 図と軸 ====" in t
    assert t.index("2. 描画に使う行") < t.index("3. 計算した列") < t.index("4. 図と軸")
    assert 'with np.errstate(divide="ignore", invalid="ignore", over="ignore")' in t
    assert 'df.insert(df.shape[1], "計算1", calc.replace([np.inf, -np.inf], np.nan), allow_duplicates=True)' in t
    # 計算した列が無い設定の生成コードは、計算した列の項目に影響されない
    assert generate_script(none.settings, none.loaded["d1"].source, none.plan).text == none.script.text


def test_steps_report_failed_computed_column(tmp_path):
    b = Built(tmp_path, make_raw([s(5)], [comp("[1]", name="甲"), comp("[4] * 2", name="乙")]))
    steps = [st for st in b.script.steps if st.field and st.field.startswith("計算した列")]
    assert [st.field for st in steps] == ["計算した列1の式", "計算した列2の式"]
    assert steps[1].message == "計算した列2（乙）を計算できませんでした。式を確認してください。"
    lines = b.script.text.split("\n")
    assert any("col4" in ln for ln in lines[steps[1].start - 1 : steps[1].end])


NASTY_NAMES = [
    'x"); import os; ("',
    "a'b\"c",
    "x\nimport os\nprint(1)",
    "x\\",
    "x import os y",
    "\\n#",
    "x\r\ny\x0b",
]


@pytest.mark.parametrize("name", NASTY_NAMES)
def test_name_injection(tmp_path, name):
    raw = make_raw([s(5)], [comp("[1] * 2", name=name)])
    b = Built(tmp_path, raw)
    compile(b.script.text, "<x>", "exec")  # 構文として壊れていない
    with b.full() as run:
        assert "os" not in run.namespace
        assert run.namespace["df"].columns[5] == b.settings.computed[0].name  # 名前は文字列としてそのまま入る
        assert run.namespace["df"].shape[1] == 6
    # コメントの行が増えていない（改行が空白になっている）: 注入した行が単独の文になっていない
    assert not any(line.strip().startswith(("import os", "print(1)")) for line in b.script.text.split("\n"))
    b.summaries()


@pytest.mark.parametrize("expr", ["[1]\n+ 1", "[1]\t* 2", "　[1]　+ 1"])
def test_expression_whitespace_variants_cannot_break_comments(tmp_path, expr):
    raw = make_raw([s(5)], [comp(expr)])
    try:
        b = Built(tmp_path, raw)
    except UserError:
        return  # 受け付けない書き方なら、コードにならない
    comment = [ln for ln in b.script.text.split("\n") if "計算した列1:" in ln]
    assert len(comment) == 1
    compile(b.script.text, "<x>", "exec")
    with b.full() as run:
        assert run.namespace["df"].shape[1] == 6


@pytest.mark.parametrize("expr", ['[1]); import os; (', '"); import os; ("', "[1] # \n import os", "__import__('os')", "[1]; import os", "[1] + 'a'"])
def test_expression_with_code_is_rejected(expr):
    with pytest.raises(UserError) as e:
        parse_settings(make_raw([s(1)], [comp(expr)]))
    assert e.value.field == "計算した列1の式"


def test_expression_text_only_appears_in_comments(tmp_path):
    raw = make_raw([s(5)], [comp("  [1]   /  max( [1] )  ")])
    b = Built(tmp_path, raw)
    for line in b.script.text.split("\n"):
        if "[1]   /  max( [1] )" in line:
            assert line.lstrip().startswith("#")


def test_unused_source_is_not_computed_or_emitted(tmp_path):
    files = [("d1", "a.csv", frame()), ("d2", "b.csv", other_frame())]
    # d2 の計算した列は、d2 の列にない [9] を参照している（使わないデータ元なので、データの検査はしない）
    raw = make_raw([s(5, source="d1")], [comp("[1] * 2", source="d1"), comp("[9] * 2", source="d2")], files=files)
    b = Built(tmp_path, raw, files)
    assert [c.data_id for c in b.plan.computed] == ["d1"]
    assert "df2" not in b.script.text and "DATA_FILE_2" not in b.script.text
    assert b.script.text.count("df1.insert") == 1
    b.summaries()
    # 構文の誤りは、使わないデータ元でも設定の検証で止まる
    raw["computed"][1]["expr"] = "[9] *"
    with pytest.raises(UserError):
        parse_settings(raw)
    # すべて使わないデータ元なら、計算した列の節は出ない
    raw2 = make_raw([s(1, source="d1")], [comp("[9]", source="d2")], files=files)
    b2 = Built(tmp_path, raw2, files)
    assert b2.plan.computed == () and "計算した列" not in b2.script.text


def test_computed_on_default_source_follows_first_file(tmp_path):
    files = [("d1", "a.csv", frame()), ("d2", "b.csv", other_frame())]
    raw = make_raw([s(5, source="d1")], [comp("[1] * 2")], files=files)  # source 空 = 先頭のファイル
    b = Built(tmp_path, raw, files)
    assert b.plan.computed[0].data_id == "d1" and b.plan.computed[0].data_var == "df1"


def test_bad_reference_in_used_source_names_that_source_columns(tmp_path):
    files = [("d1", "a.csv", frame()), ("d2", "b.csv", other_frame())]
    raw = make_raw([s(1, source="d1"), s(3, source="d2")], [comp("[1] + [4]", source="d2")], files=files)
    with pytest.raises(UserError) as e:
        Built(tmp_path, raw, files)
    assert "列 [4] はありません（データの列は [0]〜[2] です）" in str(e.value)


# ---------------------------------------------------------------- 新しいグラフの種類と計算した列


def test_step_with_computed_y(tmp_path):
    raw = make_raw([s(5)], [comp("cumsum([1])")], plot_type="step")
    b = Built(tmp_path, raw)
    summary = b.summaries()[0]
    assert summary["drawstyles"] == ["steps-post"]
    with b.full() as run:
        assert np.allclose(ydata(run.fig.axes[0]), np.cumsum(frame()["v"].to_numpy()))


def test_hist_with_computed_y(tmp_path):
    raw = make_raw([{"x": "", "y": "__idx__5"}], [comp("[1] - mean([1])")], plot_type="hist")
    b = Built(tmp_path, raw)
    summary = b.summaries()[0]
    assert summary["bars"]["vertical"] > 0
    v = frame()["v"].to_numpy()
    with b.full() as run:
        heights = sum(p.get_height() for p in run.fig.axes[0].patches)
        assert heights == N and run.fig.axes[0].get_xlim()[0] <= (v - v.mean()).min()


def test_scatter_color_with_computed_y_and_color(tmp_path):
    raw = make_raw([s(5, x=0, colorColumn="__idx__6")], [comp("[1] * 3"), comp("[4] / 100")], plot_type="scatterColor")
    b = Built(tmp_path, raw)
    summary = b.summaries()[0]
    assert summary["colorbar"]["vmax"] == pytest.approx(1.0)


def test_barh_and_stacked_with_computed_y(tmp_path):
    for plot_type in ("barh", "barStacked", "bar"):
        raw = make_raw([s(5), s(6)], [comp("[1] / 10"), comp("[4] / 10")], plot_type=plot_type, xColumn="__idx__0")
        Built(tmp_path, raw).summaries()


def test_computed_with_no_series_data_source_error_is_unchanged():
    raw = make_raw([s(1)], [comp("[1]")], files=[("d1", "a.csv", None)])
    with pytest.raises(UserError) as e:
        plan_plot({"d2": frame()}, parse_settings(raw))
    assert "読み込めていません" in str(e.value) or "データ" in str(e.value)


# ---------------------------------------------------------------- api（自動描画はコピーを渡す）


@pytest.fixture
def session(tmp_path):
    api.SESSION.forget()
    api.SESSION.workdir = tmp_path
    yield api.SESSION
    api.SESSION.forget()
    api.SESSION.workdir = None


@pytest.mark.parametrize("skip", [0, 2])
def test_auto_render_does_not_grow_the_session_dataframe(session, skip):
    raw = make_raw([s(5)], [comp("[1] / max([1])", name="比")], skipRows=skip)
    csv = frame().to_csv(index=False).encode()
    r = json.loads(api.load_file_json("d.csv", csv, json.dumps(raw)))
    assert r["ok"]
    before = session.sources["d1"].df.copy()
    shape = session.sources["d1"].df.shape
    summaries = []
    for _ in range(3):
        out = json.loads(api.render_json(json.dumps(raw)))
        assert out["ok"], out
        summaries.append(out["summary"])
        assert session.sources["d1"].df.shape == shape == (N, 5)
    pd.testing.assert_frame_equal(session.sources["d1"].df, before)
    assert summaries[0] == summaries[1] == summaries[2]
    assert "df.insert" in out["code"]
    # 保存・コピー・コードだけの更新も同じ
    assert json.loads(api.script_json(json.dumps(raw)))["code"] == out["code"]
    assert json.loads(api.save_json(json.dumps(raw)))["ok"]
    assert session.sources["d1"].df.shape == shape


def test_api_two_files_only_copies_sources_with_computed(session):
    files = [("d1", "a.csv", frame()), ("d2", "b.csv", other_frame())]
    raw = make_raw([s(5, source="d1"), s(2, source="d2")], [comp("[1] * 2", source="d1")], files=files)
    for fid, name, df in files:
        assert json.loads(api.load_file_json(name, df.to_csv(index=False).encode(), json.dumps(raw), fid))["ok"]
    for _ in range(2):
        out = json.loads(api.render_json(json.dumps(raw)))
        assert out["ok"], out
    assert session.sources["d1"].df.shape == (N, 5) and session.sources["d2"].df.shape == (N, 3)


def test_api_reports_computed_errors_with_field(session):
    raw = make_raw([s(1)], [comp("[1] * 2")])
    assert json.loads(api.load_file_json("d.csv", frame().to_csv(index=False).encode(), json.dumps(raw)))["ok"]
    raw["computed"][0]["expr"] = "[1] * (2"
    out = json.loads(api.render_json(json.dumps(raw)))
    assert out["ok"] is False and out["error"]["field"] == "計算した列1の式"
    raw["computed"][0]["expr"] = "[1] + [8]"
    out = json.loads(api.render_json(json.dumps(raw)))
    assert out["ok"] is False and "列 [8] はありません" in out["error"]["message"]
