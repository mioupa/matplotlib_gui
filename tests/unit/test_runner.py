import matplotlib as mpl
import pytest

import matplotlib.pyplot as plt

from mplgui.errors import UserError
from mplgui.runner import (
    ScriptError,
    build_filename,
    figure_to_bytes,
    figure_to_data_uri,
    run_script,
    run_to_image,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def fig():
    f, ax = plt.subplots()
    ax.plot([0, 1, 2], [0, 1, 0])
    yield f
    plt.close(f)


@pytest.mark.parametrize(
    "fmt, magic, mime, ext",
    [
        ("png", b"\x89PNG\r\n\x1a\n", "image/png", "png"),
        ("jpg", b"\xff\xd8\xff", "image/jpeg", "jpg"),
        ("svg", b"<?xml", "image/svg+xml", "svg"),
        ("pdf", b"%PDF-", "application/pdf", "pdf"),
    ],
)
def test_figure_to_bytes_magic(fig, fmt, magic, mime, ext):
    data, got_mime, got_ext = figure_to_bytes(fig, fmt)
    assert data.startswith(magic) and got_mime == mime and got_ext == ext


def test_transparent_only_png_and_svg(fig):
    for fmt in ("png", "svg"):
        figure_to_bytes(fig, fmt, transparent=True)
    for fmt in ("jpg", "pdf"):
        with pytest.raises(UserError) as info:
            figure_to_bytes(fig, fmt, transparent=True)
        assert "背景透過" in info.value.message


def test_transparent_png_has_alpha(fig):
    import io

    from matplotlib import image as mpimg

    data, _, _ = figure_to_bytes(fig, "png", transparent=True)
    arr = mpimg.imread(io.BytesIO(data))
    assert arr.shape[2] == 4 and arr[0, 0, 3] == 0
    data, _, _ = figure_to_bytes(fig, "png", transparent=False)
    assert mpimg.imread(io.BytesIO(data))[0, 0, 3] == 1


def test_unknown_format_is_user_error(fig):
    with pytest.raises(UserError):
        figure_to_bytes(fig, "gif")


def test_data_uri(fig):
    uri, ext = figure_to_data_uri(fig, "png", dpi=100)
    assert uri.startswith("data:image/png;base64,") and ext == "png"
    uri, ext = figure_to_data_uri(fig, "svg")
    assert uri.startswith("data:image/svg+xml;base64,") and ext == "svg"


def test_build_filename():
    assert build_filename("", "png") == "plot.png"
    assert build_filename(None, "png") == "plot.png"
    assert build_filename("  ", "svg") == "plot.svg"
    assert build_filename("fig.1.svg", "pdf") == "fig.1.pdf"
    assert build_filename("name.", "jpg") == "name.jpg"
    assert build_filename("結果", "png") == "結果.png"
    assert build_filename(".png", "png") == "plot.png"


def test_filename_invalid_characters_are_replaced():
    assert build_filename('a/b:c*?.png', "svg") == "a_b_c__.svg"


# ---------------------------------------------------------------- PlaceHolderLayoutEngine の除去


def _tight_fig():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [0, 1, 0])
    fig.tight_layout()
    return fig


@pytest.mark.parametrize("fmt", ["png", "svg", "pdf"])
def test_dropping_placeholder_engine_keeps_output_identical(fmt):
    import io

    from matplotlib.layout_engine import PlaceHolderLayoutEngine

    from mplgui.runner import drop_placeholder_layout_engine

    meta = {"png": {"Software": None}, "svg": {"Date": None}, "pdf": {"CreationDate": None}}[fmt]
    kw = {"dpi": 300} if fmt == "png" else {}

    def render(drop):
        fig = _tight_fig()
        try:
            assert isinstance(fig.get_layout_engine(), PlaceHolderLayoutEngine)
            if drop:
                drop_placeholder_layout_engine(fig)
                assert fig.get_layout_engine() is None
            buf = io.BytesIO()
            with mpl.rc_context({"svg.hashsalt": "fixed"}):
                fig.savefig(buf, format=fmt, metadata=meta, **kw)
            return buf.getvalue()
        finally:
            plt.close(fig)

    assert render(False) == render(True)


def test_real_layout_engine_is_kept():
    from mplgui.runner import drop_placeholder_layout_engine

    fig, ax = plt.subplots(layout="constrained")
    ax.plot([0, 1], [0, 1])
    try:
        drop_placeholder_layout_engine(fig)
        assert fig.get_layout_engine().__class__.__name__ == "ConstrainedLayoutEngine"
        figure_to_bytes(fig, "png")
        assert fig.get_layout_engine().__class__.__name__ == "ConstrainedLayoutEngine"
    finally:
        plt.close(fig)


def test_figure_to_bytes_draws_fewer_times(monkeypatch):
    from matplotlib.figure import Figure

    calls = {"n": 0}
    orig = Figure.draw

    def counting(self, *a, **k):
        calls["n"] += 1
        return orig(self, *a, **k)

    fig = _tight_fig()
    try:
        monkeypatch.setattr(Figure, "draw", counting)
        figure_to_bytes(fig, "png")
        assert calls["n"] == 1
    finally:
        plt.close(fig)


# ---------------------------------------------------------------- run_script


SIMPLE = "import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nax.plot([0, 1], [0, 1])\n"


def test_run_script_returns_fig_and_closes_it_afterwards():
    before = set(plt.get_fignums())
    with run_script(SIMPLE) as run:
        assert len(run.fig.axes[0].lines) == 1
        assert set(plt.get_fignums()) - before  # 実行中は存在する
    assert set(plt.get_fignums()) == before


def test_print_and_stderr_are_captured_in_order(capsys):
    code = SIMPLE + "import sys\nprint('first')\nprint('second', file=sys.stderr)\nprint('third')\n"
    with run_script(code) as run:
        assert run.output == "first\nsecond\nthird\n"
    assert capsys.readouterr().out == ""  # 画面（標準出力）には出ない


def test_injected_names_and_namespace():
    code = "import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nax.plot(values)\nname = __name__\n"
    with run_script(code, injected={"values": [1, 2, 3]}) as run:
        assert run.namespace["name"] == "__main__" and list(run.fig.axes[0].lines[0].get_ydata()) == [1, 2, 3]


def test_fig_variable_wins_over_last_figure():
    code = (
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots(); ax.set_title('first')\n"
        "other, bx = plt.subplots(); bx.set_title('second')\n"
    )
    with run_script(code) as run:
        assert run.fig.axes[0].get_title() == "first"


def test_last_new_figure_is_used_without_fig_variable():
    code = "import matplotlib.pyplot as plt\nplt.figure().add_subplot().set_title('a')\nplt.figure().add_subplot().set_title('b')\n"
    before = set(plt.get_fignums())
    with run_script(code) as run:
        assert run.fig.axes[0].get_title() == "b"
    assert set(plt.get_fignums()) == before


def test_no_figure_is_user_error():
    with pytest.raises(UserError) as info:
        with run_script("x = 1\nprint('hi')\n"):
            pass
    assert info.value.message == "図が作られませんでした。fig, ax = plt.subplots() などで図を作ってください。"
    assert info.value.field == "Pythonコード" and info.value.output == "hi\n"


def test_empty_figure_is_allowed():
    with run_script("import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\n") as run:
        assert len(run.fig.axes[0].lines) == 0


def test_fig_variable_that_is_not_a_figure_falls_back_to_new_figure():
    with run_script("import matplotlib.pyplot as plt\nfig = 3\nplt.figure().add_subplot()\n") as run:
        assert len(run.fig.axes) == 1


def test_rcparams_do_not_leak_between_runs():
    before = mpl.rcParams["axes.titlesize"], mpl.rcParams["lines.linewidth"]
    code = SIMPLE + "plt.rcParams['lines.linewidth'] = 9\nplt.rcParams['axes.titlesize'] = 30\n"
    with run_script(code):
        assert mpl.rcParams["lines.linewidth"] == 9
    assert (mpl.rcParams["axes.titlesize"], mpl.rcParams["lines.linewidth"]) == before
    with pytest.raises(ScriptError):
        with run_script(code + "raise ValueError('x')"):
            pass
    assert (mpl.rcParams["axes.titlesize"], mpl.rcParams["lines.linewidth"]) == before


def test_plt_show_emits_no_warning_but_other_warnings_pass():
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with run_script(SIMPLE + "plt.show()\n"):
            pass
    assert not [w for w in caught if "non-interactive" in str(w.message)]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with run_script(SIMPLE + "import warnings\nwarnings.warn('keep me')\n"):
            pass
    assert [str(w.message) for w in caught] == ["keep me"]


def test_cwd_is_changed_and_restored(tmp_path):
    import os

    (tmp_path / "data.txt").write_text("1 2 3", encoding="utf-8")
    code = SIMPLE + "import os\nvalues = open('data.txt').read()\nprint(os.getcwd() == %r)\n" % str(tmp_path.resolve())
    before = os.getcwd()
    with run_script(code, cwd=tmp_path) as run:
        assert run.output.strip() == "True" and run.namespace["values"] == "1 2 3"
    assert os.getcwd() == before


def test_cwd_is_restored_on_error(tmp_path):
    import os

    before = os.getcwd()
    with pytest.raises(ScriptError):
        with run_script("raise ValueError('x')", cwd=tmp_path):
            pass
    assert os.getcwd() == before


# ---------------------------------------------------------------- error reporting


def _error(code, **kw):
    with pytest.raises(ScriptError) as info:
        with run_script(code, **kw):
            pass
    return info.value


def test_runtime_error_reports_user_frames_line_and_source():
    code = "import matplotlib.pyplot as plt\nimport pandas as pd\nfig, ax = plt.subplots()\n\ndef f(v):\n    return v + undefined_name\n\nf(1)\n"
    err = _error(code)
    assert err.line == 6 and err.field == "Pythonコード" and isinstance(err.exc, NameError)
    assert 'File "plot.py", line 8, in <module>' in err.traceback_text and "    f(1)" in err.traceback_text
    assert 'File "plot.py", line 6, in f' in err.traceback_text and "    return v + undefined_name" in err.traceback_text
    assert err.traceback_text.rstrip().endswith("NameError: name 'undefined_name' is not defined")
    assert "runner.py" not in err.traceback_text and "contextlib" not in err.traceback_text
    assert "runner.py" in err.detail  # 全体のトレースバックは別に持つ


def test_error_in_library_called_from_user_code_points_at_user_line():
    err = _error("import pandas as pd\n\npd.DataFrame({'a': [1]})['missing']\n")
    assert err.line == 3 and isinstance(err.exc, KeyError)
    assert "pandas" not in err.traceback_text.split("KeyError")[0].replace("import pandas", "").replace("pd.DataFrame", "")


def test_status_message_is_japanese_with_line_and_hint():
    err = _error("x = 1\ny = 2\nprint(zzz)\n")
    assert err.message == (
        "Pythonコードの実行中にエラーが発生しました（3行目、NameError: 定義されていない名前を使っています）。"
        "詳細は「Pythonコード」タブに表示しています。"
    )
    assert "is not defined" not in err.message  # 英語の例外文はトレースバックだけに出す


def test_syntax_error_shows_line_and_caret():
    err = _error("import matplotlib.pyplot as plt\nfig, ax = plt.subplots(\nx = = 1\n")
    assert err.line is not None and isinstance(err.exc, SyntaxError)
    assert 'File "plot.py"' in err.traceback_text and "SyntaxError" in err.traceback_text and "^" in err.traceback_text
    assert f"{err.line}行目" in err.message and "SyntaxError: 書き方（文法）が正しくありません" in err.message


def test_indentation_error_hint():
    err = _error("if True:\nprint(1)\n")
    assert "IndentationError: インデント" in err.message and err.line == 2


@pytest.mark.parametrize(
    "code, kind, hint",
    [
        ("open('nope.txt')", "FileNotFoundError", "ファイルが見つかりません"),
        ("import not_a_real_module", "ModuleNotFoundError", "読み込めないライブラリ"),
        ("from os import nothing_here", "ImportError", "読み込めないライブラリや名前"),
        ("{}['a']", "KeyError", "存在しないキー"),
        ("[][1]", "IndexError", "範囲の外"),
        ("1 + 'a'", "TypeError", "型が合わない"),
        ("int('x')", "ValueError", "値が正しくありません"),
        ("object().foo", "AttributeError", "存在しない属性"),
        ("1 / 0", "ZeroDivisionError", "0で割り算"),
    ],
)
def test_hint_table(code, kind, hint):
    err = _error(code)
    assert type(err.exc).__name__ == kind
    assert f"{kind}: " in err.message and hint in err.message and err.line == 1


def test_unknown_exception_type_has_no_hint():
    err = _error("class MyError(Exception):\n    pass\n\nraise MyError('x')\n")
    assert err.message.startswith("Pythonコードの実行中にエラーが発生しました（4行目、MyError）。")


def test_system_exit_is_reported_not_propagated():
    err = _error("import sys\nsys.exit(2)\n")
    assert isinstance(err.exc, SystemExit) and err.line == 2 and "SystemExit" in err.message


def test_error_keeps_output_printed_before_failure():
    err = _error("print('before')\n1/0\n")
    assert err.output == "before\n"
    assert err.to_dict()["line"] == 2 and "traceback" in err.to_dict()


def test_failed_run_leaks_no_figures_and_no_linecache():
    import linecache

    before = set(plt.get_fignums())
    _error("import matplotlib.pyplot as plt\nplt.figure()\nraise ValueError('x')\n")
    assert set(plt.get_fignums()) == before and "plot.py" not in linecache.cache


# ---------------------------------------------------------------- run_to_image / summary


def test_run_to_image_returns_png_output_and_summary():
    res = run_to_image(SIMPLE + "ax.set_title('T')\nprint('hello')\n", file_format="png", dpi=100)
    assert res.data.startswith(b"\x89PNG") and res.output == "hello\n" and res.mime == "image/png"
    assert res.summary[0]["title"] == "T" and res.summary[0]["lines"] == 1


def test_run_to_image_conversion_error_carries_output():
    with pytest.raises(UserError) as info:
        run_to_image(SIMPLE + "print('x')\n", file_format="jpg", transparent=True)
    assert "背景透過" in info.value.message and info.value.output == "x\n"


def test_figure_summary_content():
    import json

    code = (
        "import matplotlib.pyplot as plt\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot([1, 2], [3, 4], label='線')\nax.scatter([1], [1])\nax.bar(['a', 'b'], [1, 2])\n"
        "ax.set_title('T'); ax.set_xlabel('X'); ax.set_ylabel('Y'); ax.set_yscale('log'); ax.set_ylim(1, 10)\n"
        "ax.legend()\nax2 = ax.twinx()\n"
    )
    res = run_to_image(code)
    json.dumps(res.summary)
    first, second = res.summary
    assert first["title"] == "T" and first["xlabel"] == "X" and first["ylabel"] == "Y"
    assert first["yscale"] == "log" and first["xscale"] == "linear" and first["ylim"] == [1.0, 10.0]
    assert (first["lines"], first["collections"], first["patches"]) == (1, 1, 2)
    assert first["legend"] == ["線"] and second["legend"] == []
    assert all(isinstance(v, float) for v in first["xlim"])


# ---------------------------------------------------------------- Phase 3: save rc, size guard


def test_pdf_uses_type42_without_script_help(fig):
    data, _, _ = figure_to_bytes(fig, "pdf")
    assert b"/FontFile2" in data and b"/Type3" not in data
    assert mpl.rcParams["pdf.fonttype"] == 3  # rc_context の外には漏れない


def test_svg_text_option(fig):
    fig.axes[0].set_title("Title")
    assert b"<text" not in figure_to_bytes(fig, "svg")[0]
    assert b"<text" not in figure_to_bytes(fig, "svg", svg_text="path")[0]
    assert b"<text" in figure_to_bytes(fig, "svg", svg_text="text")[0]
    assert mpl.rcParams["svg.fonttype"] == "path"


def test_figure_to_bytes_dpi_changes_pixels(fig):
    import struct

    data, _, _ = figure_to_bytes(fig, "png", dpi=50)
    assert struct.unpack(">II", data[16:24]) == (320, 240)


def test_raster_size_guard_in_runner_and_vector_unaffected():
    big, _ = plt.subplots(figsize=(50, 50))
    try:
        with pytest.raises(UserError) as info:
            figure_to_bytes(big, "png", dpi=1200)
        assert info.value.field == "保存 DPI" and "幅 60000 × 高さ 60000 ピクセル" in info.value.message
        with pytest.raises(UserError):
            figure_to_bytes(big, "jpg", dpi=1200)
        assert figure_to_bytes(big, "svg", dpi=1200)[0].startswith(b"<?xml")
    finally:
        plt.close(big)


def test_check_raster_size_limits():
    from mplgui.formats import check_raster_size

    check_raster_size(8, 6, 1200)  # 9600 x 7200 = 約6900万画素
    check_raster_size(50, 50, 200)  # 10000 x 10000 = 1億画素ちょうど
    with pytest.raises(UserError):
        check_raster_size(50, 50, 201)  # 画素数の上限を超える
    with pytest.raises(UserError):
        check_raster_size(55, 1, 1200)  # 66000 画素の辺（1辺は 65536 未満）


def test_is_mathtext_error_detects_only_math_parse_errors():
    from mplgui.runner import MATHTEXT_HINT, is_mathtext_error, japanese_hint

    fig, ax = plt.subplots()
    ax.set_title(r"$\alpah$")
    try:
        with pytest.raises(ValueError) as info:
            fig.canvas.draw()
        assert is_mathtext_error(info.value) and japanese_hint(info.value) == MATHTEXT_HINT
    finally:
        plt.close(fig)
    assert not is_mathtext_error(ValueError("x")) and not is_mathtext_error(None)
    assert japanese_hint(ValueError("x")) == "値が正しくありません"
    assert "\\$" in MATHTEXT_HINT


def test_mathtext_error_during_conversion_is_a_user_error_with_field():
    from mplgui.runner import MathtextError

    with pytest.raises(MathtextError) as info:
        run_to_image(SIMPLE + "ax.set_title('m$^$')\n")
    assert info.value.field == "数式" and "数式" in info.value.message
