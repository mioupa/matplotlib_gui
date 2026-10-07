import matplotlib

matplotlib.use("Agg")  # ブラウザ版と同じバックエンド。import 時点で固定する

import warnings  # noqa: E402

import pytest  # noqa: E402

FIXTURES_NAME = "fixtures"


@pytest.fixture(autouse=True)
def _quiet_glyph_warnings():
    # 開発環境には日本語フォントが無いことがあるので、グリフ不足の警告は無視する
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*missing from font.*", category=UserWarning)
        warnings.filterwarnings("ignore", message=".*missing from current font.*", category=UserWarning)
        yield


@pytest.fixture(autouse=True)
def _no_leaked_figures():
    import matplotlib.pyplot as plt

    before = set(plt.get_fignums())
    yield
    leaked = set(plt.get_fignums()) - before
    for num in leaked:
        plt.close(num)
    assert not leaked, f"閉じられていない Figure が残っている: {sorted(leaked)}"
