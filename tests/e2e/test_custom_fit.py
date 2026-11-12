"""任意の式の近似曲線（Phase 5d, G10）: カードの出し分け、scipy の遅延読み込み、エラーと復帰、編集モード。"""
import pytest

from helpers import (
    add_fit,
    code_is_stale,
    code_value,
    enter_edit_mode,
    image_summary,
    is_hidden_by_id,
    load_fixture,
    run_edited_code,
    scipy_state,
    state_list,
    status_text,
    wait_app_ready,
    wait_error_status,
    wait_scipy_state,
    wait_settled,
)

pytestmark = pytest.mark.e2e

LONG = 300_000
X, MEAN = "__idx__0", "__idx__1"

EDIT_CODE = """import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

x = np.linspace(0, 5, 20)
y = 2 * x + 1
p, _ = curve_fit(lambda x, a, b: a * x + b, x, y)
fig, ax = plt.subplots()
ax.plot(x, y)
plt.show()
"""


def start(page, app_url, fixtures_dir):
    page.goto(app_url)
    wait_app_ready(page)
    load_fixture(page, fixtures_dir / "band.csv")
    wait_settled(page)
    page.select_option("#series-s1-x", X)
    page.select_option("#series-s1-y", MEAN)
    page.fill("#series-s1-legend-name", "温度")
    wait_settled(page)


def test_card_fields_follow_the_model_and_expression(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    f = add_fit(page)
    wait_settled(page)
    custom_ids = [f"fit-{f}-expr", f"fit-{f}-expr-help"] + [f"fit-{f}-initial-{p}" for p in "abcde"]
    assert all(is_hidden_by_id(page, i) for i in custom_ids)
    # poly: 次数だけ。linear は何も増えない
    page.select_option(f"#fit-{f}-model", "poly")
    assert not is_hidden_by_id(page, f"fit-{f}-degree") and all(is_hidden_by_id(page, i) for i in custom_ids)
    wait_settled(page)
    # custom: 式と補足が出て次数は隠れる。初期値は式に出てくるパラメータだけ
    page.select_option(f"#fit-{f}-model", "custom")
    assert is_hidden_by_id(page, f"fit-{f}-degree")
    assert not is_hidden_by_id(page, f"fit-{f}-expr") and not is_hidden_by_id(page, f"fit-{f}-expr-help")
    assert page.get_attribute(f"#fit-{f}-expr", "placeholder") == "例: a*exp(-b*x) + c"
    help_text = page.inner_text(f"#fit-{f}-expr-help")
    assert "a〜e" in help_text and "^" in help_text and "exp" in help_text
    assert all(is_hidden_by_id(page, f"fit-{f}-initial-{p}") for p in "abcde")
    page.click(f"#fit-{f}-expr")
    page.keyboard.type("a*exp(-b*x) + c")
    shown = {p: not is_hidden_by_id(page, f"fit-{f}-initial-{p}") for p in "abcde"}
    assert shown == {"a": True, "b": True, "c": True, "d": False, "e": False}
    # 入力中に欄が作り直されない（フォーカスが残る）。1e3・関数名の中の文字は数えない
    assert page.evaluate("document.activeElement.id") == f"fit-{f}-expr"
    page.fill(f"#fit-{f}-expr", "1e3*abs(x) + d")
    shown = {p: not is_hidden_by_id(page, f"fit-{f}-initial-{p}") for p in "abcde"}
    assert shown == {"a": False, "b": False, "c": False, "d": True, "e": False}
    page.fill(f"#fit-{f}-initial-d", "2.5")
    fit = state_list(page, "fits")[0]
    assert fit["model"] == "custom" and fit["expr"] == "1e3*abs(x) + d" and fit["initial"]["d"] == 2.5
    # linear に戻すとカードは元どおり
    page.select_option(f"#fit-{f}-model", "linear")
    assert all(is_hidden_by_id(page, i) for i in custom_ids) and is_hidden_by_id(page, f"fit-{f}-degree")


def test_no_scipy_request_without_custom_fit(page, app_url, fixtures_dir, console_log):
    reqs = []
    page.on("request", lambda r: reqs.append(r.url))
    start(page, app_url, fixtures_dir)
    add_fit(page, model="poly", degree="3")
    wait_settled(page)
    assert image_summary(page)[0]["fitlines"] == 1
    assert scipy_state(page) == "idle"
    assert not [u for u in reqs if "scipy-" in u]


def test_custom_fit_with_real_scipy_error_and_recovery(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    reqs = []
    page.on("request", lambda r: reqs.append(r.url))
    f = add_fit(page, model="custom", expr="a*y")  # y は使えない
    wait_scipy_state(page, "ready", LONG)
    wait_settled(page, LONG)
    wait_error_status(page)
    assert "近似曲線1の式" in status_text(page)
    assert code_is_stale(page)
    page.fill(f"#fit-{f}-expr", "a*x^2 + b*x + c")
    wait_settled(page, LONG)
    assert scipy_state(page) == "ready"
    s = image_summary(page)[0]
    assert s["fitlines"] == 1
    label = [t for t in s["legend"] if t.startswith("温度の近似")]
    assert label and "a = " in label[0] and "$R^2$ = " in label[0]
    code = code_value(page)
    assert "from scipy.optimize import curve_fit" in code and "def fit_model_1(" in code
    assert not code_is_stale(page)
    assert [u for u in reqs if "scipy-" in u]
    # 1次式に戻すと import は消える
    page.select_option(f"#fit-{f}-model", "linear")
    wait_settled(page)
    assert "scipy" not in code_value(page)
    assert image_summary(page)[0]["fitlines"] == 1


def test_scipy_load_failure(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    page.route("**/scipy-*.whl", lambda r: r.abort())
    add_fit(page, model="custom", expr="a*x + b")
    wait_scipy_state(page, "failed", LONG)
    wait_settled(page, LONG)
    wait_error_status(page)
    assert "scipy を読み込めませんでした" in status_text(page)
    assert code_is_stale(page)


def test_edit_mode_loads_scipy_on_demand(page, app_url, fixtures_dir, console_log):
    start(page, app_url, fixtures_dir)
    enter_edit_mode(page)
    assert scipy_state(page) == "idle"
    page.fill("#customPyCode", EDIT_CODE)
    run_edited_code(page)
    assert scipy_state(page) == "ready"
    assert page.get_attribute("#codeOutput", "data-kind") == "ok"
    assert image_summary(page)[0]["lines"] == 1
