"""Phase 5b: 近似曲線（G5）。係数・R² を numpy の直接計算と比べ、式の文字・表示先・エラーを検査する。"""
import numpy as np
import pandas as pd
import pytest

from mplgui.codegen import POLY_TEXT_FUNCTION
from mplgui.errors import UserError
from mplgui.settings import MAX_FITS, default_fit, parse_settings
from style_helpers import N, Built, frame, plan_of, raw_settings, series

pytestmark = pytest.mark.unit


def fit(**kw):
    d = {"series": "s1"}
    d.update(kw)
    return d


def quad_frame():
    t = np.arange(N, dtype=float)
    return pd.DataFrame({"t": t, "q": 0.5 * t**2 - 2 * t + 3 + np.sin(t) * 0.1, "w": 100 - 3 * t})


def fit_line(ax):
    return [ln for ln in ax.lines if "$R^2$" in ln.get_label() or ln.get_label() == "_fit"][0]


def poly_text(coef):
    ns: dict = {}
    exec("\n".join(POLY_TEXT_FUNCTION), ns)
    return ns["poly_text"](coef)


def r_squared(x, y, deg):
    p = np.polyfit(x, y, deg)
    resid = y - np.polyval(p, x)
    return p, 1 - np.sum(resid**2) / np.sum((y - y.mean()) ** 2)


# ---------------------------------------------------------------- poly_text


def test_poly_text_formats():
    assert poly_text([3.21, -0.5, 1.234]) == "y = 1.234x$^{2}$ - 0.5x + 3.21"
    assert poly_text([-1.0, 2.0]) == "y = 2x - 1"
    assert poly_text([5.0, -2.0]) == "y = -2x + 5"
    assert poly_text([0.0, 1.0, 0.0, -1.0]) == "y = -1x$^{3}$ + 0x$^{2}$ + 1x + 0"
    assert poly_text([1.23456789, 9.87654321]) == "y = 9.877x + 1.235"
    assert poly_text([1e-5, 1e6]) == "y = 1e+06x + 1e-05"


# ---------------------------------------------------------------- 設定


def test_default_fit_and_validation():
    assert default_fit()["model"] == "linear"
    s = parse_settings(raw_settings(fits=[fit(), fit(model="poly", degree=4, color="#112233")])).fits
    assert (s[0].degree, s[1].degree, s[1].color, s[0].line_style, s[0].show) == (1, 4, "#112233", "dashed", "legend")


def test_limit_of_20():
    parse_settings(raw_settings(fits=[fit()] * MAX_FITS))
    with pytest.raises(UserError):
        parse_settings(raw_settings(fits=[fit()] * (MAX_FITS + 1)))


@pytest.mark.parametrize(
    "item, field_name",
    [
        ({"series": "nope"}, "近似曲線1の系列"),
        (fit(model="zzz"), "近似曲線1のモデル"),
        (fit(model="poly", degree=1), "近似曲線1の次数"),
        (fit(model="poly", degree=7), "近似曲線1の次数"),
        (fit(model="poly", degree=2.5), "近似曲線1の次数"),
        (fit(show="zzz"), "近似曲線1の式の表示先"),
        (fit(color="notacolor"), "近似曲線1の色"),
        (fit(lineStyle="zzz"), "近似曲線1の線種"),
    ],
)
def test_validation_errors(item, field_name):
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings(fits=[item]))
    assert e.value.field == field_name


def test_degree_hidden_for_linear():
    s = parse_settings(raw_settings(fits=[fit(model="linear", degree="abc")])).fits[0]
    assert s.degree == 1


def test_bar_fits_are_not_validated_or_used(tmp_path):
    b = Built(tmp_path, plot_type="bar", fits=[{"series": "nope", "model": "zzz"}])
    assert not b.settings.fits and not b.plan.fits and "np.polynomial" not in b.script.text


# ---------------------------------------------------------------- 計算

def test_linear_fit_matches_numpy(tmp_path):
    b = Built(tmp_path, df=quad_frame(), series_list=[series(1)], fits=[fit()])
    assert "np.polynomial.Polynomial.fit(x[ok], y[ok], 1).convert()" in b.script.text
    df = quad_frame()
    coef_np, r2_np = r_squared(df["t"].to_numpy(), df["q"].to_numpy(), 1)

    def check(fig):
        line = fit_line(fig.axes[0])
        assert len(line.get_xdata()) == 200
        assert line.get_xdata()[0] == df["t"].min() and line.get_xdata()[-1] == df["t"].max()
        np.testing.assert_allclose(line.get_ydata(), np.polyval(coef_np, line.get_xdata()), atol=1e-8)
        assert line.get_label() == f"{b.plan.series[0].legend_label}の近似: {poly_text(coef_np[::-1])}（$R^2$ = {r2_np:.4f}）"

    b.check(check)


@pytest.mark.parametrize("degree", [2, 3, 6])
def test_poly_fit_matches_numpy(tmp_path, degree):
    df = quad_frame()
    b = Built(tmp_path, df=df, series_list=[series(1)], fits=[fit(model="poly", degree=degree)])
    coef_np, r2_np = r_squared(df["t"].to_numpy(), df["q"].to_numpy(), degree)

    def check(fig):
        line = fit_line(fig.axes[0])
        np.testing.assert_allclose(line.get_ydata(), np.polyval(coef_np, line.get_xdata()), rtol=1e-6, atol=1e-6)
        assert line.get_label().endswith(f"（$R^2$ = {r2_np:.4f}）")
        assert f"x$^{{{degree}}}$" in line.get_label()

    b.check(check)


def test_fit_with_large_x_values_is_stable(tmp_path):
    t = np.arange(N, dtype=float) + 1e9
    df = pd.DataFrame({"t": t, "v": 2 * (t - 1e9) + 5})
    b = Built(tmp_path, df=df, series_list=[series(1)], fits=[fit()])

    def check(fig):
        line = fit_line(fig.axes[0])
        np.testing.assert_allclose(line.get_ydata()[[0, -1]], [5.0, 2 * (N - 1) + 5.0], atol=1e-4)

    b.check(check)


def test_fit_uses_only_plotted_rows(tmp_path):
    df = quad_frame()
    df.loc[2, "q"] = np.nan
    b = Built(tmp_path, df=df, series_list=[series(1)], fits=[fit()])
    ok = df["q"].notna()
    coef_np, _ = r_squared(df["t"][ok].to_numpy(), df["q"][ok].to_numpy(), 1)
    b.check(lambda fig: np.testing.assert_allclose(fit_line(fig.axes[0]).get_ydata()[[0, -1]], np.polyval(coef_np, [0.0, N - 1.0]), atol=1e-8))


def test_scatter_fit(tmp_path):
    b = Built(tmp_path, df=quad_frame(), series_list=[series(1)], plot_type="scatter", fits=[fit()])
    summary = b.check(lambda fig: None)
    assert summary[0]["fitlines"] == 1 and summary[0]["collections"] == 1


# ---------------------------------------------------------------- 表示先と見た目


def test_show_legend(tmp_path):
    b = Built(tmp_path, df=quad_frame(), series_list=[series(1, label="温度")], fits=[fit()])

    def check(fig):
        labels = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
        assert labels[0] == "温度" and labels[1].startswith("温度の近似: y = ")

    summary = b.check(check)
    assert summary[0]["fitlines"] == 1 and summary[0]["fittexts"] == 0
    assert "def poly_text(coef):" in b.script.text
    assert b.script.text.index("def poly_text") < b.script.text.index("# ==== 1. データの読み込み")


def test_show_text_stacks_in_order(tmp_path):
    b = Built(
        tmp_path,
        df=quad_frame(),
        series_list=[series(1, label="A"), series(2, label="B")],
        fits=[fit(show="text"), fit(show="none"), {"series": "s2", "show": "text"}],
    )
    assert "ax.text(0.03, 0.97," in b.script.text and "ax.text(0.03, 0.9," in b.script.text

    def check(fig):
        ax = fig.axes[0]
        texts = ax.texts
        assert len(texts) == 2 and texts[0].get_position() == (0.03, 0.97) and texts[1].get_position() == (0.03, 0.9)
        assert texts[0].get_text().startswith("Aの近似: y = ") and texts[1].get_text().startswith("Bの近似: y = ")
        assert texts[0].get_color() == "#FF4B00"
        legend = [t.get_text() for t in ax.get_legend().get_texts()]
        assert legend == ["A", "B"]  # 図の中・出さない、は凡例に出ない

    summary = b.check(check)
    assert summary[0]["fitlines"] == 3 and summary[0]["fittexts"] == 2 and summary[0]["annotations"]["texts"] == 0


def test_show_none_has_no_poly_text_function(tmp_path):
    b = Built(tmp_path, df=quad_frame(), fits=[fit(show="none")])
    assert "poly_text" not in b.script.text
    summary = b.check(lambda fig: None)
    assert summary[0]["fitlines"] == 1


def test_color_and_style(tmp_path):
    b = Built(tmp_path, df=quad_frame(), series_list=[series(1, lineWidth=3, color="#005AFF")], fits=[fit(lineStyle="dotted"), fit(color="#00FF00")])

    def check(fig):
        lines = [ln for ln in fig.axes[0].lines if "$R^2$" in ln.get_label()]
        assert lines[0].get_color() == "#005AFF" and lines[0].get_linestyle() == ":" and lines[0].get_linewidth() == 3.0
        assert lines[1].get_color() == "#00FF00"

    b.check(check)


def test_secondary_axis_fit(tmp_path):
    b = Built(tmp_path, df=quad_frame(), series_list=[series(1), series(2, secondaryAxis=True)], fits=[{"series": "s2", "show": "text"}])
    assert "ax2.plot(x_fit" in b.script.text and "ax2.text(0.03, 0.97" in b.script.text

    def check(fig):
        ax, ax2 = fig.axes
        assert len(ax2.texts) == 1 and not ax.texts
        assert sum("$R^2$" in t for t in [ln.get_label() for ln in ax.lines]) == 0

    b.check(check)


def test_fit_is_drawn_right_after_its_series(tmp_path):
    b = Built(tmp_path, df=quad_frame(), series_list=[series(1), series(2)], fits=[fit()])
    text = b.script.text
    assert text.index("# 系列2") > text.index("# 近似曲線1") > text.index("# 系列1")


def test_default_x_is_row_number(tmp_path):
    b = Built(tmp_path, df=quad_frame(), series_list=[series(1, x="")], fits=[fit()])
    b.check(lambda fig: None)


def test_log_axis_fit_is_linear(tmp_path):
    def log_y(raw):
        raw["axes"]["y"]["scale"] = "log"

    b = Built(tmp_path, df=pd.DataFrame({"t": np.arange(5.0), "v": np.arange(5.0) * 3 + 1}), fits=[fit()], mutate=log_y)
    b.check(lambda fig: None)


# ---------------------------------------------------------------- エラー


def test_datetime_x_error():
    df = quad_frame().assign(d=pd.date_range("2026-01-01", periods=N).strftime("%Y-%m-%d"))
    with pytest.raises(UserError) as e:
        plan_of(df=df, series_list=[series(1, x=3)], fits=[fit()])
    assert e.value.field == "近似曲線1の系列" and "日時" in str(e.value)


def test_text_x_error():
    df = quad_frame().assign(c=[f"k{i}" for i in range(N)])
    with pytest.raises(UserError) as e:
        plan_of(df=df, series_list=[series(1, x=3)], fits=[fit()])
    assert e.value.field == "近似曲線1の系列" and "文字列" in str(e.value)


def test_not_enough_distinct_x():
    df = pd.DataFrame({"t": [1.0, 1.0, 2.0, 2.0], "v": [1.0, 2.0, 3.0, 4.0]})
    plan_of(df=df, fits=[fit()])
    with pytest.raises(UserError) as e:
        plan_of(df=df, fits=[fit(model="poly", degree=2)])
    assert e.value.field == "近似曲線1の系列" and "3個以上" in str(e.value)


def test_not_enough_points_after_dropping_missing():
    df = pd.DataFrame({"t": [1.0, 2.0, 3.0], "v": [1.0, np.nan, np.nan]})
    with pytest.raises(UserError):
        plan_of(df=df, fits=[fit()])


def test_constant_y_error():
    df = pd.DataFrame({"t": np.arange(5.0), "v": np.full(5, 3.0)})
    with pytest.raises(UserError) as e:
        plan_of(df=df, fits=[fit()])
    assert "すべて同じ" in str(e.value)


def test_series_without_points_error():
    df = pd.DataFrame({"t": np.arange(5.0), "v": np.arange(5.0), "w": np.nan})
    with pytest.raises(UserError) as e:
        plan_of(df=df, series_list=[series(1), series(2)], fits=[{"series": "s2"}])
    assert e.value.field == "近似曲線1の系列"


# ---------------------------------------------------------------- 安全性


def test_series_name_cannot_inject(tmp_path):
    evil = 'x"\n__import__("os").system("x")  # \'\'\''
    b = Built(tmp_path, df=quad_frame(), series_list=[series(1, label=evil)], fits=[fit(), fit(show="text")])
    compile(b.script.text, "plot.py", "exec")
    assert "\n__import__" not in b.script.text
    with b.full() as run:
        labels = [ln.get_label() for ln in run.fig.axes[0].lines]
        assert any(label.startswith(evil + "の近似: ") for label in labels)


def test_column_name_comment_cannot_inject(tmp_path):
    df = quad_frame().rename(columns={"q": 'q"\n__import__("os")'})
    b = Built(tmp_path, df=df, series_list=[series(1)], fits=[fit()])
    compile(b.script.text, "plot.py", "exec")
    assert "\n__import__" not in b.script.text


def test_uses_only_numpy_in_generated_code(tmp_path):
    b = Built(tmp_path, df=quad_frame(), fits=[fit()])
    assert "polyfit" not in b.script.text and "scipy" not in b.script.text


# ---------------------------------------------------------------- 任意の式（G10）

from scipy.optimize import curve_fit  # noqa: E402

from mplgui.api import _step_error  # noqa: E402
from mplgui.runner import ScriptError, run_script  # noqa: E402


def custom(expr="a * exp(-b * x) + c", **kw):
    d = {"series": "s1", "model": "custom", "expr": expr}
    d.update(kw)
    return d


def decay_frame():
    t = np.linspace(0, 5, 30)
    return pd.DataFrame({"t": t, "y": 3.0 * np.exp(-0.8 * t) + 0.5 + 0.01 * np.cos(7 * t)})


def logistic_frame():
    t = np.linspace(-5, 5, 40)
    return pd.DataFrame({"t": t, "y": 4.0 / (1 + np.exp(-1.5 * (t - 0.5))) + 0.02 * np.sin(5 * t)})


def test_custom_defaults_and_settings():
    d = default_fit()
    assert d["expr"] == "" and d["initial"] == {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1}
    f = parse_settings(raw_settings(fits=[custom(initial={"a": "2.5", "b": 3, "c": 7})])).fits[0]
    assert f.model == "custom" and f.params == ("a", "b", "c") and f.initial == (2.5, 3.0, 7.0)
    # 使うパラメータだけ。式の中の順に関わらず a〜e の順
    f = parse_settings(raw_settings(fits=[custom("c * x + a", initial={"a": 4, "c": 9})])).fits[0]
    assert f.params == ("a", "c") and f.initial == (4.0, 9.0)
    # 空欄・欠けは 1
    f = parse_settings(raw_settings(fits=[custom("a * x", initial={"a": ""})])).fits[0]
    assert f.initial == (1.0,)


@pytest.mark.parametrize(
    "item, field_name, text",
    [
        (custom(""), "近似曲線1の式", "近似曲線1の式を入力してください。"),
        (custom("   "), "近似曲線1の式", "近似曲線1の式を入力してください。"),
        (custom("a * (x"), "近似曲線1の式", "近似曲線1の式: "),
        (custom("a * " + "x" * 300), "近似曲線1の式", "近似曲線1の式: "),
        (custom("a * b"), "近似曲線1の式", "x を含めて"),
        (custom("x + 1"), "近似曲線1の式", "パラメータ"),
        (custom("max(x) * a"), "近似曲線1の式", "近似曲線1の式: "),
        (custom("a * x", initial={"a": "abc"}), "近似曲線1の初期値（a）", "初期値（a）"),
        (custom("a * x", initial={"a": float("inf")}), "近似曲線1の初期値（a）", "初期値（a）"),
        (custom("a * x + b", initial={"a": 1, "b": None if False else "zz"}), "近似曲線1の初期値（b）", "初期値（b）"),
    ],
)
def test_custom_validation_errors(item, field_name, text):
    with pytest.raises(UserError) as e:
        parse_settings(raw_settings(fits=[item]))
    assert e.value.field == field_name and text in str(e.value)


def test_custom_fields_hidden_for_other_models():
    # expr / initial は custom 以外では検証せず使わない。custom の degree も使わない
    for model in ("linear", "poly"):
        f = parse_settings(raw_settings(fits=[fit(model=model, expr="((", initial={"a": "zz"})])).fits[0]
        assert f.expr == "" and f.expr_node is None and f.params == ()
    parse_settings(raw_settings(fits=[custom(degree="abc")]))
    # 使っていないパラメータの初期値は検証しない
    parse_settings(raw_settings(fits=[custom("a * x", initial={"a": 1, "b": "zz"})]))


def test_custom_exponential_matches_scipy(tmp_path):
    df = decay_frame()
    b = Built(tmp_path, df=df, series_list=[series(1, label="減衰")], fits=[custom(initial={"a": 1, "b": 1, "c": 1})])
    assert "from scipy.optimize import curve_fit" in b.script.text
    assert "scipy" in b.script.text.split("\n")[2]

    def model(x, a, b, c):
        return a * np.exp(-b * x) + c

    x, y = df["t"].to_numpy(), df["y"].to_numpy()
    expect, _ = curve_fit(model, x, y, p0=[1.0, 1.0, 1.0], maxfev=10000)
    r2 = 1 - np.sum((y - model(x, *expect)) ** 2) / np.sum((y - y.mean()) ** 2)

    def check(fig):
        ax = fig.axes[0]
        line = fit_line(ax)
        assert line.get_label().startswith("減衰の近似: y = a*exp(-b*x) + c（a = ")
        assert line.get_label().endswith(f"、$R^2$ = {r2:.4f}）")
        xs, ys = line.get_data()
        assert len(xs) == 200 and xs[0] == x.min() and xs[-1] == x.max()
        np.testing.assert_allclose(ys, model(xs, *expect), rtol=1e-6)
        for name, value in zip("abc", expect):
            assert f"{name} = {value:.4g}" in line.get_label()

    summary = b.check(check)
    assert summary[0]["fitlines"] == 1


def test_custom_logistic_matches_scipy(tmp_path):
    df = logistic_frame()
    b = Built(tmp_path, df=df, fits=[custom("a / (1 + exp(-b * (x - c)))", initial={"a": 3, "b": 1, "c": 0})])

    def model(x, a, b, c):
        return a / (1 + np.exp(-b * (x - c)))

    x, y = df["t"].to_numpy(), df["y"].to_numpy()
    expect, _ = curve_fit(model, x, y, p0=[3.0, 1.0, 0.0], maxfev=10000)

    def check(fig):
        xs, ys = fit_line(fig.axes[0]).get_data()
        np.testing.assert_allclose(ys, model(xs, *expect), rtol=1e-6)

    b.check(check)
    assert "p0=[3.0, 1.0, 0.0]" in b.script.text and "def fit_model_1(x, a, b, c):" in b.script.text


def test_custom_generated_snippet(tmp_path):
    b = Built(tmp_path, df=decay_frame(), fits=[custom()])
    text = b.script.text
    assert "def fit_model_1(x, a, b, c):  # 近似曲線1の式: a * exp(-b * x) + c" in text
    assert "    return a * np.exp(-b * x) + c" in text or "np.exp(" in text
    assert "fit_params, _ = curve_fit(fit_model_1, x[ok], y[ok], p0=[1.0, 1.0, 1.0], maxfev=10000)" in text
    assert "fit_model_1(x[ok], *fit_params)" in text and "np.isfinite(fit_y)" in text


def test_custom_show_variants(tmp_path):
    df = decay_frame()
    b = Built(
        tmp_path, df=df, series_list=[series(1, label="A")],
        fits=[custom(show="text"), custom("a * x + b", show="none"), custom("a * x + b")],
    )

    def check(fig):
        ax = fig.axes[0]
        assert len(ax.texts) == 1 and ax.texts[0].get_position() == (0.03, 0.97)
        assert ax.texts[0].get_text().startswith("Aの近似: y = a*exp(-b*x) + c（")
        legend = [t.get_text() for t in ax.get_legend().get_texts()]
        assert len(legend) == 2 and legend[0] == "A" and legend[1].startswith("Aの近似: y = a*x + b（a = ")
        assert sum(ln.get_label() == "_fit" for ln in ax.lines) == 2  # show=text と none

    summary = b.check(check)
    assert summary[0]["fitlines"] == 3 and summary[0]["fittexts"] == 1
    assert "poly_text" not in b.script.text  # 任意の式だけなら poly_text は要らない


def test_custom_mixed_with_poly(tmp_path):
    b = Built(tmp_path, df=decay_frame(), fits=[custom(), fit(model="poly", degree=2)])
    assert "def poly_text(coef):" in b.script.text and "curve_fit" in b.script.text
    assert b.check(lambda fig: None)[0]["fitlines"] == 2


def test_custom_secondary_axis(tmp_path):
    df = decay_frame().assign(w=lambda d: 2 * d["y"] + 1)
    b = Built(tmp_path, df=df, series_list=[series(1), series(2, secondaryAxis=True)], fits=[{**custom(show="text"), "series": "s2"}])
    assert "ax2.plot(x_fit, fit_model_1(x_fit, *fit_params)" in b.script.text and "ax2.text(0.03, 0.97" in b.script.text

    def check(fig):
        ax, ax2 = fig.axes
        assert len(ax2.texts) == 1 and not ax.texts

    b.check(check)


def test_custom_fit_number_names_function(tmp_path):
    b = Built(tmp_path, df=decay_frame(), fits=[fit(), custom("a * x + b")])
    assert "def fit_model_2(x, a, b):" in b.script.text and "fit_model_1" not in b.script.text
    assert b.check(lambda fig: None)[0]["fitlines"] == 2


def test_scipy_not_imported_without_custom(tmp_path):
    for fits in ([], [fit()], [fit(model="poly", degree=2, show="text")]):
        b = Built(tmp_path, df=decay_frame(), fits=fits)
        assert "scipy" not in b.script.text and "curve_fit" not in b.script.text
    b = Built(tmp_path, df=decay_frame(), fits=[custom()], plot_type="bar")  # 棒グラフでは使わない
    assert "scipy" not in b.script.text


@pytest.mark.filterwarnings("ignore:invalid value encountered in log:RuntimeWarning")
@pytest.mark.filterwarnings("ignore:Covariance of the parameters could not be estimated")
def test_custom_non_finite_initial_maps_to_step_message(tmp_path):
    t = np.arange(10.0)
    df = pd.DataFrame({"t": t, "y": 2 * t + 1})
    b = Built(tmp_path, df=df, fits=[custom("log(a) * x + b", initial={"a": -1, "b": 1})])
    with pytest.raises(ScriptError) as e:
        with run_script(b.script.text, cwd=tmp_path):
            pass
    mapped = _step_error(b.script, e.value)
    assert mapped.args[0] == "近似曲線1: 式を当てはめられませんでした。初期値を変えてみてください。"
    assert mapped.field == "近似曲線1の初期値"


def test_custom_no_convergence_maps_to_step_message(tmp_path):
    b = Built(tmp_path, df=decay_frame(), fits=[custom()])

    def fail(*args, **kwargs):  # 収束しないときの curve_fit と同じ例外（plot.py の外で起こす）
        raise RuntimeError("Optimal parameters not found: The maximum number of function evaluations is exceeded.")

    text = b.script.text.replace("from scipy.optimize import curve_fit", "curve_fit = fail")
    assert text.count("\n") == b.script.text.count("\n")
    with pytest.raises(ScriptError) as e:
        with run_script(text, injected={"fail": fail}, cwd=tmp_path):
            pass
    mapped = _step_error(b.script, e.value)
    assert mapped.args[0] == "近似曲線1: 式を当てはめられませんでした。初期値を変えてみてください。"
    assert mapped.field == "近似曲線1の初期値"


def test_custom_not_enough_distinct_x():
    df = pd.DataFrame({"t": [1.0, 1.0, 2.0, 2.0, 3.0, 3.0], "v": [1.0, 2.0, 3.0, 4.0, 5.0, 7.0]})
    plan_of(df=df, fits=[custom("a * x + b")])  # 3 個 > 2 個
    with pytest.raises(UserError) as e:
        plan_of(df=df, fits=[custom("a * x**2 + b * x + c")])  # 3 個 <= 3 個
    assert e.value.field == "近似曲線1の系列" and "近似曲線1: " in str(e.value) and "4個以上" in str(e.value)


def test_custom_data_errors():
    df = decay_frame().assign(d=pd.date_range("2026-01-01", periods=30).strftime("%Y-%m-%d"), c=[f"k{i}" for i in range(30)])
    for x, word in ((2, "日時"), (3, "文字列")):
        with pytest.raises(UserError) as e:
            plan_of(df=df, series_list=[series(1, x=x)], fits=[custom()])
        assert e.value.field == "近似曲線1の系列" and word in str(e.value)
    flat = pd.DataFrame({"t": np.arange(5.0), "v": np.full(5, 3.0)})
    with pytest.raises(UserError) as e:
        plan_of(df=flat, fits=[custom("a * x + b")])
    assert "すべて同じ" in str(e.value)


def test_custom_injection(tmp_path):
    evil = 'x"\n__import__("os").system("x")  # \'\'\''
    b = Built(tmp_path, df=decay_frame(), series_list=[series(1, label=evil)], fits=[custom(), custom("a * x + b", show="text")])
    compile(b.script.text, "plot.py", "exec")
    assert "\n__import__" not in b.script.text
    with b.full() as run:
        assert any(ln.get_label().startswith(evil + "の近似: ") for ln in run.fig.axes[0].lines)
    # 式の文字列に命令を入れても、パーサが拒否する
    for bad in ('a * __import__("os")', "a * x; import os", "a * x\nimport os", "a.__class__ * x", "a * x  # \n"):
        with pytest.raises(UserError):
            parse_settings(raw_settings(fits=[custom(bad)]))


def test_custom_expression_only_in_comment(tmp_path):
    b = Built(tmp_path, df=decay_frame(), fits=[custom("a   *   exp( -b*x )+c")])
    lines = [ln for ln in b.script.text.split("\n") if "a   *   exp( -b*x )+c" in ln]
    assert len(lines) == 1 and lines[0].startswith("def fit_model_1(") and "# 近似曲線1の式: " in lines[0]
    assert "\n" not in lines[0]
    # 木から整えた式だけがコードとラベルに入る
    assert "a*exp(-b*x) + c" in b.script.text
