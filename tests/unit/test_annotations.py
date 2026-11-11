"""Phase 5b: 注釈（G4）。dataprep の解釈・検査と、生成コードを CPython で実行した図を検査する。"""
import pandas as pd
import pytest

from mplgui.errors import UserError
from mplgui.settings import MAX_ANNOTATIONS, default_annotation, parse_settings
from style_helpers import Built, frame, plan_of, raw_settings, series

pytestmark = pytest.mark.unit


def ann(kind="hline", **kw):
    d = {"kind": kind}
    d.update(kw)
    return d


def dates_frame():
    df = frame()
    df["d"] = pd.date_range("2026-01-01", periods=len(df)).strftime("%Y-%m-%d")
    return df


def text_frame():
    df = frame()
    df["c"] = [f"k{i}" for i in range(len(df))]
    return df


def build(tmp_path, annotations, df=None, **kw):
    return Built(tmp_path, df=df, annotations=annotations, **kw)


# ---------------------------------------------------------------- 設定


def test_default_annotation_shape():
    d = default_annotation()
    assert d["kind"] == "hline" and d["coords"] == "data" and d["alpha"] is None and d["fontSize"] is None
    assert parse_settings(raw_settings(annotations=[d])).annotations[0].kind == "hline"


def test_missing_keys_filled_and_numbers_become_strings():
    s = parse_settings(raw_settings(annotations=[{"kind": "text", "x": 1.5, "y": 2, "text": "a"}])).annotations[0]
    assert (s.x, s.y, s.color, s.coords) == ("1.5", "2", "#000000", "data")


def test_limit_of_50():
    parse_settings(raw_settings(annotations=[ann(y=1)] * MAX_ANNOTATIONS))
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings(annotations=[ann(y=1)] * (MAX_ANNOTATIONS + 1)))
    assert str(e.value) == "注釈は50個までです。"


def test_unused_fields_are_not_validated():
    # hline は text / coords / fontSize / start / end / x を使わない
    s = parse_settings(
        raw_settings(annotations=[ann("hline", y=1, text="x" * 500, coords="zzz", fontSize="abc", start=object(), x=[1])])
    )
    assert s.annotations[0].kind == "hline"


def test_used_fields_are_validated():
    bad = [
        (ann("text", text="x" * 201, x=1, y=1), "注釈1の文字"),
        (ann("text", text="a", coords="zzz"), "注釈1の座標"),
        (ann("text", text="a", fontSize=0), "注釈1の文字の大きさ"),
        (ann("hline", y=1, lineWidth=0), "注釈1の線幅"),
        (ann("hline", y=1, lineStyle="zzz"), "注釈1の線種"),
        (ann("hline", y=1, color="notacolor"), "注釈1の色"),
        (ann("hspan", start=1, end=2, alpha=2), "注釈1の不透明度"),
        (ann("zzz"), "注釈1の種類"),
    ]
    for item, field_name in bad:
        with pytest.raises(UserError) as e:
            parse_settings(raw_settings(annotations=[item]))
        assert e.value.field == field_name, item


def test_axis_only_validated_when_secondary_is_used():
    parse_settings(raw_settings(annotations=[ann(y=1, axis="zzz")]))
    with pytest.raises(UserError):
        parse_settings(raw_settings([series(secondaryAxis=True)], annotations=[ann(y=1, axis="zzz")]))
    # Y を使わない種類は、第2Y軸を使っていても検証しない
    parse_settings(raw_settings([series(secondaryAxis=True)], annotations=[ann("vline", x=1, axis="zzz")]))


# ---------------------------------------------------------------- 描画計画（検査）


@pytest.mark.parametrize(
    "item, field_name",
    [
        (ann("hline"), "注釈1のY"),
        (ann("hline", y="abc"), "注釈1のY"),
        (ann("vline"), "注釈1のX"),
        (ann("vline", x="2026-01-01"), "注釈1のX"),  # 数値の X に日付
        (ann("hspan", start=1), "注釈1の終了"),
        (ann("vspan", end=1), "注釈1の開始"),
        (ann("text", text="  ", x=1, y=1), "注釈1の文字"),
        (ann("text", text="a", y=1), "注釈1のX"),
        (ann("text", text="a", x=1), "注釈1のY"),
        (ann("text", text="a", x=1, y="1,5"), "注釈1のY"),
    ],
)
def test_input_errors(item, field_name):
    with pytest.raises(UserError) as e:
        plan_of(annotations=[item])
    assert e.value.field == field_name


def test_datetime_x_errors():
    for item, field_name in [(ann("vline", x="1.5"), "注釈1のX"), (ann("vspan", start="2026-01-01", end="zzz"), "注釈1の終了")]:
        with pytest.raises(UserError) as e:
            plan_of(df=dates_frame(), series_list=[series(x=5)], annotations=[item])
        assert e.value.field == field_name and "日時" in str(e.value)


def test_log_axis_rejects_non_positive():
    def log_y(raw):
        raw["axes"]["y"]["scale"] = "log"

    with pytest.raises(UserError) as e:
        plan_of(annotations=[ann("hline", y=0)], mutate=log_y)
    assert e.value.field == "注釈1のY"
    with pytest.raises(UserError):
        plan_of(annotations=[ann("hspan", start=-1, end=3)], mutate=log_y)

    def log_x(raw):
        raw["axes"]["x"]["scale"] = "log"

    with pytest.raises(UserError):
        plan_of(df=frame().assign(t=lambda d: d["t"] + 1), annotations=[ann("vline", x=0)], mutate=log_x)
    # 図の中の割合は軸の種類に関係しない
    plan_of(annotations=[ann("text", text="a", coords="axes", x=0, y=0)], mutate=log_y)


def test_plan_values_by_axis_kind():
    p = plan_of(annotations=[ann("vline", x="2.5"), ann("hline", y="1e1")]).annotations
    assert (p[0].x, p[0].date, p[1].y) == (2.5, False, 10.0)
    p = plan_of(df=dates_frame(), series_list=[series(x=5)], annotations=[ann("vline", x="2026/01/03 12:00"), ann("vspan", start="2026-01-02", end="2026-01-04")]).annotations
    assert p[0].x == "2026-01-03 12:00:00" and p[0].date and (p[1].start, p[1].end) == ("2026-01-02", "2026-01-04")
    p = plan_of(df=text_frame(), series_list=[series(x=5)], annotations=[ann("vline", x="1.5")]).annotations
    assert p[0].x == 1.5 and not p[0].date


def test_hidden_secondary_axis_falls_back_to_ax():
    # 第2軸の系列に描ける点が無いと ax2 は作られない
    df = frame().assign(w=float("nan"))
    p = plan_of(df=df, series_list=[series(1), series(4, secondaryAxis=True)], annotations=[ann(y=1, axis="y2")])
    assert p.annotations[0].target == "ax"


def test_tick_estimate_includes_annotations():
    def step(raw):
        raw["axes"]["y"]["majorStep"] = 0.5

    plan_of(annotations=[ann(y=20)], mutate=step)
    with pytest.raises(UserError):
        plan_of(annotations=[ann(y=2000)], mutate=step)


# ---------------------------------------------------------------- 生成コードの図


def test_no_annotation_section_by_default(tmp_path):
    b = Built(tmp_path)
    assert "注釈" not in b.script.text and "# ==== 5. 軸" in b.script.text


def test_section_numbers_shift(tmp_path):
    b = build(tmp_path, [ann(y=15)])
    heads = [ln for ln in b.script.text.splitlines() if ln.startswith("# ==== ")]
    assert [h.split(" ")[2] for h in heads] == ["1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."]
    assert heads[4] == "# ==== 5. 注釈 ====" and heads[5].startswith("# ==== 6. 軸")


def test_hline_vline(tmp_path):
    b = build(tmp_path, [ann("hline", y=15, label="基準値", color="#FF0000", lineWidth=2), ann("vline", x=4, alpha=0.5)])
    assert 'ax.axhline(15.0, color="#FF0000", linewidth=2.0, linestyle="dashed", label="基準値")' in b.script.text
    assert 'ax.axvline(4.0, color="#000000", linewidth=1.0, linestyle="dashed", alpha=0.5)' in b.script.text

    def check(fig):
        ax = fig.axes[0]
        h = [ln for ln in ax.lines if ln.get_label() == "基準値"][0]
        assert list(h.get_ydata()) == [15.0, 15.0] and h.get_color() == "#FF0000" and h.get_linewidth() == 2.0
        assert "基準値" in [t.get_text() for t in ax.get_legend().get_texts()]

    summary = b.check(check)
    assert summary[0]["annotations"] == {"texts": 0, "hlines": 1, "vlines": 1, "hspans": 0, "vspans": 0}


def test_spans(tmp_path):
    b = build(tmp_path, [ann("hspan", start=20, end=12, label="帯"), ann("vspan", start=2, end=3, alpha=0.4)])
    assert "ax.axhspan(20.0, 12.0, color=\"#000000\", alpha=0.2, linewidth=0, label=\"帯\")" in b.script.text
    assert "ax.axvspan(2.0, 3.0, color=\"#000000\", alpha=0.4, linewidth=0)" in b.script.text

    def check(fig):
        ax = fig.axes[0]
        spans = [p for p in ax.patches]
        assert len(spans) == 2 and {round(p.get_alpha(), 2) for p in spans} == {0.2, 0.4}

    summary = b.check(check)
    assert summary[0]["annotations"]["hspans"] == 1 and summary[0]["annotations"]["vspans"] == 1


def test_text_data_and_axes(tmp_path):
    b = build(
        tmp_path,
        [ann("text", text="ピーク", x=3, y=16, fontSize=9), ann("text", text="左上", coords="axes", x=0.05, y=0.95, alpha=0.5)],
    )
    assert 'ax.text(3.0, 16.0, "ピーク", color="#000000", fontsize=9.0)' in b.script.text
    assert 'ax.text(0.05, 0.95, "左上", transform=ax.transAxes, color="#000000", fontsize=FONT_SIZE, alpha=0.5)' in b.script.text

    def check(fig):
        texts = fig.axes[0].texts
        assert [t.get_text() for t in texts] == ["ピーク", "左上"]
        assert texts[0].get_position() == (3.0, 16.0) and texts[1].get_position() == (0.05, 0.95)
        assert texts[0].get_fontsize() == 9.0

    summary = b.check(check)
    assert summary[0]["annotations"]["texts"] == 2


def test_datetime_x(tmp_path):
    b = build(
        tmp_path,
        [ann("vline", x="2026-01-04"), ann("vspan", start="2026-01-06", end="2026-01-08 12:00"), ann("text", text="t", x="2026-01-02", y=15)],
        df=dates_frame(),
        series_list=[series(x=5)],
    )
    assert 'ax.axvline(pd.Timestamp("2026-01-04"), ' in b.script.text
    assert 'pd.Timestamp("2026-01-08 12:00:00")' in b.script.text
    summary = b.check(lambda fig: None)
    assert summary[0]["annotations"]["vlines"] == 1 and summary[0]["annotations"]["vspans"] == 1


def test_text_x_position_is_category_index(tmp_path):
    b = build(tmp_path, [ann("vline", x=1.5)], df=text_frame(), series_list=[series(x=5)])

    def check(fig):
        line = [ln for ln in fig.axes[0].lines if ln.get_label().startswith("_child")][0]
        assert list(line.get_xdata()) == [1.5, 1.5]

    b.check(check)


def test_bar_annotations(tmp_path):
    b = build(tmp_path, [ann("hline", y=20), ann("vline", x=2)], plot_type="bar")
    summary = b.check(lambda fig: None)
    assert summary[0]["annotations"]["hlines"] == 1 and summary[0]["annotations"]["vlines"] == 1
    assert summary[0]["patches"] == 10  # 棒だけ（線は patches に入らない）


def test_secondary_axis_annotations(tmp_path):
    b = build(
        tmp_path,
        [ann("hline", y=50, axis="y2", label="第2"), ann("hspan", start=60, end=70, axis="y2"), ann("text", text="r", x=2, y=80, axis="y2"), ann("hline", y=15)],
        series_list=[series(1), series(4, secondaryAxis=True)],
    )
    assert "ax2.axhline(50.0" in b.script.text and "ax2.axhspan" in b.script.text and "ax2.text(2.0" in b.script.text
    assert "ax.axhline(15.0" in b.script.text

    def check(fig):
        ax, ax2 = fig.axes
        assert len(ax2.texts) == 1 and not ax.texts
        assert "第2" in [t.get_text() for t in ax.get_legend().get_texts()]  # まとめて凡例にする

    b.check(check)


def test_legend_with_only_annotation_label(tmp_path):
    b = build(tmp_path, [ann(y=15, label="基準")], series_list=[series(label="_hidden")])
    assert "凡例に出せるラベルが無い" not in b.script.text

    def check(fig):
        assert [t.get_text() for t in fig.axes[0].get_legend().get_texts()] == ["基準"]

    b.check(check)


def test_no_label_no_legend_still_holds(tmp_path):
    b = build(tmp_path, [ann(y=15)], series_list=[series(label="_hidden")])
    assert "凡例に出せるラベルが無い" in b.script.text


def test_annotations_do_not_change_existing_series_summary(tmp_path):
    base = Built(tmp_path).check(lambda fig: None)[0]
    with_ann = build(tmp_path, [ann(y=15, label="x"), ann("vspan", start=1, end=2)]).check(lambda fig: None)[0]
    for key in ("title", "xlabel", "ylabel", "errorbars", "collections", "markers", "alphas", "bands", "fitlines"):
        assert base[key] == with_ann[key], key


def test_injection(tmp_path):
    evil = 'a"\n__import__("os").system("x")  # \'\'\''
    b = build(tmp_path, [ann("text", text=evil, x=1, y=1), ann(y=2, label=evil), ann("vline", x=1, label="\\")])
    compile(b.script.text, "plot.py", "exec")
    assert "\n__import__" not in b.script.text
    with b.full() as run:
        assert evil in [t.get_text() for t in run.fig.axes[0].texts]
        assert evil in [t.get_text() for t in run.fig.axes[0].get_legend().get_texts()]


def test_date_text_cannot_inject():
    with pytest.raises(UserError):
        plan_of(df=dates_frame(), series_list=[series(x=5)], annotations=[ann("vline", x='2026-01-01"); __import__("os")#')])


def test_steps_registered(tmp_path):
    b = build(tmp_path, [ann(y=15), ann("vline", x=2)])
    fields = [s.field for s in b.script.steps]
    assert "注釈1" in fields and "注釈2" in fields
