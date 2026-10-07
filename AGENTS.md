# matplotlib GUI 引き継ぎ資料（AI エージェント向け）

要件の正は `docs/REQUIREMENTS.md`。このファイルと食い違う場合は REQUIREMENTS.md を優先する。
この資料は Phase 2（描画経路のコード生成化と Pythonコードタブの刷新）完了時点の実装を説明する。各 Phase の完了時に実装に合わせて更新すること（要件 A11）。

## 1. ゴールと前提

- CSV / TXT / XLSX のデータから、ブラウザ上の GUI だけで matplotlib の図を作る。
- 利用形態は GitHub Pages 配信（公開 URL: https://mioupa.github.io/matplotlib_gui/）。`file://` で直接開く使い方は非対応。
- サーバー処理を持たない。計算はすべてブラウザ内の Python（PyScript / Pyodide）で行う。GitHub Pages は静的配信のみに使う。
- 読み込んだデータは外部に送信しない。外部への通信はライブラリとフォントの取得だけ。
- 列の指定は列番号（`__idx__N`）で行う。同名の列があっても区別できる。
- 自動読込・自動描画を保つ（「読み込む」「描画する」ボタンは置かない）。
- 図は、設定から生成した Python スクリプトの実行だけで描く（描画経路は1本）。画面の図と、書き出した `.py` の結果は一致する。
- データ確認タブは、描画から除外される先頭行（`skipRows`）をグレー（`.skipped-row`）で表示する。
- CDN の URL はすべてバージョン固定にする。`tests/unit/test_cdn_pinning.py` が `index.html`・`js/`・`css/`・`py/` の全 URL を走査して強制する。

## 2. ファイル構成

| パス | 役割 |
|---|---|
| `index.html` | 画面のマークアップのみ。スクリプト読み込み失敗時の案内（`onerror`）を含む |
| `pyscript.toml` | PyScript 設定（パッケージ、`packages_cache`、`[files]` による Python ファイルの配置） |
| `css/style.css` | スタイル |
| `js/main.js` | エントリ。UI を設定オブジェクトに結び付ける |
| `js/defaults.js` | 設定の既定値（`DEFAULT_SETTINGS`）、色パレット（UD カラー） |
| `js/code-state.js` | Pythonコードタブの状態（モード `sync` / `edit`、直近に生成したコードとその世代）。設定オブジェクトには入れない |
| `js/state.js` | 設定オブジェクトの保持・更新・購読（`getSettings`、`setPath`、`updateSeries`、`addSeries`、`removeSeries`、`subscribe`、`toJson`） |
| `js/bridge.js` | Python（`window.mplgui`）の唯一の窓口。読込・描画・保存の制御、世代管理、フォント取得の起動 |
| `js/startup-progress.js` | Python 起動中の段階表示。Resource Timing（`PerformanceObserver`、取得済みエントリを含む）から Pyodide 本体（`pyodide.asm.wasm`・`python_stdlib.zip`）→ パッケージ wheel（pandas / matplotlib）→ 初期化（`/py/main.py` の取得）を推定する |
| `js/font-cache.js` | 日本語フォントの取得と Cache Storage への保存 |
| `js/ui/codeTab.js` | Pythonコードタブ（行番号、モード別のボタン、コピー、.py 保存、Ctrl/Cmd+Enter） |
| `js/ui/codeOutput.js` | 「実行結果」欄（`#codeOutput`）。print の出力とトレースバックを表示する |
| `js/ui/*.js`（上記以外） | 画面部品（`colorPicker`、`dataPreview`、`fileInfo`（選択中のファイル名と文字コードの表示）、`forms`、`notify`、`plotView`（画像と `data-summary`）、`progress`、`saveFormat`、`series`、`tabs`） |
| `py/main.py` | PyScript のエントリ。JS と `mplgui` の橋渡しだけを書く（`window.mplgui` の登録、Excel 用ライブラリの遅延導入、作業フォルダ `api.SESSION.workdir` の設定） |
| `py/mplgui/settings.py` | 設定スキーマ、既定値、検証、日本語エラー（凍結 dataclass へ変換） |
| `py/mplgui/loader.py` | バイト列から DataFrame（文字コード判定、区切り文字、プレビュー）。読込結果に `SourceInfo`（ファイル名、種別、文字コード、区切り文字、ヘッダの有無、xlsx のシート名）を付ける。codegen が生成スクリプトの読込部に使う |
| `py/mplgui/dataprep.py` | DataFrame を見て決める処理。`plan_plot` が描画計画 `PlotPlan` を作る（Y 列の自動割り当て、X の数値変換の要否、描ける点の有無、A7 の警告、データ由来の日本語 `UserError`） |
| `py/mplgui/codegen.py` | 設定・`SourceInfo`・`PlotPlan` から matplotlib スクリプトを生成する（`generate_script`）。純粋な関数 |
| `py/mplgui/formats.py` | 保存形式の表（`FORMATS`）、保存解像度（`SAVE_DPI` = 120）、`build_filename`、`savefig_kwargs`。runner と codegen が共有する |
| `py/mplgui/runner.py` | スクリプトの実行（`run_script` / `run_to_image`）、Figure → 画像（PNG/JPG/SVG/PDF）、図の要約（`figure_summary`）、実行時エラーの整形 |
| `py/mplgui/fonts.py` | 日本語フォントの登録と rcParams。フォント一覧 `SANS_SERIF_PRIORITY` が唯一の定義で、生成スクリプトの rcParams もこれを使う |
| `py/mplgui/errors.py` | `UserError`（利用者が直せるエラー） |
| `py/mplgui/api.py` | JS から呼ばれる JSON 入出力の関数。読込済みデータ（`SESSION`）と、アップロードしたファイルの作業フォルダへの書き出しを持つ |
| `py/mplgui/runtime.py` | 警告フィルタ（起動時） |
| `tests/unit/` | 単体テスト（CPython、Agg） |
| `tests/e2e/` | E2E テスト（pytest-playwright、Chromium）。`run_script_summary.py` は、生成スクリプトを CPython で実行して図の要約を出す補助（一致確認用） |
| `tests/fixtures/` | 合成テストデータ（`make_fixtures.py` が生成） |
| `tests/perf/bench.py` | 起動・描画の計測。結果は `docs/PERFORMANCE.md` |
| `.github/workflows/tests.yml` | CI |
| `_config.yml` | GitHub Pages（Jekyll）の include / exclude |

`py/mplgui/*` は `js` / `pyodide` に依存しない純粋なモジュールにする（CPython で単体テストできるようにするため）。DOM に触れるのは JS だけ。

## 3. 設定オブジェクト

- スキーマのバージョンは 1（`version`）。JSON のキーは camelCase。
- 唯一の正は JS 側（`js/state.js`）の設定オブジェクト。Python は DOM を読まず、渡された JSON を `settings.parse_settings` / `parse_load_settings` で凍結 dataclass に変換して使う。
- JS の既定値（`js/defaults.js`）と Python の既定値（`settings.default_settings()`）は一致させる。`tests/unit/test_defaults_parity.py` が比較する（node が無いと skip）。
- 主な構造: `load`（`delimiter`、`hasHeader`）、`plot`（`type`、`skipRows`、`xColumn`、`title`、`fontSize`、`figure`、`legend`、`grid`、`margins`）、`axes`（`x` / `y` / `y2`: `label`、`scale`、`min`、`max`）、`series[]`、`save`（`filename`、`format`、`transparent`）。
- 系列: `id`、`x`、`y`、`color`、`lineWidth`、`lineStyle`、`markerSize`、`label`、`secondaryAxis`。`markerSize: null` は「自動」（line は 0、scatter は 24）。ユーザーが数値を入れたら自動切替の対象外。
- Pythonコードタブの状態（モード `sync` / `edit`、生成したコード）は設定オブジェクトに入れず、`js/code-state.js` に持つ。スキーマは version 1 のまま。編集モードのコード本文は、`render` / `save` の別引数 `code` で渡す。「使用する」（`useCustomCode`）は廃止した。

## 4. Python ⇄ JS の API（`window.mplgui`）

Python が登録し、登録後に `mplgui-ready` イベントを送る。引数・戻り値は JSON 文字列（ファイルとフォントはバイト列）。

| 関数 | 引数 | 戻り値（`ok: true` のとき） |
|---|---|---|
| `ensureExcel()` | なし（非同期） | `{ok}`。初回の .xlsx 読込前に openpyxl を導入する |
| `loadFile(name, bytes, loadJson)` | ファイル名、内容、`{version, load}` | `{encoding, columns, preview, warnings}`（.xlsx は `encoding: null`） |
| `render(settingsJson, code)` | 設定 JSON、`code`（null または文字列） | `code` が null: `{image, code, output, summary, seriesCount, skipRows, warnings}`。文字列: `{image, output, summary}` |
| `save(settingsJson, code)` | 同上 | `{filename, mime, dataUri, output}` |
| `scriptFilename(saveFilename)` | 保存ファイル名の入力値 | 「.py で保存」のファイル名（文字列）。保存ファイル名と同じ規則（`formats.build_filename`）で拡張子を `.py` にする |
| `registerFont(bytes)` | フォントのバイト列 | `{registered}` |
| `fontStatus()` | なし | `{registered}` |

`defaultCustomCode()` は廃止した（Phase 2）。

- `code` が null（GUI 同期）: 設定から生成したスクリプトの「自動描画用」（§4.1）を、読込済みの DataFrame（`df`）を渡して実行する。`image` は PNG の data URI、`code` は表示用の完全なスクリプト、`output` は実行中の print / stderr、`summary` は `runner.figure_summary` の軸ごとの要約。読込済みデータが必要。`save` は保存設定の形式・背景透過・`SAVE_DPI`（120）で書き出す（`render` のプレビューは dpi 100）。
- `code` が文字列（編集モード）: そのスクリプトを丸ごと、アップロードしたファイルのある作業フォルダ（`SESSION.workdir`）で実行する。`render` は設定を読まない（設定が不正でも、読込済みデータが無くても動く）。`save` は設定を解釈したうえで、保存形式と背景透過だけを使う。GUI の設定をコードの結果に上書き適用することはしない（A8）。
- `loadFile` は、読み込んだファイルを元のファイル名（フォルダ部分は除く）で作業フォルダに書き出す（前のファイルは消す。失敗したら読込済みデータと書き出したファイルを破棄する）。こうして、表示中のスクリプトの `pd.read_csv("ファイル名", ...)` がそのまま動く（P5）。
- `warnings` は `{series, message}` の配列（読込時は文字列配列の場合もある。JS の `warningTexts` が吸収する）。
- 失敗: `{ok: false, error: {message, field?, detail?, traceback?, line?}, output?}`。
  - 利用者が直せる原因は `UserError`。`message` は日本語で、どの項目が悪いかを含める（`field`）。
  - それ以外の例外は内部エラー。短い日本語メッセージ（`INTERNAL_ERROR_MESSAGE`）に、`detail` として traceback を付ける（画面の「内部エラー詳細」に出る）。
  - スクリプトの実行時エラーは `runner.ScriptError`。`message` は日本語の要約（編集モードは「N行目、エラーの型: 日本語の説明」入り）、`traceback` は `plot.py` の行だけのトレースバック、`line` は最後の `plot.py` の行番号、`detail` は完全な traceback。トップレベルの `output` は、失敗するまでの print の出力（`output` 属性を持つ例外だけ）。
  - GUI 同期で生成コードの実行が失敗したときは、行番号から失敗した手順（`GeneratedScript.step_for_line`）を引き、手順ごとの日本語メッセージ（`field` 付き）に置き換える（`api._step_error`）。手順に当たらなければ `GENERIC_ERROR_MESSAGE`。
- `render` は読込済みデータが無いと（GUI 同期のとき）「先にファイルを読み込んでください。」を返す。

## 4.1 コード生成（Phase 2）

描画経路は1本: 設定 → `dataprep.plan_plot`（データを見て決める処理と検査）→ `codegen.generate_script`（スクリプトの文字列）→ `runner`（実行して Figure を得て画像にする）。GUI の図と、書き出す `.py` は同じコードから作る。

- `dataprep.plan_plot(df, settings)`: `skipRows` の適用、Y 列の自動割り当て、X の数値変換の要否、描ける点があるか、数値に変換できず除外した値の警告（A7）を決める。データ由来の問題は日本語の `UserError`（列が範囲外、除外行数が多すぎる、描ける数値データが無い、など）にする。結果は凍結 dataclass の `PlotPlan` / `SeriesPlan`。
- `codegen.generate_script(settings, source, plan)` は `GeneratedScript`（`text`、`load_lines`、`output_lines`、`steps`）を返す。純粋な関数で、データには触れない。
- スクリプトの構成: ヘッダ（使い方、`import`、日本語フォントの rcParams、`FONT_SIZE`）→ `1. データの読み込み`（`DATA_FILE`、`pd.read_csv` / `pd.read_excel`。文字コード、区切り文字、ヘッダ、シート名を明記）→ `2. 描画に使う行`（`skipRows`）→ `3. 図と軸`（`fig, ax`）→ `4. 系列` → `5. 軸（ラベル・スケール・範囲・目盛）` → `6. グリッドと凡例` → `7. 余白` → `8. 保存と表示`（`fig.savefig(...)` と `plt.show()`）。各セクションの見出しは `# ==== 番号. タイトル ====`。
- 変数名は、`df`（データ）、`fig` / `ax` / `ax2`（第2Y軸）、系列ごとの `x` / `y` / `ok`（欠けた行を除くマスク）、棒グラフ（複数系列）の `bar_data` / `positions` / `x_labels` / `width`。列は常に `df.iloc[:, N]`（列番号）で参照し、GUI で選んだ列名と番号はコメントに書く（同名の列を区別できる）。列名はコードに入れない。
- 自動描画用の変種（`GeneratedScript.auto_render_text`）: 「データの読み込み」と「保存と表示」の行を空行にしたもの。行番号は表示中のスクリプトと同じなので、トレースバックの行番号がそのまま使える。GUI の自動描画は、これに読込済みの `df` を渡して実行する（ファイルを読み直さない）。
- 手順（`Step`）: 失敗しうる行の範囲と日本語メッセージ（`field` 付きのものもある）の対応表。系列の描画（`GENERIC_ERROR_MESSAGE`）、軸のスケール・範囲（X / Y / 第2Y）、`tight_layout`、`subplots_adjust`（余白）を登録している。
- **安全性（必須）**: 列名・タイトル・ラベル・色・ファイル名・文字コードなどは信頼できない入力で、実行されるコードに入る。値は必ず `literal()`（str / int / 有限の float / bool / None だけを `repr` で出す。他の型は例外）を通して書き出し、コメントに入れる文字列は必ず `comment_text()`（改行・制御文字を空白にする）を通す。f 文字列などで、これ以外の方法で信頼できない文字列をコードに埋め込まないこと。`tests/unit/test_codegen.py` の注入テストが検査する。
- GUI の設定を、ユーザーが編集したコードの結果に上書き適用しない（A8）。編集モードのコードは、設定を使わずそのまま実行する。
- 機能追加（Phase 3〜5）の手順: 描画の種類は `SERIES_EMITTERS`（プロット種別 → 系列の出力関数）に追加する。出力関数は `_Builder` に行を足し、失敗しうる行は `with b.step(メッセージ, field)` で包む。軸・グリッド・余白などは対応する `_emit_*` 関数に足す。データを見ないと決められないこと（列の割り当て、変換の要否、警告、データ由来のエラー）は `dataprep` の `PlotPlan` / `SeriesPlan` に項目を足して渡す。設定項目を足すときは JS の `defaults.js` と `settings.py` の両方に足す。生成するコードは pandas / matplotlib / numpy だけを使う（ローカルの Python でそのまま動かすため）。新しい行を足したら、単体テストで「全体を実行した図」と「自動描画用の図」が一致することも確かめる。
- 生成スクリプトの保存ファイル名（`savefig` の引数）は `formats.build_filename` で決める。保存形式と解像度は `formats.savefig_kwargs` / `SAVE_DPI` で、GUI の「保存」と同じにする。

### runner（スクリプトの実行）

- `run_script(code, injected=, cwd=)` はコンテキストマネージャ。`matplotlib.rc_context()` の中で実行し、スクリプトが変えた rcParams を次の実行に持ち越さない。`cwd` を指定すると実行中だけ作業フォルダを移す（終了後に戻す）。
- stdout と stderr は1つのバッファに集めて `output` として返す。
- 図の選び方: 名前空間の `fig`（`Figure` のとき）を優先し、無ければ実行中に新しく作られた最後の図。どちらも無ければ「図が作られませんでした。」（`UserError`）。
- 実行中に作られた図は、`with` を抜けるときにすべて閉じる（呼び出し側は `with` の中で画像にする）。`linecache` の登録も消す。
- 失敗: `compile` エラーも実行時の例外も `SystemExit`（`exit()`）も `ScriptError` にする。トレースバックは `plot.py` のフレームだけを残し、メッセージには日本語の説明（`japanese_hint`。インデント、文法、`NameError`、`FileNotFoundError`、`ImportError` など）を付ける。
- `plt.show()` は Agg では何もせず警告を出すので、スクリプトの実行中だけ、この警告（`FigureCanvasAgg is non-interactive, and thus cannot be shown`）を無視する（§8）。

## 5. 描画パイプライン

- 描画は設定変更の 250 ms 後（デバウンス）。読込は、ファイル選択・ヘッダ変更で 0 ms、区切り文字の変更で 450 ms 後。保存設定（`save.*`）の変更では再描画しない。`skipRows` の変更は Python を呼ばず、データ確認表のグレー表示だけ即時に更新する。
- 起動中の `#progress`（`aria-live="polite"`）は段階表示: 「Python 実行環境を読み込み中…」→「ライブラリを読み込み中…（pandas ✓, matplotlib …）」→「ライブラリを初期化中…」→ 準備完了で消える（フォント取得の表示が続く場合あり）。`<html>` の `data-startup-stage`（`runtime` / `packages` / `init` / `ready`）に現在の段階が入る。新しい id は無い。読込失敗の案内（`data-load-failed`）は上書きしない。
- 描画要求には世代番号を付ける。Python の描画は同時に最大1つ。実行中に新しい要求が来たら「やり直し」の印だけ付け、終了後に最新の設定で1回だけ描く（合流）。古い世代の結果は画像にもステータスにも反映しない。
- Python の起動前に選んだファイルや変えた設定は保持し、起動後に最新の内容で1回読み込んで描く（起動キュー）。
- Pythonコードタブのモード（`js/code-state.js`）:
  - `sync`: GUI の設定から生成したスクリプトを表示し、描画に成功するたびに更新する。
  - `edit`: 利用者が書き換えたコードを「実行」（Ctrl/Cmd+Enter）したときだけ描く。GUI の変更でも、ファイルの読込でも自動では描かず、コードも更新しない（ステータスに warning で「編集中のため反映されません」と出す）。読込は行い、ファイルは作業フォルダに置かれる。フォント取得後の描き直しも、実行したことがあるときだけ行う。
  - 「編集」で `edit`、「GUI から再生成」で `sync` に切り替える。切り替えのたびに、予約中・実行中の描画を無効にする（世代を進め、結果は画像にもコードにもステータスにも反映しない）。このため `data-render-generation` は、モード切替の直後に、表示中の画像の世代より先に進んだままになることがある。E2E は `tests/e2e/helpers.py` の専用ヘルパー（`wait_code_generated`、`wait_image_generation_changed`、`run_edited_code`、`wait_run_finished`）で待つこと。
  - `sync` の描画は読込済みデータが必要。`edit` は Python が動いていればよい（コードが自分でファイルを読む）。
- E2E が使う状態は `<html>` の data 属性: `data-app-state`（`starting` / `ready` / `failed`）、`data-data-state`（`none` / `loading` / `ready` / `error`）、`data-render-state`（`idle` / `pending` / `rendering`）、`data-render-generation`、`data-font-state`（`idle` / `loading` / `ready` / `failed`）、`data-load-count`。表示中の画像は `#plotArea img` の `data-generation` と `data-summary`（`figure_summary` の JSON）を持つ。ステータスは `#status` の `data-kind`。Pythonコードタブ用に、`<html>` の `data-code-mode`（`sync` / `edit`）、`#customPyCode`（textarea）の `data-generation`（表示中のコードを生成した世代。GUI 同期のとき、同じ世代の画像と対応する）、`#codeOutput` の `data-kind`（`ok` / `error`）、`#codeSyncStatus` の `data-state`（`sync` / `edit`）がある。

## 6. 起動とフォント

- PyScript 2026.7.3（Pyodide 314.0.3 / Python 3.14）。`pyscript.toml` は `packages = ["pandas", "matplotlib"]`、`packages_cache = "passthrough"`（micropip を使わない）。
- openpyxl と et_xmlfile は Pyodide 同梱ではないので、初めて .xlsx を読むときに `py/main.py` が、バージョン固定の wheel URL（`files.pythonhosted.org`）を `pyodide_js.loadPackage` に渡して導入する。起動時には導入しない。
- matplotlib のバックエンドは Agg（`py/main.py` で `matplotlib.use("Agg")`。pyplot を import する前に指定する）。
- 日本語フォントは固定 URL の jsDelivr（`noto-cjk@Sans2.004` の `NotoSansCJKjp-Regular.otf`、約16 MB）から取得し、Cache Storage（キャッシュ名 `mplgui-fonts-v1`）に保存する。2回目以降の訪問ではダウンロードしない。取得はセッション中1回で、失敗しても再試行せず、警告を1度だけ出してフォールバックフォントで続行する。
- フォント取得は、進みが 20 秒止まる（ヘッダが届かない、または本文が進まない）と失敗扱いにする（`FONT_STALL_MS`）。
- 最初の描画はフォント取得を最大 8 秒待つ（`FONT_FIRST_RENDER_WAIT_MS`）。超えたらフォールバックフォントで描き、取得が終わったら現在の設定で1回だけ描き直す。
- テスト専用に、`window.__MPLGUI_TEST_OVERRIDES__ = {fontStallMs, fontFirstRenderWaitMs}` で上の時間を短縮できる。

## 7. 文字コード判定・数値変換警告・ステータス

- 文字コード（`loader.detect_encoding`）: BOM 付きなら utf-8-sig → UTF-8 → CP932 と EUC-JP。両方でデコードできるときは、半角カナ・私用領域・制御文字などの「文字化けらしい文字」が少ないほうを採用し、同数なら CP932。どれでも読めなければ日本語のエラーにする。判定結果は `#encodingLabel` に表示する。
- 数値に変換できず除外した値は、系列ごとに警告にする（`dataprep.dropped_warning`。`dataprep.plan_plot` が集める）。
- ステータス（`#status`）の種別は `ok` / `warning` / `error`。警告は成功メッセージに添えて表示し、`error` のときは `data-kind="error"`。日本語フォント取得失敗のような常時有効な警告は、以後の表示にも添える。

## 8. 警告フィルタ

無視する警告は、次の3つだけ。それ以外の警告は無視しない（A10）。

- pandas の pyarrow 関連の `DeprecationWarning`（`runtime.configure_warnings`、起動時）
- matplotlib のグリフ不足の `UserWarning`（`runtime.configure_warnings`、起動時）
- `plt.show()` が Agg で出す `UserWarning`（`FigureCanvasAgg is non-interactive, and thus cannot be shown`）。生成スクリプトも `plt.show()` で終わるため、`runner._execute` の中だけ、`warnings.catch_warnings()` の範囲で無視する（スクリプトの実行が終われば元に戻る。グローバルには設定しない）。

## 9. parentNode エラー

旧実装は `parentNode` を含むエラーを JS / Python の両側で抑制・回復していた。Phase 1 でオーナーの承認を得て削除した。原因は、旧 `matplotlib_pyodide` バックエンドが、表示されなかった Figure の破棄時に起こしていたこと。PyScript 2026.7.3 と Agg の組み合わせでは発生しない。エラーを一括で握りつぶす処理は再導入しないこと（再現した場合は、原因を調べて範囲を絞る）。

## 10. テスト

```sh
uv sync
uv run playwright install chromium
uv run pytest                  # 単体テスト（tests/unit）
uv run pytest tests/e2e        # E2E（Chromium とローカルの静的サーバー）
```

- 新しい機能には単体テストを必ず追加する。
- 単体テスト（`tests/unit/`）のうち Phase 2 で加えたもの:
  - `test_codegen.py`: 生成したスクリプトを CPython で実際に実行し、期待する artist（線、点、棒、凡例、軸範囲、ラベルなど）を検査する。「全体を実行した図」と「自動描画用の変種に `df` を渡した図」の要約が一致することも確かめる。読込部が `loader` と同じ結果になること、列名・タイトルなどに悪意のある文字列を入れてもコードを注入できないこと（`literal` / `comment_text`）も検査する。
  - `test_dataprep.py`: 描画計画（Y 列の自動割り当て、X の変換、除外値の警告、データ由来のエラー）。
  - `test_runner.py`: `run_script`（出力の捕捉、図の選び方、図と `linecache` の後始末、rcParams の分離、作業フォルダ、`plt.show()` の警告、エラーの行番号・日本語の説明）と画像出力。
  - `test_fonts.py`: フォント一覧が生成スクリプトと rcParams で共通であること。`test_api.py`: 新しい `render` / `save` / `loadFile`（作業フォルダへの書き出し）/ エラーの形。
- E2E（`tests/e2e/`）のうち Phase 2 で加えたもの: `test_code_tab.py`（同期表示、GUI 変更への追従、コピー、.py 保存、編集・実行、編集中の GUI 変更が反映されないこと、「GUI から再生成」、Ctrl/Cmd+Enter、トレースバックと print の表示、編集モードでの保存、狭い画面）、`test_codegen_consistency.py`（下記）。
- 生成コードの一致確認（要件 7 章）: `test_codegen_consistency.py` が、ブラウザで設定した図（line / scatter / bar）の `.py` を実際にダウンロードし、`tests/fixtures` のデータと同じフォルダに置いて CPython で実行する（`run_script_summary.py` が `MPLBACKEND=Agg`、`PYTHONPATH=py` で実行して `figure_summary` を出力する）。その要約を、ブラウザの画像の `data-summary` と比べる（系列数、軸範囲、ラベル、凡例、スケール、棒グラフの目盛ラベル）。フォントは環境で違うので、画素やレイアウトは比べない。
- E2E は要素を id だけで選ぶ。`index.html` の id は安定させ、変えるときはテストも直す。アプリ固有の待機・操作は `tests/e2e/helpers.py` にまとめる。
- テストデータは `tests/fixtures/` の合成データだけ（公開リポジトリなので実データを置かない）。
- テスト用サーバー（`tests/e2e/server.py`）は listen backlog を 128 に広げている。既定の 5 だと、Chromium が ES モジュールを一斉に取得したときに接続が切れて、アプリが起動しないことがある。
- 環境変数 `E2E_BASE_PATH=/matplotlib_gui/` を付けると、Pages と同じサブパス配下で配信して検証する（絶対パス参照の検出）。`E2E_SERVE_DIR` で配信ディレクトリを変えられる（CI は Jekyll のビルド結果 `_site`）。

## 11. CI と GitHub Pages

- CI（`.github/workflows/tests.yml`）: push で単体テスト、プルリクエストで E2E。E2E は Jekyll でビルドした `_site` を `/matplotlib_gui/` 配下で配信して検証する。
- Jekyll は `_` で始まるファイルを既定で配信しない。`__init__.py` は `_config.yml` の `include` で明示している。開発用ファイル（`docs/`、`tests/`、`AGENTS.md`、`pyproject.toml`、`uv.lock`、`.github/` など）は `exclude`。
- 新しい Python モジュールを追加したら、`pyscript.toml` の `[files]` に必ず追加する（`tests/unit/test_pages_publish.py` が参照ファイルの公開を確認する）。
- matplotlib 3.10 では `tight_layout()` 後に `PlaceHolderLayoutEngine` が残り、`savefig` が余分に全体を再描画する。`runner.drop_placeholder_layout_engine` がこれを外している（出力は同一）。

## 12. 運用ルール（必須）

- このリポジトリ配下のみを対象に作業する。リポジトリ外のファイルには触れない。
- push やプルリクエストの作成は、オーナーの確認を取ってから行う。
- ローカル環境のパスを、リポジトリ内の文書やコードに書かない。

## 13. Phase 2 でオーナーが決めたこと（2026-10-08）

- 旧「Pythonコード(beta)」タブの名前空間（`get_plot_data`、従来形式の settings dict、`plotted_count`）は、互換を残さずに廃止した。
- 生成スクリプトの最後は `fig.savefig(...)`（GUI の「保存」と同じ形式・解像度）と `plt.show()`。
- 編集は明示的な「編集」ボタンで始める。`useCustomCode`（「使用する」）は廃止した。編集中は GUI の変更で、コードも図も変わらない。
- 棒グラフ（1系列・複数系列）は、カテゴリの目盛ラベルを保つ（Phase 1 の不具合を修正）。複数系列は、棒の位置にラベルを付ける（25個を超えたら間引く）。
- line / scatter で X が数値でない列（文字列・日時）のとき、Phase 1 と同じ見た目を保つため、生成コードに `ax.set_xscale("linear")` を入れる（目盛は位置の番号になる）。D5（日付軸）で見直す（Phase 4）。
- ファイル選択欄に、選んだファイル名を欄の中に表示する（`#fileNameLabel`。`input` は選択のたびに空に戻すため、JS が表示する）。
