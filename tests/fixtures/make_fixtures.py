"""テスト用の合成データを決定的に生成する。実データは一切含まない。

実行: uv run python tests/fixtures/make_fixtures.py
"""
import math
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

    (OUT / "tab.txt").write_bytes(csv_text(header, data, sep="\t").encode("utf-8"))

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
    wb.save(OUT / "multi_sheet.xlsx")

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
