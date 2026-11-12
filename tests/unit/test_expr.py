"""expr.py（式で新しい列）の単体テスト。"""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_series_equal

from mplgui import expr
from mplgui.expr import ExprError, evaluate, parse, to_code

INDEX = pd.Index(range(10, 18))
C0 = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8], index=INDEX)
C1 = pd.Series([2.0, 0, -1, 4, np.nan, 6, -7, 8], index=INDEX)
C2 = pd.Series([0.5, 1.5, np.nan, 2.5, 3.5, 4.5, 5.5, 6.5], index=INDEX)
COLS = {0: C0, 1: C0, 2: C1, 3: C2}  # [1] = C0, [2] = C1, [3] = C2（A は [0]）


def run(text, columns=COLS, index=INDEX):
    return evaluate(parse(text), columns, index)


def values(text):
    return run(text)[0]


def code_of(text):
    return to_code(parse(text), lambda i: f"col{i}", repr)


def via_code(text):
    ns = {"np": np, "pd": pd, **{f"col{i}": s for i, s in COLS.items()}}
    with np.errstate(all="ignore"):
        r = eval(code_of(text), ns)  # テスト内だけで使う
    arr = np.full(len(INDEX), float(r)) if np.isscalar(r) or np.ndim(r) == 0 else r.to_numpy(float)
    arr = np.where(np.isinf(arr), np.nan, arr)
    return pd.Series(arr, index=INDEX, dtype=float)


def err(text):
    with pytest.raises(ExprError) as e:
        parse(text)
    return e.value


# ---- 構文 ----


def test_precedence_and_associativity():
    assert values("-2**2 + [1]*0").iloc[0] == -4
    assert values("2**3**2 + [1]*0").iloc[0] == 512
    assert values("2^-1 + [1]*0").iloc[0] == 0.5
    assert_series_equal(values("[1]-[2]-[3]"), C0 - C1 - C2, check_names=False)
    assert_series_equal(values("[1]/[2]/[3]").fillna(-9), (C0 / C1 / C2).replace([np.inf, -np.inf], np.nan).fillna(-9), check_names=False)
    assert_series_equal(values("2 + [1] * 3"), 2 + C0 * 3, check_names=False)
    assert_series_equal(values("([0] + 1) * 2"), (C0 + 1) * 2, check_names=False)
    assert_series_equal(values("+[1]"), C0, check_names=False)


@pytest.mark.parametrize(
    "letters, index", [("A", 0), ("Z", 25), ("AA", 26), ("AZ", 51), ("BA", 52), ("ZZZ", 18277)]
)
def test_excel_letters(letters, index):
    node = parse(f"{letters} + 1")
    assert expr.column_indices(node) == (index,)


def test_fullwidth_input():
    node = parse("（Ａ　＋　２）　＊　ｍａｘ（［２］）")
    assert expr.column_refs(node) == ((0, 2), (2, 15))
    assert_series_equal(values("［１］　＋　１"), C0 + 1, check_names=False)


def test_whitespace_and_bracket_spaces():
    assert parse("[ 3 ]").index == 3
    assert expr.column_indices(parse("  [ 3 ]\t+ B ")) == (1, 3)


def test_column_refs_positions_in_text_order():
    node = parse("[5] + max(A) * [2]")
    assert expr.column_refs(node) == ((5, 1), (0, 11), (2, 16))
    assert expr.column_indices(node) == (0, 2, 5)


def test_is_series():
    assert expr.is_series(parse("[1] + 1"))
    assert expr.is_series(parse("[1] - max([1])"))
    assert not expr.is_series(parse("max([1])"))
    assert not expr.is_series(parse("max([1]) / 2"))
    assert expr.is_series(parse("diff([1])"))


# ---- 関数 ----


@pytest.mark.parametrize("name", expr.ELEMENTWISE)
def test_elementwise(name):
    with np.errstate(all="ignore"):
        expected = getattr(np, name)(C1)
    expected = expected.replace([np.inf, -np.inf], np.nan)
    assert_series_equal(values(f"{name}([2])"), expected, check_names=False)


def test_aggregates_against_pandas():
    for name, ref in [
        ("min", C1.min()), ("max", C1.max()), ("mean", C1.mean()),
        ("median", C1.median()), ("std", C1.std()),
        ("first", C1.iloc[0]), ("last", C1.iloc[-1]),
    ]:
        r = values(f"{name}([2])")
        assert (r == ref).all(), name
    nan_head = pd.Series([np.nan, np.nan, 3.0, np.nan], index=pd.RangeIndex(4))
    cols = {0: nan_head}
    assert run("first(A)", cols, nan_head.index)[0].eq(3.0).all()
    assert run("last(A)", cols, nan_head.index)[0].eq(3.0).all()
    all_nan = {0: pd.Series([np.nan] * 3)}
    r, count = run("max(A)", all_nan, all_nan[0].index)
    assert r.isna().all() and count == 0


def test_aggregates_return_numpy_floats():
    s = pd.Series([1.0, 2.0, np.nan])
    nan = pd.Series([np.nan, np.nan])
    for name, fn in expr._AGG_METHODS.items():
        assert isinstance(fn(s), np.float64), name
        assert isinstance(fn(nan), np.float64), name
    # 生成コードでも 0 での割り算で例外にならない（全部欠損の mean は pandas では Python の float）
    with np.errstate(all="ignore"):
        assert np.isnan(eval(code_of("mean([1]) / 0"), {"np": np, "col1": nan}))


def test_series_funcs():
    assert_series_equal(values("rolling_mean([3], 3)"), C2.rolling(3, center=True).mean(), check_names=False)
    assert_series_equal(values("diff([2])"), C1.diff(), check_names=False)
    assert_series_equal(values("cumsum([3])"), C2.cumsum(), check_names=False)
    assert_series_equal(values("[1] - rolling_mean([1], 1)"), C0 - C0.rolling(1, center=True).mean(), check_names=False)


CORPUS = [
    "[1]", "-[1]", "[1] + [2]", "[1] - [2]", "[1] * [2]", "[1] / [2]", "[1] ** 2", "[1] ^ 0.5",
    "([1] + [2]) * [3]", "[1] + [2] * [3]", "[1] - ([2] - [3])", "[1] / ([2] / [3])",
    "([1] * [2]) ** [3]", "[1] ** [2] ** [3]", "([1] ** [2]) ** [3]", "-[1] ** 2", "(-[1]) ** 2",
    "2 ** -[1]", "-([1] + 1)", "-(-[1])", "(-2) ** [1]", "-2 * [1]", "[1] / -2",
    "abs([2])", "sqrt([2])", "log([2]) + 1", "log10([1]) * 2", "exp([1] / 10)", "sin([1]) ** 2 + cos([1]) ** 2",
    "tan([3])", "abs([2] - 3) / sqrt([1])", "max([1])", "max([1]) / 0", "[1] - mean([1])",
    "([1] - min([1])) / (max([1]) - min([1]))", "std([2]) * [1]", "median([3]) - [3]", "first([1]) / last([1])",
    "-max([2])", "max([2]) ** 2", "(max([1]) - 1) ** [1]", "rolling_mean([1], 3) * 2", "diff([1]) / [2]",
    "cumsum([1]) - cumsum([3])", "1 / ([2] - [2])", "log([2]) / [1]", "[1] * (1 + 2) / 4", "A + B * C", "1e3 * [1] + .5",
    "sqrt(max([1]) - 100)",
]


@pytest.mark.parametrize("text", CORPUS)
def test_evaluate_matches_generated_code(text):
    assert_series_equal(values(text), via_code(text), check_names=False)


def test_code_is_minimal_and_precedence_aware():
    assert code_of("[1] + [2] * [3]") == "col1 + col2 * col3"
    assert code_of("([1] + [2]) * [3]") == "(col1 + col2) * col3"
    assert code_of("[1] - ([2] - [3])") == "col1 - (col2 - col3)"
    assert code_of("[1] ** [2] ** [3]") == "col1 ** col2 ** col3"
    assert code_of("([1] ** [2]) ** [3]") == "(col1 ** col2) ** col3"
    assert code_of("-[1] ** 2") == "-col1 ** 2.0"
    assert code_of("(-[1]) ** 2") == "(-col1) ** 2.0"
    assert code_of("max([1]) - [1]") == "np.float64(col1.max()) - col1"
    assert code_of("rolling_mean([1] + 1, 5)") == "(col1 + 1.0).rolling(5, center=True).mean()"


def test_injection_free_code():
    node = parse("[3] * 1.5 + abs(  [4]  ) - max(B)")
    code = to_code(node, lambda i: f"COL{i}", lambda v: "NUM")
    assert code == "COL3 * NUM + np.abs(COL4) - np.float64(COL1.max())"


@pytest.mark.parametrize(
    "text",
    ["__import__('os')", "[1]; import os", "[1]\n+1", "'a'", '"a"', "[1] \\ 2", "[1].real", "[1] if 1 else 2", "x = 1", "[1] % 2", "[1] // 2", "lambda"],
)
def test_injection_inputs_rejected(text):
    with pytest.raises(ExprError):
        parse(text)


# ---- 定数の畳み込み ----


def test_constant_folding():
    node = parse("[1] * (1 + 2)")
    assert isinstance(node.right, expr.Number) and node.right.value == 3.0
    assert code_of("[1] * (1 + 2)") == "col1 * 3.0"
    assert code_of("sqrt(16) * [1]") == "4.0 * col1"
    assert code_of("2 ** 3 ** 2 + [1]") == "512.0 + col1"


@pytest.mark.parametrize("text", ["[1] + 1/0", "[1] + sqrt(-1)", "[1] * (-8) ** 0.5", "[1] + log(0)", "1e999 + [1]", "[1] + exp(1000)"])
def test_non_finite_constants_rejected(text):
    e = err(text)
    assert "計算できない定数" in e.message and e.position is not None


# ---- エラー ----


@pytest.mark.parametrize(
    "text, pos, msg",
    [
        ("[1] # 2", 5, "「#」は使えません"),
        ("([1] + 2", 1, "閉じ括弧「)」が足りません"),
        ("max([1]", 4, "閉じ括弧「)」が足りません"),
        ("[1] + 2)", 8, "「)」に対応する「(」がありません"),
        (")[1]", 1, "「)」に対応する「(」がありません"),
        ("[1] *", 5, "「*」の後に値がありません"),
        ("[1] + * 2", 5, "「+」の後に値がありません"),
        ("* [1]", 1, "「*」の前に値がありません"),
        ("[1] [2]", 5, "値と値の間に演算子（+ - * / など）がありません"),
        ("2[1]", 2, "値と値の間に演算子"),
        ("[1] 2", 5, "値と値の間に演算子"),
        ("[a]", 1, "列は [0] のように、角括弧の中に番号を書いてください"),
        ("[]", 1, "列は [0] のように"),
        ("[1", 1, "列は [0] のように"),
        ("foo + [1]", 1, "「foo」は使えません"),
        ("foo([1])", 1, "使える関数: abs, sqrt"),
        ("max + [1]", 1, "「max」は関数です"),
        ("MAX([1])", 1, "関数名は小文字で書いてください（max）"),
        ("ABCD", 1, "「ABCD」は使えません"),
        ("sqrt([1], 2)", 1, "sqrt には値を1つ指定してください"),
        ("sqrt()", 1, "sqrt には値を1つ指定してください"),
        ("rolling_mean([1])", 1, "rolling_mean には「式, 窓の幅」の2つを指定してください"),
        ("max([1], [2])", 1, "max には値を1つ指定してください"),
        ("max(1)", 1, "max の中には列を含めてください"),
        ("max(max([1]))", 1, "max の中には列を含めてください"),
        ("diff(2 + 3)", 1, "diff の中には列を含めてください"),
        ("rolling_mean([1], 0)", 19, "rolling_mean の窓の幅は 1〜1000 の整数で指定してください"),
        ("rolling_mean([1], 1001)", 19, "窓の幅は 1〜1000"),
        ("rolling_mean([1], 2.5)", 19, "窓の幅は 1〜1000"),
        ("rolling_mean([1], -1)", 19, "窓の幅は 1〜1000"),
        ("rolling_mean([1], [2])", 19, "窓の幅は 1〜1000"),
        ("1 + 2", None, "式に列"),
        ("2 * 3", None, "式に列"),
        ("", None, "式を入力してください"),
        ("   ", None, "式を入力してください"),
        ("[1] + (2, 3)", 9, "「,」は関数の引数の区切りにだけ使えます"),
    ],
)
def test_error_messages(text, pos, msg):
    e = err(text)
    assert msg in e.message
    assert e.position == pos


def test_error_str_includes_position():
    e = err("[1] # 2")
    assert str(e) == "5文字目: 「#」は使えません"
    assert str(err("")) == "式を入力してください"


def test_limits():
    e = err("1" * 201)
    assert e.message == "式は200文字までです" and e.position is None
    parse("1+" * 98 + "[1]")  # 200 文字ちょうど以下
    assert err("(" * 31 + "[1]" + ")" * 31).message.startswith("入れ子が深すぎます")
    parse("(" * 30 + "[1]" + ")" * 30)
    assert err("-" * 31 + "[1]").message.startswith("入れ子が深すぎます")
    assert err("[1]" + "^2" * 40).message.startswith("入れ子が深すぎます")
    assert err("abs(" * 31 + "[1]" + ")" * 31).message == "入れ子が深すぎます（30 段まで）"
    parse("rolling_mean([1], 1)")
    parse("rolling_mean([1], 1000)")


def test_no_recursion_error_on_long_inputs():
    for text in ["-" * 200, "(" * 200, "[1]" + "**2" * 66, "abs(" * 50, "[1]" + "+[1]" * 49]:
        try:
            parse(text)
        except ExprError:
            pass


# ---- スカラーだけの式 ----


def test_scalar_only_expressions():
    r, count = run("max([1])")
    assert r.eq(8.0).all() and len(r) == len(INDEX) and count == 0
    r, count = run("max([1]) / 0")
    assert r.isna().all() and count == len(INDEX)
    r, count = run("max([1]) / 2 + min([1])")
    assert r.eq(5.0).all()
    assert r.index.equals(INDEX)


# ---- invalid_count ----


def test_invalid_count_division():
    r, count = run("[1] / [2]")
    assert count == 1 and r.isna().sum() == 2  # 0 での割り算 1 行と、NaN 入力 1 行
    assert np.isnan(r.iloc[1]) and np.isnan(r.iloc[4])


def test_invalid_count_sqrt_and_log():
    assert run("sqrt([2])")[1] == 2  # -1 と -7
    assert run("log([2])")[1] == 3  # 0, -1, -7（0 は -inf）


def test_invalid_count_edges_and_nan_not_counted():
    assert run("rolling_mean([1], 3)")[1] == 0
    assert run("diff([1])")[1] == 0
    assert run("cumsum([2])")[1] == 0
    c = {0: pd.Series([np.nan, 1.0, 4.0], index=pd.RangeIndex(3))}
    r, count = run("sqrt(A)", c, c[0].index)
    assert count == 0 and r.isna().sum() == 1


def test_invalid_count_counts_only_final_nan():
    # 途中の inf は最終的に NaN になる行だけ数える
    r, count = run("1 / ([2] - [2]) * 0")
    assert count == len(INDEX) - 1 or count == 7
    assert r.isna().all()


def test_invalid_count_aggregate():
    c = {0: pd.Series([5.0], index=pd.RangeIndex(1))}
    r, count = run("std(A)", c, c[0].index)  # 1 行だと標準偏差は NaN
    assert count == 1 and r.isna().all()
    r, count = run("max([2]) + 1")
    assert count == 0


# ---- 近似の式（モデル。G10） -------------------------------------------------

MODELS = [
    "a*exp(-b*x) + c",
    "a*x^2 + b*x + c",
    "a/(1 + exp(-b*(x - c)))",
    "a*sin(b*x + c) + d",
    "-a^2 * x",
    "a^b^c + x",
    "(a + b)*(x - e)/2",
    "a*x**-b + 1e-3",
    "a - (b - x)",
    "a/(b*x)",
    "log(abs(x) + 1)*a + sqrt(b**2)",
]


def merr(text):
    with pytest.raises(ExprError) as e:
        expr.parse_model(text)
    return e.value


def mcode(text):
    return expr.model_to_code(expr.parse_model(text), repr)


def mrun(text, x, **p):
    ns = {"np": np, "x": x, **{k: np.float64(v) for k, v in p.items()}}
    with np.errstate(all="ignore"):
        return eval(mcode(text), ns)  # テスト内だけで使う


@pytest.mark.parametrize("text", MODELS)
def test_model_accepted(text):
    node = expr.parse_model(text)
    assert expr.model_params(node)


def test_model_params_order_and_dedup():
    assert expr.model_params(expr.parse_model("c*x + a*x + c")) == ("a", "c")
    assert expr.model_params(expr.parse_model("e*x + d + b")) == ("b", "d", "e")


def test_model_e_vs_number_vs_exp():
    n = expr.parse_model("1e-3*x + e")
    assert expr.model_params(n) == ("e",)
    assert expr.model_to_text(n) == "0.001*x + e"
    n = expr.parse_model("2.5E3*x + a")
    assert expr.model_to_text(n) == "2500*x + a"
    n = expr.parse_model("exp(x) + e")
    assert expr.model_params(n) == ("e",)
    assert expr.model_to_code(n, repr) == "np.exp(x) + e"


def test_model_errors_with_positions():
    e = merr("a*[0]*x")
    assert (e.message, e.position) == (
        "近似の式では列は使えません（変数は x、パラメータは a〜e です）。",
        3,
    )
    e = merr("a*A + x")
    assert e.position == 3 and "列は使えません" in e.message
    assert merr("a*BC*x").position == 3
    for name in ("min", "max", "mean", "median", "std", "first", "last"):
        e = merr(f"a*{name}(x)")
        assert e.position == 3 and "近似の式では使えません" in e.message and "sqrt" in e.message
    for name in ("rolling_mean", "diff", "cumsum"):
        e = merr(f"{name}(x)*a")
        assert e.position == 1 and "近似の式では使えません" in e.message
    assert merr("a + 1").message == "式に x を含めてください。"
    assert merr("a*2*3").message == "式に x を含めてください。"
    assert merr("x + 1").message == "式にパラメータ（a〜e）を1つ以上含めてください。"
    e = merr("a*y + x")
    assert e.position == 3 and "使える名前は x と a〜e です" in e.message
    assert merr("f*x").position == 1
    assert merr("a*x + k").position == 7
    e = merr("2e")
    assert e.position == 2 and "演算子" in e.message
    assert merr("a*x ab").position == 5
    assert merr("a(x)").position == 1
    assert merr("exp").position == 1
    assert merr("").message == "式を入力してください"


def test_model_normal_parse_unchanged():
    for text in ("x", "a", "x + [0]", "a*[0]"):
        with pytest.raises(ExprError) as e:
            parse(text)
        assert "使えません" in e.value.message
    assert parse("[0] + 1").kind == "series"


def test_model_fullwidth():
    n = expr.parse_model("ａ＊ｅｘｐ（－ｂ＊ｘ）＋ｃ")
    assert expr.model_to_text(n) == "a*exp(-b*x) + c"


def test_model_precedence_and_assoc():
    x = np.array([0.5, 1.0, 2.0])
    assert np.allclose(mrun("-a^2 + 0*x", x, a=3), -9.0)  # -(a^2)
    assert np.allclose(mrun("a^b^c + 0*x", x, a=2, b=3, c=2), 2**9)
    assert np.allclose(mrun("(-a)^2 + 0*x", x, a=3), 9.0)
    assert np.allclose(mrun("a - (b - x)", x, a=1, b=5), 1 - (5 - x))
    assert expr.model_to_text(expr.parse_model("-a^2 + x")) == "-a^2 + x"
    assert expr.model_to_text(expr.parse_model("(-a)^2 + x")) == "(-a)^2 + x"
    assert expr.model_to_text(expr.parse_model("a^b^c + x")) == "a^b^c + x"
    assert expr.model_to_text(expr.parse_model("(a^b)^c + x")) == "(a^b)^c + x"
    assert expr.model_to_code(expr.parse_model("(a^b)^c + x"), repr) == "(a ** b) ** c + x"


@pytest.mark.parametrize("text", MODELS)
@pytest.mark.parametrize("kind", ["array", "series"])
def test_model_code_matches_evaluate(text, kind):
    xs = np.array([0.1, 0.5, 1.0, 2.0, 3.5])
    x = xs if kind == "array" else pd.Series(xs, index=range(5, 10))
    params = {"a": 1.3, "b": 0.7, "c": 2.0, "d": -0.4, "e": 1.1}
    node = expr.parse_model(text)
    got = np.asarray(mrun(text, x, **params), dtype=float)
    want = expr.evaluate_model(node, xs, params)
    assert np.allclose(got, want, equal_nan=True)
    assert want.shape == xs.shape


def test_model_code_as_function_body():
    code = mcode("a*exp(-b*x) + c")
    ns = {"np": np}
    exec(f"def f(x, a, b, c):\n    return {code}\n", ns)  # テスト内だけで使う
    x = np.linspace(0, 2, 5)
    assert np.allclose(ns["f"](x, np.float64(2), np.float64(1), np.float64(0.5)), 2 * np.exp(-x) + 0.5)
    assert expr.evaluate_model(expr.parse_model("a*x + 1"), [1, 2], {"a": 2}).tolist() == [3.0, 5.0]


@pytest.mark.parametrize(
    "text, want",
    [
        ("a*exp(-b*x)+c", "a*exp(-b*x) + c"),
        ("a * x ** 2 + b * x + c", "a*x^2 + b*x + c"),
        ("a/(1+exp(-b*(x-c)))", "a/(1 + exp(-b*(x - c)))"),
        ("a*x^0.5", "a*x^0.5"),
        ("a*x + 1e-5", "a*x + 1e-05"),
        ("(a*x)^2", "(a*x)^2"),
        ("a/(b*x)", "a/(b*x)"),
        ("a*(b + x)", "a*(b + x)"),
        ("2*3*a*x", "6*a*x"),
    ],
)
def test_model_to_text(text, want):
    assert expr.model_to_text(expr.parse_model(text)) == want


@pytest.mark.parametrize("text", MODELS)
def test_model_text_is_safe(text):
    t = expr.model_to_text(expr.parse_model(text))
    assert t.isascii() and "$" not in t and "\n" not in t
    assert set(t) <= set("abcdexlogsintqrpw0123456789.+-*/^() ")


@pytest.mark.parametrize(
    "text",
    [
        "a*x); import os #",
        "a*x\nimport os",
        "__import__('os')",
        "a*x; b",
        "a.real*x",
        "x[0]*a",
        "a*x$",
        "lambda: a*x",
        "a*x if b else c",
    ],
)
def test_model_injection_rejected(text):
    with pytest.raises(ExprError):
        expr.parse_model(text)


def test_model_limits():
    with pytest.raises(ExprError):
        expr.parse_model("a*x" + "+1" * 100)
    e = merr("a*x+" + "1" * 200)
    assert "200文字" in e.message
    with pytest.raises(ExprError):
        expr.parse_model("(" * 60 + "a*x" + ")" * 60)
    with pytest.raises(ExprError):
        expr.parse_model("-" * 150 + "a*x")
    with pytest.raises(ExprError):
        expr.parse_model("a^" * 90 + "x")


def test_model_nonfinite_constant():
    with pytest.raises(ExprError):
        expr.parse_model("a*x + 1/0")


def test_no_dynamic_execution_in_module():
    import inspect
    import re

    src = inspect.getsource(expr)
    for word in ("eval", "exec", "compile", "ast"):
        assert not re.search(rf"(?<![.\w]){word}\(|import {word}\b", src)
