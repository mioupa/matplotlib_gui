"""Phase 5a: 既定の設定（目盛・枠線・エラーバーを使わない）の生成コードが、Phase 4 と1文字も変わらないことを確かめる。

tests/unit/golden/*.py.txt は Phase 5a の変更前のコードで生成した出力（golden_cases.py が構成を定義する）。
"""
from pathlib import Path

import pytest

import golden_cases

pytestmark = pytest.mark.unit

GOLDEN = Path(__file__).resolve().parent / "golden"


@pytest.mark.parametrize("name", list(golden_cases.CASES))
def test_default_output_is_byte_identical_to_phase4(name):
    expected = (GOLDEN / f"{name}.py.txt").read_text(encoding="utf-8")
    assert golden_cases.build(name) == expected
