# テスト用データ

すべて `make_fixtures.py` が生成する**合成データ**です（実データは含みません）。再生成: `uv run python tests/fixtures/make_fixtures.py`

| ファイル | 内容・目的 |
|---|---|
| `utf8.csv` | UTF-8、カンマ区切り、ヘッダ行あり。列名は 時間 / 電圧 / 電流（基本ケース） |
| `utf8_bom.csv` | BOM 付き UTF-8。先頭列名に不可視文字が残らないか |
| `cp932.csv` | cp932。機種依存文字（①、㈱）を含み、厳密な shift_jis では読めない |
| `euc_jp.csv` | EUC-JP（漢字・ひらがな含む備考列つき）。cp932 と誤判定されないこと |
| `tab.txt` | タブ区切りのテキスト |
| `multi_sheet.xlsx` | 2 シート（Sheet1 / 二枚目）で内容が異なる |
| `duplicate_columns.csv` | 同名の列（温度）が 2 つあり値が異なる（列番号指定の確認） |
| `non_numeric.csv` | 「1,234」形式の数値、「12 mV」のような単位付き、N/A、空欄が混在 |
| `growth.csv` | 時間 / 指数 / 線形。値はすべて正（対数軸で描ける）。生成コードの一致確認用 |
| `categories.csv` | 品目（文字列）/ 売上A / 売上B。文字列カテゴリの棒グラフ用 |
| `preamble.csv` | 先頭に説明の行が3行（3行目はカンマの数が違う。skipLines 無しでは列数の不整合で読めない）。skipLines=3 で読める |
| `european.csv` | 区切り `;`、小数点 `,`、桁区切り `.`（`1.234,5`、負の値あり） |
| `thousands.csv` | カンマ区切りで、引用符付きの桁区切り（`"1,234"`、負の値あり） |
| `comments.csv` | `#` の行全体のコメントと、データ行末尾の `# note` |
| `preamble.xlsx` | 2 シート（データ / 説明つき）。2 枚目は見出しの前に説明が2行 |
