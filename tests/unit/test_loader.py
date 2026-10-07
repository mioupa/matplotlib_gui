from pathlib import Path

import pytest

from mplgui.errors import UserError
from mplgui.loader import build_preview, column_options, decode_delimiter, load_dataframe, load_file

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(name, delimiter="", has_header=True):
    return load_file((FIXTURES / name).read_bytes(), name, delimiter, has_header)


def test_decode_delimiter():
    assert decode_delimiter("", ".csv") == ","
    assert decode_delimiter("", ".txt") == r"\s+"
    assert decode_delimiter(r"\t", ".txt") == "\t"
    assert decode_delimiter(";", ".csv") == ";"


def test_utf8_csv():
    loaded = _load("utf8.csv")
    assert list(loaded.df.columns) == ["時間", "電圧", "電流"]
    assert loaded.encoding == "utf-8" and len(loaded.df) == 30


def test_utf8_bom_csv_loads():
    # BOM が列名に残らない対応は A5（Step 5）。ここでは読めて列数が正しいことだけ確認する
    loaded = _load("utf8_bom.csv")
    assert loaded.df.shape == (30, 3)


def test_cp932_fixture_is_not_supported_by_current_logic():
    # 現行の文字コード判定（utf-8 → shift_jis）では機種依存文字を含む cp932 は読めない。A5 で対応する
    with pytest.raises(UserError) as info:
        _load("cp932.csv")
    assert "文字コード" in info.value.message


def test_tab_txt_whitespace_auto():
    loaded = _load("tab.txt")
    assert list(loaded.df.columns) == ["時間", "電圧", "電流"]


def test_tab_txt_explicit_delimiter():
    loaded = _load("tab.txt", delimiter=r"\t")
    assert loaded.df.shape == (30, 3)


def test_xlsx_first_sheet():
    loaded = _load("multi_sheet.xlsx")
    assert list(loaded.df.columns) == ["時間", "電圧", "電流"]
    assert loaded.encoding is None


def test_duplicate_columns_are_distinguishable_by_index():
    df = _load("duplicate_columns.csv").df
    opts = column_options(df)
    assert [o["value"] for o in opts] == ["__idx__0", "__idx__1", "__idx__2"]
    assert len({o["label"] for o in opts}) == 3
    assert opts[0]["label"].endswith("[0]") and opts[1]["label"].endswith("[1]")
    assert not df.iloc[:, 0].equals(df.iloc[:, 1])


def test_no_header_names_columns():
    loaded = _load("utf8.csv", has_header=False)
    assert list(loaded.df.columns) == ["column_0", "column_1", "column_2"]
    assert len(loaded.df) == 31


def test_non_numeric_fixture_loads_as_text_columns():
    df = _load("non_numeric.csv").df
    import pandas as pd

    assert not pd.api.types.is_numeric_dtype(df["金額"]) and not pd.api.types.is_numeric_dtype(df["単位付き"])


def test_preview_payload_shape():
    df = _load("utf8.csv").df
    p = build_preview(df)
    assert set(p) == {"columns", "rows", "totalRows", "totalColumns", "limit", "truncated"}
    assert p["columns"] == ["時間", "電圧", "電流"]
    assert p["totalRows"] == 30 and p["totalColumns"] == 3 and p["truncated"] is False
    assert len(p["rows"]) == 30 and all(len(r) == 3 for r in p["rows"])
    assert all(isinstance(c, str) for r in p["rows"] for c in r)
    assert p["rows"][1] == ["0.1", "0.1987", "1.4777"]


def test_preview_is_truncated_to_100_rows():
    import pandas as pd

    p = build_preview(pd.DataFrame({"a": range(250), "b": range(250)}))
    assert len(p["rows"]) == 100 and p["truncated"] is True and p["totalRows"] == 250 and p["limit"] == 100


def test_nan_cells_in_preview():
    p = build_preview(_load("non_numeric.csv").df)
    assert any("NaN" in row for row in p["rows"])


@pytest.mark.parametrize(
    "name, data",
    [("a.pdf", b"x"), ("empty.csv", b""), ("onlyheader.csv", b"a,b\n")],
)
def test_errors_are_user_errors_in_japanese(name, data):
    with pytest.raises(UserError) as info:
        load_file(data, name, "", True)
    assert not info.value.message.isascii()


def test_load_dataframe_wrapper():
    assert not load_dataframe((FIXTURES / "utf8.csv").read_bytes(), "utf8.csv", "", True).empty
