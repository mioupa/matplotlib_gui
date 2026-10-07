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


@pytest.mark.parametrize(
    "name, code",
    [
        ("utf8.csv", "utf-8"),
        ("utf8_bom.csv", "utf-8-sig"),
        ("cp932.csv", "cp932"),
        ("euc_jp.csv", "euc-jp"),
        ("tab.txt", "utf-8"),
        ("duplicate_columns.csv", "utf-8"),
        ("non_numeric.csv", "utf-8"),
        ("multi_sheet.xlsx", None),
    ],
)
def test_every_fixture_loads_with_expected_encoding(name, code):
    loaded = _load(name)
    assert loaded.encoding == code
    assert len(loaded.df) > 0


def test_utf8_bom_is_not_left_in_first_header():
    loaded = _load("utf8_bom.csv")
    assert loaded.df.shape == (30, 3)
    assert list(loaded.df.columns) == ["時間", "電圧", "電流"]
    assert "\ufeff" not in str(loaded.df.columns[0])


def test_cp932_machine_dependent_characters_survive():
    df = _load("cp932.csv").df
    assert df.columns[0] == "時間①"
    assert "㈱テスト" in set(df["備考"])


def test_euc_jp_is_not_mistaken_for_cp932():
    loaded = _load("euc_jp.csv")
    assert loaded.encoding == "euc-jp"
    assert list(loaded.df.columns) == ["時間", "電圧", "電流", "備考"]
    assert "測定開始" in set(loaded.df["備考"])


def test_ambiguous_bytes_prefer_the_plausible_candidate():
    # 「あい」の EUC-JP は cp932 でも半角カナとして厳密にデコードできてしまう
    data = "名前,値\nあい,1\nうえお,2\n".encode("euc-jp")
    data.decode("cp932")  # 例外にならないこと（前提の確認）
    assert load_file(data, "x.csv", "", True).encoding == "euc-jp"


def test_ambiguous_tie_prefers_cp932():
    # ASCII だけに近い短いバイト列など、どちらでも同じ見た目になる場合は cp932
    from mplgui.loader import detect_encoding

    assert detect_encoding("ｱ\n".encode("cp932"))[0] == "cp932"  # 半角カナ 1 文字: EUC-JP では 0x8E 付きの別表現


def test_undecodable_bytes_give_japanese_error():
    import random

    rng = random.Random(0)
    data = b"a,b\n" + bytes([0xFF, 0xFE, 0xFD] + [rng.choice([0xFF, 0xFF, 0x81, 0x41]) for _ in range(40)]) + b"\n"
    with pytest.raises(UserError) as info:
        load_file(data, "bad.csv", "", True)
    msg = info.value.message
    assert "文字コードを判定できませんでした" in msg and "UTF-8" in msg and "保存し直して" in msg


def test_unparsable_csv_gives_japanese_error():
    data = b"a,b\n1,2\n1,2,3,4,5\n6,7\n"
    with pytest.raises(UserError) as info:
        load_file(data, "ragged.csv", ",", True)
    assert not info.value.message.isascii() and "Error" not in info.value.message


def test_bad_regex_delimiter_gives_japanese_error():
    with pytest.raises(UserError) as info:
        load_file(b"a b\n1 2\n", "x.txt", "(a", True)
    assert info.value.field == "区切り文字" and not info.value.message.isascii()


def test_bad_delimiter_escape_gives_japanese_error():
    with pytest.raises(UserError) as info:
        decode_delimiter("\\x", ".csv")
    assert info.value.field == "区切り文字"


def test_broken_xlsx_gives_japanese_error():
    with pytest.raises(UserError) as info:
        load_file(b"not a zip", "broken.xlsx", "", True)
    assert "Excel" in info.value.message and info.value.detail


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
