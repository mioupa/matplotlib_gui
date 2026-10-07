# Matplotlib GUI

CSV / TXT / XLSX のデータから、ブラウザ上の操作だけで matplotlib の図を作るツールです。サーバーを使わず、Python（PyScript / Pyodide）をブラウザの中で実行します。

## 使い方

https://mioupa.github.io/matplotlib_gui/ を開いてください。`index.html` を `file://` で直接開く使い方には対応していません。

1. 「入力ファイル」で `.csv` / `.txt` / `.xlsx` を選びます。
2. 読み込みと描画は自動で行われます（「描画する」ボタンはありません）。設定を変えると、すぐ再描画されます。
3. 「描画系列」でX列・Y列・色などを選び、必要なら系列を追加します。
4. 「保存設定」でファイル名と形式を選び、「保存する」で書き出します。

対応する文字コードは UTF-8、UTF-8（BOM付き）、Shift_JIS（CP932）、EUC-JP です。判定した文字コードは、読み込み後に画面へ表示されます。

## 主な機能

- 系列カード（複数系列、X/Y列、色、線幅、線種、点サイズ、凡例名）と、第2Y軸
- プロット種別: line / scatter / bar
- 軸の対数表示と範囲指定、余白指定、主目盛線・副目盛線、凡例位置
- 保存: png / jpg / svg / pdf、背景透過
- データ確認タブ: 先頭100行を表示し、描画から除外される先頭行をグレーで表示
- Pythonコードタブ: 設定から生成した matplotlib のスクリプトを表示（下記）
- 数値に変換できず除外した値の警告、日本語のエラーメッセージ

## Pythonコードタブ

図は、設定から生成した Python スクリプトの実行で描いています。「Pythonコード」タブには、そのスクリプト全体（データの読み込みから保存まで）が表示されます。

- 設定を変えると、スクリプトも図と一緒に更新されます（「GUI と同期しています」）。
- 「コピー」でクリップボードへコピーし、「.py で保存」でファイルに書き出せます。ファイル名は「保存設定」のファイル名に `.py` を付けたものです。
- 「編集」を押すと、スクリプトを書き換えられます。「実行」（または Ctrl / Cmd + Enter）でそのコードを実行し、図を更新します。編集中は GUI の変更を図にもコードにも反映しません（「GUI と同期していません」）。「GUI から再生成」で、現在の設定から作ったコードに戻ります。
- `print` の出力と、エラー時の行番号付きトレースバックは、タブ内の「実行結果」に表示されます。

### 書き出した .py をローカルで実行する

1. 書き出した `.py` を、データファイルと同じフォルダに置きます（スクリプトは元のファイル名でデータを読みます）。
2. `pip install pandas matplotlib numpy` を実行します。`.xlsx` を読むときは `openpyxl` も入れます。
3. `python plot.py` で実行します（ファイル名は書き出した名前に読み替えてください）。

日本語フォントは、見つかったものを使います。無い場合も実行はできますが、日本語は豆腐（□）で表示されます。

## プライバシー

読み込んだデータの処理はすべてブラウザの中で行い、外部には送信しません。外部への通信は、ライブラリ（PyScript / Pyodide / pandas / matplotlib など）とフォントの取得だけです。通信先は次のとおりです。

| ホスト | 取得するもの |
|---|---|
| `pyscript.net` | PyScript 本体 |
| `cdn.jsdelivr.net` | Pyodide 本体と同梱パッケージ（pandas / matplotlib など）、画面用フォント（Noto Sans JP）、グラフ用の日本語フォント（Noto Sans CJK JP） |
| `files.pythonhosted.org` | openpyxl の wheel（`.xlsx` を初めて開くときだけ） |

初回の訪問では、Pyodide とライブラリ（数十 MB）と、日本語フォント（約 16 MB）をダウンロードするため、時間がかかります。2回目以降はキャッシュを使います（フォントはブラウザの Cache Storage に保存し、再ダウンロードしません）。

## 開発

開発用の依存は [uv](https://docs.astral.sh/uv/) で管理します（実行時には使いません）。

```sh
uv sync
uv run playwright install chromium
uv run pytest                 # 単体テスト
uv run pytest tests/e2e       # E2E テスト（Chromium で実際に動かす）
uv run python -m http.server  # ローカルで確認: http://localhost:8000/
uv run python tests/perf/bench.py --reps 5   # 起動・描画の計測（結果は docs/PERFORMANCE.md）
```

CI（GitHub Actions）は、push のたびに単体テストを、プルリクエストのたびに E2E テストを実行します。E2E は Pages と同じ Jekyll ビルドの結果を `/matplotlib_gui/` 配下で配信して検証します。

要件は `docs/REQUIREMENTS.md`、AI エージェント向けの引き継ぎ情報は `AGENTS.md` にあります。

## ライセンス

[LICENSE.md](LICENSE.md)（MIT License）を参照してください。
