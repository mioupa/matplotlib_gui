"""テスト用の合成データを決定的に生成する。実データは一切含まない。

実行: uv run python tests/fixtures/make_fixtures.py
"""
import math
import re
from datetime import datetime
from pathlib import Path

import openpyxl

OUT = Path(__file__).parent
N = 30


def rows():
    out = []
    for i in range(N):
        t = i * 0.1
        out.append((round(t, 3), round(math.sin(t * 2), 4), round(0.5 * math.cos(t * 3) + 1, 4)))
    return out


def csv_text(header, data, sep=","):
    lines = [sep.join(header)]
    lines += [sep.join(str(v) for v in r) for r in data]
    return "\n".join(lines) + "\n"


def _normalize_zip(path):
    """zip 内の更新時刻を固定する（openpyxl は保存時刻を書き込むため）。"""
    import zipfile

    with zipfile.ZipFile(path) as zf:
        items = [(info.filename, zf.read(info.filename)) for info in zf.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        for name, data in items:
            if name == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*", rb"\g<1>2026-01-01T00:00:00Z", data)
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            out.writestr(info, data)


def main():
    data = rows()
    header = ["時間", "電圧", "電流"]
    text = csv_text(header, data)
    (OUT / "utf8.csv").write_bytes(text.encode("utf-8"))
    (OUT / "utf8_bom.csv").write_bytes(text.encode("utf-8-sig"))

    # cp932 固有（機種依存）文字: ① ㈱ は shift_jis(厳密) では符号化できない
    cp_header = ["時間①", "電圧", "電流"]
    lines = [",".join(cp_header) + ",備考"]
    for i, r in enumerate(data):
        lines.append(",".join(str(v) for v in r) + (",㈱テスト" if i % 5 == 0 else ",通常"))
    (OUT / "cp932.csv").write_bytes(("\n".join(lines) + "\n").encode("cp932"))

    # EUC-JP（漢字・ひらがな・全角カタカナ。半角カナは含めない）
    eu_header = ["時間", "電圧", "電流", "備考"]
    eu_lines = [",".join(eu_header)]
    notes = ["通常", "測定開始", "異常なし", "再測定"]
    for i, r in enumerate(data):
        eu_lines.append(",".join(str(v) for v in r) + "," + notes[i % len(notes)])
    (OUT / "euc_jp.csv").write_bytes(("\n".join(eu_lines) + "\n").encode("euc-jp"))

    (OUT / "tab.txt").write_bytes(csv_text(header, data, sep="\t").encode("utf-8"))

    # 生成コードの一致確認用: 正の値だけ（対数軸に使える）／文字列のカテゴリ列を持つ棒グラフ用
    growth = [(i, round(2 ** (i / 3), 4), round(10 + i * 1.5, 2)) for i in range(N)]
    (OUT / "growth.csv").write_bytes(csv_text(["時間", "指数", "線形"], growth).encode("utf-8"))
    cats = [(f"品目{c}", 10 + i * 7 % 23, 30 - i * 5 % 17) for i, c in enumerate("ABCDEF")]
    (OUT / "categories.csv").write_bytes(csv_text(["品目", "売上A", "売上B"], cats).encode("utf-8"))

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Sheet1"
    ws1.append(header)
    for r in data:
        ws1.append(list(r))
    ws2 = wb.create_sheet("二枚目")
    ws2.append(["x", "y", "z"])
    for i in range(20):
        ws2.append([i, i * i, 100 - i])
    # 作成日時を固定して、再生成してもバイト列が変わらないようにする
    fixed = datetime(2026, 1, 1)
    wb.properties.created = fixed
    wb.properties.modified = fixed
    wb.save(OUT / "multi_sheet.xlsx")
    _normalize_zip(OUT / "multi_sheet.xlsx")

    # 前置き行（装置の説明）が3行。3行目はカンマの数が違うので、skipLines 無しでは表として読めない
    pre = [
        "装置: テスト用ロガー,型番: X-100,単位: V",
        "備考: この行はデータではありません",
        "測定日: 2026-01-01,担当: 合成データ,単位: V と mA,備考: 5列,終",
    ]
    (OUT / "preamble.csv").write_bytes(("\n".join(pre) + "\n" + text).encode("utf-8"))

    # ヨーロッパ式の数値: 区切り ;、小数点 ,、桁区切り .（1.234,5）
    eu = [(i + 1, f"{(i + 1) * 1234.5:,.1f}".replace(",", "_").replace(".", ",").replace("_", "."), f"{i * 0.25:.2f}".replace(".", ",")) for i in range(12)]
    eu.append((13, "-1.234.567,5", "-0,5"))
    (OUT / "european.csv").write_bytes(csv_text(["番号", "値", "比"], eu, sep=";").encode("utf-8"))

    # 引用符付きの桁区切り（カンマ区切りで "1,234"）。負の値も含む
    th = [(i + 1, f'"{(i + 1) * 1234:,}"', f'"{-(i + 1) * 98765.5:,.1f}"') for i in range(12)]
    (OUT / "thousands.csv").write_bytes(csv_text(["番号", "金額", "差額"], th).encode("utf-8"))

    # コメント: 行全体の # と、データ行の末尾の # note
    cm = ["# 全体のコメント", "x,y"]
    for i in range(10):
        cm.append(f"{i},{i * i}" + (" # note" if i == 4 else ""))
        if i == 6:
            cm.append("# 途中のコメント行")
    (OUT / "comments.csv").write_bytes(("\n".join(cm) + "\n").encode("utf-8"))

    # 2 シート。2 枚目は見出しの前に説明の行が 2 行ある
    wb2 = openpyxl.Workbook()
    p1 = wb2.active
    p1.title = "データ"
    p1.append(["t", "v"])
    for i in range(15):
        p1.append([i, i * 2])
    p2 = wb2.create_sheet("説明つき")
    p2.append(["測定条件: 合成データ"])
    p2.append(["単位: V"])
    p2.append(["t", "v", "w"])
    for i in range(15):
        p2.append([i, i * i, 100 - i])
    wb2.properties.created = fixed
    wb2.properties.modified = fixed
    wb2.save(OUT / "preamble.xlsx")
    _normalize_zip(OUT / "preamble.xlsx")

    dup = ["温度", "温度", "値"]
    # 同名列(温度)で値が異なる
    d = [(20 + i * 0.5, 100 - i * 2, round(math.sqrt(i + 1), 4)) for i in range(N)]
    (OUT / "duplicate_columns.csv").write_bytes(csv_text(dup, d).encode("utf-8"))

    lines = ["番号,金額,電圧,単位付き"]
    for i in range(20):
        amount = f'"{(i + 1) * 1234:,}"'
        volt = "N/A" if i % 7 == 3 else ("" if i % 7 == 5 else str(round(i * 0.25, 2)))
        unit = f"{i * 3 + 1} mV"
        lines.append(f"{i},{amount},{volt},{unit}")
    (OUT / "non_numeric.csv").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
