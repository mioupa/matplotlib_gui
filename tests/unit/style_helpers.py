"""Phase 5b のテスト（系列のスタイル・注釈・近似曲線）が共有する補助。"""
import contextlib

import numpy as np
import pandas as pd

from mplgui.codegen import generate_script
from mplgui.dataprep import plan_plot
from mplgui.loader import load_file
from mplgui.runner import figure_summary, run_script
from mplgui.settings import default_settings, parse_settings

N = 10


def frame():
    t = np.arange(N, dtype=float)
    return pd.DataFrame(
        {
            "t": t,  # 0
            "v": t * 2 + 10,  # 1
            "lo": t * 2 + 8,  # 2
            "hi": t * 2 + 13,  # 3
            "w": 100 - t * 3.0,  # 4
        }
    )


def series(y=1, x=0, **kw):
    d = {"x": x if isinstance(x, str) else f"__idx__{x}", "y": f"__idx__{y}"}
    d.update(kw)
    return d


def raw_settings(series_list=None, plot_type="line", mutate=None, annotations=None, fits=None):
    raw = default_settings()
    raw["series"] = series_list if series_list is not None else [series()]
    raw["plot"]["type"] = plot_type
    if annotations is not None:
        raw["annotations"] = annotations
    if fits is not None:
        raw["fits"] = fits
    if mutate:
        mutate(raw)
    return raw


def plan_of(df=None, **kw):
    loaded = load_file((df if df is not None else frame()).to_csv(index=False).encode("utf-8"), "d.csv", "", True)
    settings = parse_settings(raw_settings(**kw))
    return plan_plot(loaded.df, settings)


class Built:
    def __init__(self, tmp_path, df=None, **kw):
        self.dir = tmp_path
        (df if df is not None else frame()).to_csv(tmp_path / "d.csv", index=False, encoding="utf-8")
        self.loaded = load_file((tmp_path / "d.csv").read_bytes(), "d.csv", "", True)
        self.settings = parse_settings(raw_settings(**kw))
        self.plan = plan_plot(self.loaded.df, self.settings)
        self.script = generate_script(self.settings, self.loaded.source, self.plan)

    @contextlib.contextmanager
    def full(self):
        with run_script(self.script.text, cwd=self.dir) as run:
            yield run

    @contextlib.contextmanager
    def auto(self):
        with run_script(self.script.auto_render_text(), injected={"df": self.loaded.df}) as run:
            yield run

    def check(self, fn):
        """全体の実行と自動描画用の実行の両方に fn(fig) を適用し、要約が一致することも確かめる。要約を返す。"""
        with self.full() as run:
            fn(run.fig)
            full = figure_summary(run.fig)
        with self.auto() as run:
            fn(run.fig)
            auto = figure_summary(run.fig)
        assert full == auto
        return full
