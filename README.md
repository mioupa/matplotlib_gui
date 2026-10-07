# Matplotlib GUI

CSV / TXT / XLSX のデータから、ブラウザ上の操作だけで matplotlib の図を作るツールです。サーバーを使わず、Python（PyScript / Pyodide）をブラウザの中で実行します。

## 使い方

https://mioupa.github.io/matplotlib_gui/ を開いてください。`index.html` を `file://` で直接開く使い方には対応していません。

1. 「入力ファイル」で `.csv` / `.txt` / `.xlsx` を選びます。
2. 読み込みと描画は自動で行われます（「描画する」ボタンはありません）。設定を変えると、すぐ再描画されます。
3. 「描画系列」でX列・Y列・色などを選び、必要なら系列を追加します。
4. 「体裁」でフォント・図のサイズ・プリセットなどを整えます。
5. 「保存」でファイル名・形式・DPI を選び、「保存する」で書き出すか、「クリップボードにコピー」で他のアプリに貼り付けます。

左の設定パネルは「データ読み込み」「系列」「軸・目盛」「体裁」「保存」の区分に分かれていて、見出しを押すと折りたためます（折りたたみの状態は、このブラウザに覚えておきます）。

対応する文字コードは UTF-8、UTF-8（BOM付き）、Shift_JIS（CP932）、EUC-JP です。判定した文字コードは、読み込み後に画面へ表示されます。

## 主な機能

- 系列カード（複数系列、X/Y列、色、線幅、線種、点サイズ、凡例名）と、第2Y軸
- プロット種別: line / scatter / bar
- 軸の対数表示と範囲指定、余白指定、主目盛線・副目盛線、凡例位置
- 保存: png / jpg / svg / pdf、背景透過。PNG・JPG は保存 DPI（72 / 150 / 300 / 600 または任意の値。既定は 300）を指定できます。プレビューは 100 dpi で表示します
- PDF は文字をフォントとして埋め込みます（Type 42）。Illustrator などで文字を編集できます。SVG は、文字を「パスに変換」（既定。どの環境でも同じ見た目）か「テキストのまま」（編集できる。開く環境に同じフォントが無いと見た目が変わります）から選べます
- 図のサイズ: inch / cm / mm で指定（単位を切り替えると、図の大きさを変えずに数値を換算します）
- スタイルプリセット（標準 / 論文1段組 / 論文2段組 / スライド16:9）: 「適用」で、図のサイズ・フォントサイズ・線幅・点サイズをまとめて設定します
- カラーパレット（UD カラー / tab10 / グレースケール）: 切り替えると、すべての系列の色を、系列の順に新しいパレットの色へ塗り直します
- 欧文フォント: 標準（Noto Sans JP）、Arimo（Arial 互換）、Tinos（Times 互換）。英数字と記号だけを選んだフォントで書き、日本語は Noto Sans JP で書きます（Tinos のときは数式も Times 系の字形になります）
- クリップボードへのコピー: プレビュー中の図を、保存 DPI の PNG として画像でコピーします（背景透過は保存設定に従います）。対応ブラウザは Chrome / Edge 98 以降、Safari 13.1 以降、Firefox 127 以降で、https で開いている必要があります。非対応のときは「保存する」で PNG を保存してください
- 数式・上付き・下付き: タイトル・軸ラベル・凡例名で、`$` で囲んだ部分が数式になります。例: `m$^2$`（上付き）、`H$_2$O`（下付き）、`$\alpha$`（ギリシャ文字）。`$` を文字として書くときは `\$` とします。書き方を間違えると、日本語のエラーが表示されます
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

日本語フォントは、見つかったものを使います。無い場合も実行はできますが、日本語は豆腐（□）で表示されます。欧文フォントを選んだ図は、Arimo / Tinos（または Arial / Times New Roman、Liberation）が入っていればそれを使い、無ければ日本語フォントで書きます。PDF の文字は TrueType 形式のフォントなら正しく埋め込まれます。macOS のヒラギノなど OpenType（CFF）形式のフォントでは、PDF の文字が正しく表示されないことがあります。そのときは Noto Sans JP（TrueType 版）を入れてください。

## プライバシー

読み込んだデータの処理はすべてブラウザの中で行い、外部には送信しません。外部への通信は、ライブラリ（PyScript / Pyodide / pandas / matplotlib など）とフォントの取得だけです。通信先は次のとおりです。

| ホスト | 取得するもの |
|---|---|
| `pyscript.net` | PyScript 本体 |
| `cdn.jsdelivr.net` | Pyodide 本体と同梱パッケージ（pandas / matplotlib など）、画面用フォント（Noto Sans JP）、グラフ用のフォント（日本語の Noto Sans JP、選んだときだけ Arimo / Tinos） |
| `files.pythonhosted.org` | openpyxl の wheel（`.xlsx` を初めて開くときだけ） |

初回の訪問では、Pyodide とライブラリ（数十 MB）と、日本語フォント（約 5.7 MB）をダウンロードするため、時間がかかります。欧文フォントは、選んだときだけ取得します（各 約 0.3〜0.5 MB）。2回目以降はキャッシュを使います（フォントはブラウザの Cache Storage に保存し、再ダウンロードしません）。

## フォントとライセンス

グラフに使うフォントは、実行時に jsDelivr から取得します（このリポジトリには含めていません）。いずれも SIL Open Font License 1.1 です。

| フォント | 用途 | ライセンス全文 |
|---|---|---|
| Noto Sans JP（TrueType 版） | グラフの日本語、画面用のフォント | https://cdn.jsdelivr.net/npm/@expo-google-fonts/noto-sans-jp@0.4.4/LICENSE_FONT |
| Arimo | 欧文フォント（Arial 互換） | https://cdn.jsdelivr.net/npm/@expo-google-fonts/arimo@0.4.3/LICENSE_FONT |
| Tinos | 欧文フォント（Times 互換） | https://cdn.jsdelivr.net/npm/@expo-google-fonts/tinos@0.4.2/LICENSE_FONT |

画面用の Web フォントは、`@fontsource/noto-sans-jp@5.3.0`（Noto Sans JP、同じく SIL OFL 1.1）を jsDelivr から読み込みます。グラフの日本語に TrueType 版を使うのは、PDF に文字をフォントとして埋め込む（Type 42）には TrueType 形式が必要なためです。

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
