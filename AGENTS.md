# matplotlib GUI 引き継ぎ資料（AI エージェント向け）

要件の正は `docs/REQUIREMENTS.md`。このファイルと食い違う場合は REQUIREMENTS.md を優先する。
この資料は Phase 4（データ取り込み: ドラッグ&ドロップ・貼り付け・シート選択・読み込み設定（ヘッダ前の読み飛ばし・桁区切り・小数点・コメント記号）・日時の列と日時軸・複数ファイル）完了時点の実装を説明する。各 Phase の完了時に実装に合わせて更新すること（要件 A11）。

## 1. ゴールと前提

- CSV / TXT / TSV / XLSX のデータから、ブラウザ上の GUI だけで matplotlib の図を作る。
- 利用形態は GitHub Pages 配信（公開 URL: https://mioupa.github.io/matplotlib_gui/）。`file://` で直接開く使い方は非対応。
- サーバー処理を持たない。計算はすべてブラウザ内の Python（PyScript / Pyodide）で行う。GitHub Pages は静的配信のみに使う。
- 読み込んだデータは外部に送信しない。外部への通信はライブラリとフォントの取得だけ（フォントは日本語の Noto Sans JP（TrueType 版）、選んだときだけ欧文の Arimo / Tinos。画面用の Web フォントは fontsource の Noto Sans JP）。
- 列の指定は列番号（`__idx__N`）で行う。同名の列があっても区別できる。
- 自動読込・自動描画を保つ（「読み込む」「描画する」ボタンは置かない）。
- 図は、設定から生成した Python スクリプトの実行だけで描く（描画経路は1本）。画面の図と、書き出した `.py` の結果は一致する。
- データ確認タブは、描画から除外される先頭行（`skipRows`）をグレー（`.skipped-row`）で表示する。ヘッダより前に読み飛ばした行（`load.skipLines`）は、表の上に枠で囲んで別に表示する（`#dataPreamble`。グレー表示とは見た目を分ける）。
- 保存 DPI（既定 300）、図サイズの単位（inch / cm / mm）、欧文フォント、スタイルプリセット、カラーパレット、クリップボードへのコピー、数式（mathtext）の案内が加わった。いずれも設定 → 生成コード → 実行の1本の経路に載る（GUI だけの特別扱いは無い）。
- Phase 4 でデータの取り込みが広がった。ファイルのドラッグ&ドロップ（ページ全体）と表の貼り付け（`pasted_data.tsv` として扱う）、`.tsv`、xlsx のシート選択、ヘッダより前に読み飛ばす行数、桁区切り・小数点・コメント記号、日時の列の自動認識と日時軸（X 軸の表示書式）、複数ファイル（最大10個。系列ごとにデータ元を選ぶ）。読込の引数は、生成コードの読込部にすべて明記する（区切り文字などの自動判定は足していない）。いずれも設定 → 生成コード → 実行の1本の経路に載る。
- CDN の URL はすべてバージョン固定にする。`tests/unit/test_cdn_pinning.py` が `index.html`・`js/`・`css/`・`py/` の全 URL を走査して強制する。取得しない説明リンクの `matplotlib.org` は、バージョンを含むパス（`/3.10.8/...`）だけ許可する。

## 2. ファイル構成

| パス | 役割 |
|---|---|
| `index.html` | 画面のマークアップのみ。スクリプト読み込み失敗時の案内（`onerror`）を含む |
| `pyscript.toml` | PyScript 設定（パッケージ、`packages_cache`、`[files]` による Python ファイルの配置） |
| `css/style.css` | スタイル |
| `js/main.js` | エントリ。UI を設定オブジェクトに結び付ける |
| `js/defaults.js` | 設定の既定値（`DEFAULT_SETTINGS`、`SCHEMA_VERSION` = 3）、UD カラーの色（`PALETTE`） |
| `js/units.js` | 図サイズの単位（`UNITS`、`UNIT_NAMES`、`UNIT_STEP`）と換算 `convertLength(value, from, to)`（mm を介し、to の単位で丸める: in 3 桁 / cm 2 桁 / mm 1 桁）。純粋な ES module |
| `js/palettes.js` | カラーパレット（`PALETTES`: `ud` / `tab10` / `gray`）、`getPalette`、`paletteColor(id, index)`。id は `settings.PALETTES` と一致させる。色は JS だけが持つ |
| `js/presets.js` | スタイルプリセット（`PRESETS`: standard / paper1 / paper2 / slide）、`planPreset`（適用内容を計算するだけ）、`newSeriesDefaults`（直前のプリセットを新しい系列へ）。名前は設定に入れない |
| `js/code-state.js` | Pythonコードタブの状態（モード `sync` / `edit`、直近に生成したコードとその世代、「最新でない」印 `isCodeStale` / `setCodeStale`）。設定オブジェクトには入れない |
| `js/state.js` | 設定オブジェクトの保持・更新・購読（`getSettings`、`setPath`、`updateSeries`、`addSeries`、`removeSeries`、`applyPalette`、`setFileSheet`、`setLastPreset` / `getLastPreset`、`subscribe`、`toJson`）。直近に適用したプリセットはセッション中だけここに持つ |
| `js/bridge.js` | Python（`window.mplgui`）の唯一の窓口。読込・描画・保存・コピー（`makeClipboardImage`）・コードだけの更新（`script`）の制御、世代管理、日本語・欧文フォント取得の起動と待ち。読み込んだファイル（データN）ごとの状態（`File`・バイト列・貼り付けか・`loading` / `ready` / `error`・結果）を持ち、ファイルの追加・置き換え・削除（`selectFiles` / `selectFile` / `removeFile`）、読込の予約（`scheduleLoad`。ファイルごと）、最後のファイルを外したときの初期状態への復帰、コードの「最新でない」印を扱う |
| `js/startup-progress.js` | Python 起動中の段階表示。Resource Timing（`PerformanceObserver`、取得済みエントリを含む）から Pyodide 本体（`pyodide.asm.wasm`・`python_stdlib.zip`）→ パッケージ wheel（pandas / matplotlib）→ 初期化（`/py/main.py` の取得）を推定する |
| `js/font-cache.js` | フォントの取得と Cache Storage への保存。種類（`japanese` / `arimo` / `tinos`）ごとの URL（`FONT_URLS`）、種類ごとに1セッション1回の取得、旧 OTF のキャッシュ削除 |
| `js/ui/codeTab.js` | Pythonコードタブ（行番号、モード別のボタン、コピー、.py 保存、Ctrl/Cmd+Enter） |
| `js/ui/codeOutput.js` | 「実行結果」欄（`#codeOutput`）。print の出力とトレースバックを表示する |
| `js/ui/loadSection.js` | データ読み込み区分のシート選択（`#sheetGroup` / `#sheetSelect`。xlsx のときだけ表示し、選んだシートは `load.files` に書く） |
| `js/ui/dropPaste.js` | ファイルのドロップ（ページ全体。`#dropOverlay` と、`#dropLoad` / `#dropReplace` / `#dropAdd` の区画）、表の貼り付け（`#pasteArea` とページ上の paste）、「貼り付けたデータを保存（.tsv）」（`#savePastedBtn`）。どれも `bridge.js` の `selectFiles` / `selectFile` に渡すだけ |
| `js/ui/fileList.js` | 2ファイル以上のときのファイル一覧（`#fileList`。各行 `file-<id>`・シートの選択・削除）と、データ確認タブの表示元の切替（`#previewSource`）。`bridge.js` が作る表示用のデータを描くだけ |
| `js/ui/dateFormat.js` | 軸・目盛区分の X 軸の日時の書式（`#xDateFormat` のプリセットと「任意」の `#xDateFormatCustom`）。値は `axes.x.dateFormat` に書く。表示の可否（`#xDateFormatGroup`）は `series.js` が決める |
| `js/ui/panelSections.js` | 設定パネルの区分（`details.panel-section`）の折りたたみ。状態は localStorage（キー `mplgui.panelSections`、`{区分の id: 開いているか}`）だけに持ち、設定オブジェクトには入れない。localStorage が使えなくても動く（すべて開く） |
| `js/ui/styleSection.js` | 体裁区分: プリセットの「適用」、カラーパレット、図サイズの単位切替（数値を換算し、ラベルと step を単位に合わせる） |
| `js/ui/saveSection.js` | 保存区分: DPI（72 / 150 / 300 / 600 のセレクトと「任意」の入力欄）。値は `save.dpi`（数値）に書く |
| `js/ui/clipboard.js` | 「クリップボードにコピー」。`<html data-copy-state>` を更新する |
| `js/ui/*.js`（上記以外） | 画面部品（`colorPicker`、`dataPreview`（先頭100行、前置き行の枠、日時の列の印）、`fileInfo`（選択中のファイル名と文字コードの表示）、`forms`、`notify`、`plotView`（画像と `data-summary`）、`progress`、`saveFormat`（形式に応じた透過の可否と、SVG の文字・PDF の説明の出し分け）、`series`（系列カード。複数ファイルのときはデータ元の選択と、データ元ごとの列の選択肢。X の日時の列の有無）、`tabs`） |
| `py/main.py` | PyScript のエントリ。JS と `mplgui` の橋渡しだけを書く（`window.mplgui` の登録（`loadFile` / `removeSource` / `clearSources` / `render` / `save` / `copyImage` / `script` / `registerFont` など）、Excel 用ライブラリの遅延導入、作業フォルダ `api.SESSION.workdir` の設定） |
| `py/mplgui/settings.py` | 設定スキーマ（version 3）、既定値、検証、日本語エラー（凍結 dataclass へ変換。`FileEntry`、読込設定の検証、`axes.x.dateFormat`）、`migrate_settings`（v1 → v2 → v3） |
| `py/mplgui/loader.py` | バイト列から DataFrame（文字コード判定、区切り文字、読込設定（`skip_lines` / `thousands` / `decimal` / `comment`）、xlsx のシート、日時の列の認識、プレビューと前置き行）。読込結果に `SourceInfo`（ファイル名、種別（csv / txt / tsv / xlsx）、文字コード、区切り文字、ヘッダの有無、読込設定、シート名とシート一覧、日時に変換した列 `datetime_columns`、貼り付けたデータか `pasted`）を付ける。`SourceInfo.read_kwargs()` が `pd.read_csv` / `pd.read_excel` の引数の唯一の定義で、loader と codegen が共有する。`split_lines`（pandas と同じく `\r` / `\n` / `\r\n` だけで行を分ける）、`detect_datetime_columns` / `convert_datetime` / `apply_datetime_columns`、`open_excel`（`pd.ExcelFile`）も持つ |
| `py/mplgui/dataprep.py` | DataFrame（または `{ファイル id: DataFrame}`）を見て決める処理。`plan_plot` が描画計画 `PlotPlan` を作る（データ元ごとの `skipRows` と Y 列の自動割り当て、X の数値変換・日時・文字列の別、描ける点の有無、A7 の警告（桁区切り・小数点のヒント付き）、日時の X の検査、データ由来の日本語 `UserError`）。描画に使うデータ元は `PlotPlan.sources`（`PlanSource`: id・番号・変数名・ファイル名）と `SeriesPlan.data_id` / `data_var` に持つ |
| `py/mplgui/codegen.py` | 設定・`SourceInfo`（または `{ファイル id: SourceInfo}`）・`PlotPlan` から matplotlib スクリプトを生成する（`generate_script`）。純粋な関数 |
| `py/mplgui/formats.py` | 保存形式の表（`FORMATS`）、保存解像度の既定値（`DEFAULT_SAVE_DPI` = 300。実際の値は `save.dpi`）、`build_filename`、`savefig_kwargs`、形式ごとの rcParams（`savefig_rc`）、PNG / JPG の画素数の上限（`MAX_RASTER_PIXELS`、`MAX_RASTER_SIDE`、`raster_pixels`、`check_raster_size`）。runner と codegen が共有する |
| `py/mplgui/runner.py` | スクリプトの実行（`run_script` / `run_to_image`）、Figure → 画像（PNG/JPG/SVG/PDF。`savefig_rc` を `rc_context` で適用、画素数の検査）、図の要約（`figure_summary`）、実行時エラーの整形、数式の誤りの判定（`is_mathtext_error`、`MathtextError`） |
| `py/mplgui/fonts.py` | フォントの登録と rcParams。日本語の一覧 `SANS_SERIF_PRIORITY`（先頭は Noto Sans JP）と、欧文フォントの表 `LATIN_FONTS`（Arimo / Tinos の表示名・候補名・mathtext フォントセット）が唯一の定義で、生成スクリプトもこれを使う。`register_font_bytes(data, kind=)` は種類（`japanese` / `arimo` / `tinos`）ごとに1回だけ登録する |
| `py/mplgui/errors.py` | `UserError`（利用者が直せるエラー） |
| `py/mplgui/api.py` | JS から呼ばれる JSON 入出力の関数（`render_json` / `save_json` / `copy_image_json` / `script_json` など）。読込済みデータ（`SESSION`。ファイル id ごとの `LoadedSource`（`df`・`SourceInfo`・書き出したファイル）と、xlsx の `ExcelFile` のキャッシュ（同じバイト列の間だけ）。`remove_source_json` / `clear_sources_json` も持つ）と、アップロードしたファイルの作業フォルダへの書き出しを持つ |
| `py/mplgui/runtime.py` | 警告フィルタ（起動時） |
| `tests/unit/` | 単体テスト（CPython、Agg）。`test_js_modules.py` は node で純粋な JS モジュール（units / palettes / presets / state）を検査する |
| `tests/e2e/` | E2E テスト（pytest-playwright、Chromium）。`run_script_summary.py` は、生成スクリプトを CPython で実行して図の要約を出す補助（一致確認用） |
| `tests/fixtures/` | 合成テストデータ（`make_fixtures.py` が生成。説明は `README.md`。Phase 4 で `preamble` / `european` / `thousands` / `comments` / `datetime` / `datetime_iso_tz` / `dates_ja` などを追加） |
| `tests/perf/bench.py` | 起動・描画の計測。結果は `docs/PERFORMANCE.md` |
| `.github/workflows/tests.yml` | CI |
| `_config.yml` | GitHub Pages（Jekyll）の include / exclude |

`py/mplgui/*` は `js` / `pyodide` に依存しない純粋なモジュールにする（CPython で単体テストできるようにするため）。DOM に触れるのは JS だけ。

## 3. 設定オブジェクト

- スキーマのバージョンは 3（`version`）。JSON のキーは camelCase。
- 唯一の正は JS 側（`js/state.js`）の設定オブジェクト。Python は DOM を読まず、渡された JSON を `settings.parse_settings` / `parse_load_settings` で凍結 dataclass に変換して使う。
- JS の既定値（`js/defaults.js`）と Python の既定値（`settings.default_settings()`）は一致させる。`tests/unit/test_defaults_parity.py` が比較する（node が無いと skip）。
- 主な構造: `load`（`delimiter`、`hasHeader`、`skipLines`、`thousands`、`decimal`、`comment`、`parseDates`、`files`）、`plot`（`type`、`skipRows`、`xColumn`、`title`、`fontSize`、`figure`、`latinFont`、`palette`、`legend`、`grid`、`margins`）、`axes`（`x` / `y` / `y2`: `label`、`scale`、`min`、`max`。`x` だけ `dateFormat`）、`series[]`、`save`（`filename`、`format`、`transparent`、`dpi`、`svgText`）。
- Phase 3 で足した項目と既定値:
  - `plot.figure`: `{width: 8, height: 6, unit: "in"}`。`unit` は `in` / `cm` / `mm`。`width` / `height` は選んだ単位の値で持つ（インチに直して持たない）。Python が検証するときだけ `FigureSettings.width_in` で「値 / 1インチあたりの長さ（2.54 / 25.4）」と割ってインチにする。上限は 50 inch を選んだ単位に直した値（in 50 / cm 127 / mm 1270）で、超えると単位つきの日本語エラー。
  - `plot.latinFont`: `default` / `arimo` / `tinos`（既定 `default`）。`plot.palette`: `ud` / `tab10` / `gray`（既定 `ud`。Python は選択肢の検証だけで、色は JS の `palettes.js` が持つ）。
  - `save.dpi`: 整数（既定 300、50〜1200、整数に見える数値・数値文字列・空欄=既定値を受け付ける。それ以外は「保存 DPI」の日本語エラー）。`save.svgText`: `path`（文字を図形にする。既定）/ `text`（文字のまま）。
- `settings.migrate_settings(raw)`: `parse_settings` / `parse_load_settings` / `parse_save_settings` が最初に通す（純粋。引数は変更しない）。version が無ければ現在のバージョン扱い。v1 → v2 は `save.dpi` が無ければ 120 にする（v1 の保存は常に 120 dpi だったので同じ出力になる）。図の単位・欧文フォント・パレット・SVG の文字は既定値で補われる。v2 → v3 は `load.parseDates` が無ければ **false** にする（v2 までの出力を保つ。Phase 3 の dpi 120 と同じ考え方。v3 で新しく作る設定の既定値は true）。他の新項目は既定値で補われる。1・2・3 以外は「設定のバージョン…に対応していません」の `UserError`。
- Phase 4 で足した項目と既定値（スキーマ version 3）:
  - `load.skipLines`（0）: ヘッダより前に読み飛ばす行数。整数（上限 1,000,000）。`field` は「ヘッダより前に読み飛ばす行数」。`plot.skipRows`（描画から除外する先頭行数。ヘッダの後のデータ行を数える）とは別の項目。
  - `load.thousands`（`""`。`""` / `,` / `.` / 空白 / `'`）、`load.decimal`（`.`。`.` / `,`）、`load.comment`（`""` または1文字）。thousands と decimal が同じ記号、comment が `"`・空白・thousands・decimal と同じ、はいずれも日本語の `UserError`（`field` は「桁区切り」「コメント記号」）。pandas の `thousands` / `decimal` / `comment` にそのまま渡す。
  - `load.parseDates`（true）: 日時の列を自動で認識する（§7）。
  - `load.files`（`[]`）: `[{id, name, sheet}]`。`id` は `d` + 数字（`d1`, `d2`, ...。削除しても再利用しない）、`sheet` が `""` なら先頭シート。最大 10 個（超えると「読み込めるファイルは10個までです。」）。画面の「データN」は、この配列の位置（N = 位置 + 1）。名前・シートの変更は、そのファイルだけを読み直す。
  - `series[].source`（`""`）: データ元のファイル id。`""` は `load.files` の先頭。`load.files` に無い id は「系列Nのデータ元が見つかりません。…」（`field` は「系列Nのデータ元」）。
  - `axes.x.dateFormat`（`""`）: X 軸の日時の表示書式（strftime）。`""` は自動。空でなければ `%` を含み、`strftime` が通ること（64 文字以下）。誤りは「X軸の日時の書式」の日本語エラー。`axes.y` / `axes.y2` には無い。
- パレットの色、プリセットの値、単位の換算は JS だけが持つ（`js/palettes.js`、`js/presets.js`、`js/units.js`）。プリセット名は設定に入れない。「適用」は図サイズ・単位・フォントサイズ・各系列の線幅と点サイズを個別の設定に書き込むだけで、直近のプリセットは `state.js` がセッション中だけ覚える（新しい系列に、線幅と、scatter のときの点サイズを引き継ぐ）。点サイズは、プリセットが自動（標準）なら全系列を自動に戻し、数値なら scatter か点サイズを入力済みの系列だけ書き換える。パレットの切替（`state.applyPalette`）は、全系列を系列の順に新しいパレットの色で塗り直してから `plot.palette` を書く。新しい系列の既定色は現在のパレットの未使用色。
- 系列: `id`、`x`、`y`、`color`、`lineWidth`、`lineStyle`、`markerSize`、`label`、`secondaryAxis`、`source`。`markerSize: null` は「自動」（line は 0、scatter は 24）。ユーザーが数値を入れたら自動切替の対象外。
- Pythonコードタブの状態（モード `sync` / `edit`、生成したコード）は設定オブジェクトに入れず、`js/code-state.js` に持つ。編集モードのコード本文は、`render` / `save` の別引数 `code` で渡す。「使用する」（`useCustomCode`）は廃止した。

## 4. Python ⇄ JS の API（`window.mplgui`）

Python が登録し、登録後に `mplgui-ready` イベントを送る。引数・戻り値は JSON 文字列（ファイルとフォントはバイト列）。

| 関数 | 引数 | 戻り値（`ok: true` のとき） |
|---|---|---|
| `ensureExcel()` | なし（非同期） | `{ok}`。初回の .xlsx 読込前に openpyxl を導入する |
| `loadFile(name, bytes, loadJson, sourceId, pasted)` | ファイル名、内容、`{version, load}`、データ元の id（省略時 `d1`）、貼り付けたデータか（省略時 false） | `{encoding, columns, preview, sheets, sheet, warnings}`。.xlsx は `encoding: null`、`sheets` はシート名の配列（xlsx 以外は `[]`）、`sheet` は読んだシート名（xlsx 以外は `null`）。`columns` の各要素は `{value, label, kind}`（`kind` は `datetime` / `number` / `text`）。`preview` は `{columns, columnKinds, rows, …, preamble: {lines, total}}`（`preamble` は読み飛ばした行の先頭最大20行と総数。`skipLines` が 0 のときは空） |
| `render(settingsJson, code)` | 設定 JSON、`code`（null または文字列） | `code` が null: `{image, code, output, summary, seriesCount, skipRows, warnings}`。文字列: `{image, output, summary}` |
| `save(settingsJson, code)` | 同上 | `{filename, mime, dataUri, output}` |
| `copyImage(settingsJson, code)` | 同上 | `{mime, dataUri, width, height, output}`（保存形式にかかわらず PNG） |
| `script(settingsJson)` | 設定 JSON | `{code}`（設定から生成した完全なスクリプトだけ。実行しない。読込済みデータが必要（無いと「先にファイルを読み込んでください。」）） |
| `scriptFilename(saveFilename)` | 保存ファイル名の入力値 | 「.py で保存」のファイル名（文字列）。保存ファイル名と同じ規則（`formats.build_filename`）で拡張子を `.py` にする |
| `removeSource(id)` | ファイル id（`d1` など） | `{ok}`（そのデータ元と作業フォルダのファイルを取り除く。無い id でも `ok`） |
| `clearSources()` | なし | `{ok}`（すべてのデータ元と作業フォルダのファイルを取り除く。「置き換えて読み込む」の前に JS が呼ぶ） |
| `registerFont(bytes, kind)` | フォントのバイト列、種類（`japanese`（省略時）/ `arimo` / `tinos`。他は「未対応のフォントの種類」の `UserError`） | `{registered, kind}`（種類ごとに登録は1回だけ。2回目以降は `registered: false`） |
| `fontStatus()` | なし | `{registered, kinds}`（`registered` は日本語フォントの登録済みか、`kinds` は登録済みの種類の一覧） |

`defaultCustomCode()` は廃止した（Phase 2）。

- `code` が null（GUI 同期）: 設定から生成したスクリプトの「自動描画用」（§4.1）を、読込済みの DataFrame（`df`）を渡して実行する。`image` は PNG の data URI、`code` は表示用の完全なスクリプト、`output` は実行中の print / stderr、`summary` は `runner.figure_summary` の軸ごとの要約。読込済みデータが必要。`save` は保存設定の形式・背景透過・`save.dpi`・`save.svgText` で書き出す（`render` のプレビューは dpi 100、`PREVIEW_DPI`）。形式ごとの rcParams（`formats.savefig_rc`: PDF は `pdf.fonttype=42`、SVG は `svg.fonttype` = `path` / `none`）は `matplotlib.rc_context` で `savefig` の間だけ適用する（生成コードの `plt.rcParams[...]` と同じ値）。`copyImage` は保存形式にかかわらず PNG を `save.dpi` で作り、背景透過は保存設定に従う（クリップボードにコピーする画像。C5）。`script` は、保存設定（`save.*`）の変更で表示中のコードだけを作り直すのに使う（§5）。
- `code` が文字列（編集モード。`save` / `copyImage` も同様）: そのスクリプトを丸ごと、アップロードしたファイルのある作業フォルダ（`SESSION.workdir`）で実行する。`render` は設定を読まない（設定が不正でも、読込済みデータが無くても動く）。`save` は保存設定（`save.*`）だけを `settings.parse_save_settings` で検証して使う（描画設定が不正でも、編集したコードの図は保存できる）。GUI の設定をコードの結果に上書き適用することはしない（A8）。
- `loadFile` は、読み込んだファイルを元のファイル名（フォルダ部分は除く）で作業フォルダに書き出す（同じ id の前のファイルは消す。失敗したらその id の読込済みデータと書き出したファイルを破棄する）。貼り付けたデータは `pasted_data.tsv`（UTF-8、タブ区切り）という名前のファイルとして同じ経路で読む。こうして、表示中のスクリプトの `pd.read_csv("ファイル名", ...)` がそのまま動く（P5）。
- 読込の規則（`loader.load_file`）: 拡張子は `.csv` / `.txt` / `.tsv` / `.xlsx`（それ以外は「対応していない拡張子です。xlsx/csv/txt/tsvを選択してください。」）。区切り文字の既定は拡張子で決まる（csv はカンマ、txt は空白、tsv はタブ。自動判定はしない）。pandas に渡す引数は `SourceInfo.read_kwargs()`（csv: `sep`・`header`・`skiprows`・`thousands`・`decimal`・`comment`・`engine="python"`。xlsx: `sheet_name`・`header`・`skiprows`・`thousands`・`decimal`・`comment`）。xlsx のシートは `loadJson` の `load.files` のうち `sourceId` の項目から決め（無ければ先頭）、無い名前は「シート「X」がファイルにありません。…」（`field` は「シート」）。`pd.ExcelFile` は同じバイト列の間だけ id ごとにキャッシュする（シートの切替を速くする）。
- 読込のエラーと警告（利用者に案内する）: 区切りが空白で `thousands` が空白、`comment` が区切り文字と同じ、は `UserError`。列数が揃わない `ParserError` と、`skipLines` が大きすぎてデータが無いときは、「ヘッダより前に読み飛ばす行数」を案内する文を添える。小数点と区切り文字が同じ記号（1文字の区切りで `decimal == sep`）はエラーにせず警告にする（引用符で囲まれた値は読めるため）。結果が1列で先頭のデータ行に `;` かタブがあれば、区切り文字の指定漏れの警告（`DELIMITER_HINT`）を返す。前置き行は、csv / txt / tsv ではデコード後のテキストを `split_lines`、xlsx では先頭 `skipLines` 行をタブでつないで作る。
- `warnings` は `{series, message}` の配列（読込時は文字列配列の場合もある。JS の `warningTexts` が吸収する）。
- 失敗: `{ok: false, error: {message, field?, detail?, traceback?, line?}, output?}`。
  - 利用者が直せる原因は `UserError`。`message` は日本語で、どの項目が悪いかを含める（`field`）。
  - それ以外の例外は内部エラー。短い日本語メッセージ（`INTERNAL_ERROR_MESSAGE`）に、`detail` として traceback を付ける（画面の「内部エラー詳細」に出る）。
  - スクリプトの実行時エラーは `runner.ScriptError`。`message` は日本語の要約（編集モードは「N行目、エラーの型: 日本語の説明」入り）、`traceback` は `plot.py` の行だけのトレースバック、`line` は最後の `plot.py` の行番号、`detail` は完全な traceback。トップレベルの `output` は、失敗するまでの print の出力（`output` 属性を持つ例外だけ）。
  - GUI 同期で生成コードの実行が失敗したときは、行番号から失敗した手順（`GeneratedScript.step_for_line`）を引き、手順ごとの日本語メッセージ（`field` 付き）に置き換える（`api._step_error`）。手順に当たらなければ `GENERIC_ERROR_MESSAGE`。
- `render` は読込済みデータが無いと（GUI 同期のとき）「先にファイルを読み込んでください。」を返す。
- 画素数の検査（`formats.check_raster_size`）: PNG / JPG は、書き出す前に `int(幅inch × dpi)` × `int(高さinch × dpi)`（Agg と同じ切り捨て。`raster_pixels`）が 1 億画素（`MAX_RASTER_PIXELS`）を超える、または1辺が 65536（`MAX_RASTER_SIDE`）以上なら、`UserError`（「保存する画像が大きすぎます（幅 N × 高さ M ピクセル）。保存 DPI か図のサイズを小さくしてください。」、`field` は「保存 DPI」）にする。`runner.figure_to_bytes` で行うので、`render`（dpi 100）・`save`・`copyImage`・編集モードのどれにも効く。SVG / PDF には使わない。
- 数式（mathtext）の書き間違い（C6）: `runner.is_mathtext_error` が、matplotlib の `_mathtext.py` から出た `ValueError` または pyparsing の `ParseBaseException`（`__cause__` / `__context__` の連鎖を含む）を判定する。GUI 同期では、実行中（`tight_layout` など）でも、画像にするとき（`MathtextError`）でも、`api.MATHTEXT_ERROR`（`field` は「数式」。例 `m$^2$`、`H$_2$O`、`$\alpha$`、`\$` を案内する日本語）にする。編集モードでは、`runner.MATHTEXT_HINT` が日本語の説明（`japanese_hint`）として「N行目、ValueError: …」に付く（実行中に見つかったとき。画像にするときに見つかった場合は `field` が「数式」）。内部エラーにはしない。

### 複数ファイル（Phase 4 D6）

- `loadFile` は id ごとに読み込み、その id のデータ元だけを置き換える（失敗したら、その id だけを破棄。ほかは残る）。`api.Session.sources` は `{id: LoadedSource(df, info, written)}`、Excel の `ExcelFile` も id ごと。
- データ元の解決: `series.source` が空なら `load.files` の先頭、`load.files` が空なら読み込んだ先頭。読み込めていないデータ元を使う系列は「データN（name）を読み込めていません…」（`field` は「系列Nのデータ元」）。`dataprep.plan_plot(data, settings)` は DataFrame または `{id: DataFrame}` を受け、`skipRows` と Y の自動割り当てをデータ元ごとに行う。棒グラフは全系列が同じデータ元（違えば「データ元」のエラー）。
- 生成コード: `load.files` が 1 件以下なら従来どおり（`DATA_FILE` / `df`）。2 件以上なら、系列が使うファイルだけを `DATA_FILE_N` / `dfN`（N は一覧の位置 = 画面の「データN」）で読む。自動描画では `{"df1": ..., "df2": ...}` を注入する。
- JS（`bridge.js`）: ファイルごとに `{File, bytes, pasted, state(loading|ready|error), result, error}` を持つ。`#fileInput`（置き換え）、`#addFileBtn` / `#addFileInput`（追加）、ドロップの `#dropReplace` / `#dropAdd`、一覧 `#fileList`（行 `file-<id>`、`file-<id>-sheet`、`file-<id>-remove`）、データ確認の `#previewSource`、系列の `series-<id>-source`。同じ名前のファイルは同じ id で置き換え、上限は 10 個。`data-data-state` は読込中が1つでもあれば `loading`、失敗が1つでもあれば `error`（ほかのファイルが読めていれば描画は行い、失敗は警告に出す）。`data-load-count` は、読み込めたデータ元がある読込の完了ごとに増える。

## 4.1 コード生成（Phase 2）

描画経路は1本: 設定 → `dataprep.plan_plot`（データを見て決める処理と検査）→ `codegen.generate_script`（スクリプトの文字列）→ `runner`（実行して Figure を得て画像にする）。GUI の図と、書き出す `.py` は同じコードから作る。

- `dataprep.plan_plot(data, settings)`（`data` は DataFrame または `{ファイル id: DataFrame}`）: データ元の解決（`series.source` が空なら `load.files` の先頭）、データ元ごとの `skipRows` の適用と Y 列の自動割り当て、X の数値・日時・文字列の別、描ける点があるか、日時の X の検査（日時と日時でない X の混在、X が日時のときの対数軸・範囲指定、Y が日時、はいずれも日本語の `UserError`）、数値に変換できず除外した値の警告（A7）を決める。データ由来の問題は日本語の `UserError`（列が範囲外、除外行数が多すぎる、描ける数値データが無い、など）にする。結果は凍結 dataclass の `PlotPlan` / `SeriesPlan`。
- `codegen.generate_script(settings, source, plan)` は `GeneratedScript`（`text`、`load_lines`、`output_lines`、`steps`）を返す。純粋な関数で、データには触れない。
- スクリプトの構成: ヘッダ（使い方、`import`、日本語フォントの rcParams、欧文フォントの設定（下記）、`FONT_SIZE`）→ `1. データの読み込み`（`DATA_FILE`、`pd.read_csv` / `pd.read_excel`。読込の引数はすべて1行に1つ、コメント付きで明記する（下記））→ `2. 描画に使う行`（`skipRows`）→ `3. 図と軸`（`fig, ax`。単位ごとの書き方は下記）→ `4. 系列` → `5. 軸（ラベル・スケール・範囲・目盛）` → `6. グリッドと凡例` → `7. 余白` → `8. 保存と表示`（形式ごとの rcParams、`fig.savefig(...)`、`plt.show()`）。各セクションの見出しは `# ==== 番号. タイトル ====`。
- `1. データの読み込み`（Phase 4）: 引数は `SourceInfo.read_kwargs()` の順に、既定値も含めてすべて書く（csv: `encoding`（自動判定）、`sep`、`header`、`skiprows`、`thousands`、`decimal`、`comment`、`engine="python"`。xlsx: `sheet_name`、`header`、`skiprows`、`thousands`、`decimal`、`comment`。xlsx では「ファイル内のシート」の一覧もコメントに書く）。ヘッダなしのときは続けて `df.columns = [f"column_{i}" ...]`。日時の列があれば、`# 日時の列を日時に変換する…` に続けて列ごとに `df.isetitem(N, pd.to_datetime(df.iloc[:, N], format="…", errors="coerce"))  # 列名 [N]`（前後の空白があれば `.str.strip()`、タイムゾーンの混在は `utc=True`、タイムゾーン付きは `.dt.tz_localize(None)`）。loader も同じ式（`convert_datetime`）を同じ順で適用するので、画面のデータと生成コードの読込結果は一致する。貼り付けたデータ（`SourceInfo.pasted`）のときは、読込部の先頭と「使い方」に「貼り付けたデータを保存して `pasted_data.tsv` として置く」案内を書く（データはスクリプトに埋め込まない）。
- 複数ファイル: `load.files` が1件以下なら `DATA_FILE` / `df`。2件以上なら、系列が使うファイルだけを `DATA_FILE_N` / `dfN`（N = `load.files` の位置 + 1 = 画面の「データN」。使わないファイルがあっても番号は詰めない）で、「データN: ファイル名」の見出しコメント付きで読む。`2. 描画に使う行`（`skipRows`）も `dfN` ごと。系列のコメントと変数は `p.data_var` を使う。
- 軸（Phase 4）: X が日時のとき（line / scatter）、`axes.x.dateFormat` が空なら `mdates.AutoDateLocator()` と `mdates.ConciseDateFormatter(date_locator)`、指定があれば `mdates.DateFormatter(<literal>)`。`import matplotlib.dates as mdates` は日時軸のときだけ書く。棒グラフで X が日時のときは `.dt.strftime(<書式>)` でカテゴリの文字列にして並べる（書式は `dateFormat`、空なら全部 0 時 `%Y-%m-%d` / 秒が全部 0 `%Y-%m-%d %H:%M` / それ以外 `%Y-%m-%d %H:%M:%S`）。X が日時でない文字列の列のときは、Phase 2 の `ax.set_xscale("linear")` を入れず、目盛に X の値（カテゴリ）を出す。描く系列の X のカテゴリ（重複を除く）が 25 個を超えるときだけ `ticker.MaxNLocator(nbins=25, integer=True)` で間引く（`import matplotlib.ticker as ticker` もそのときだけ）。
- 欧文フォント（`plot.latinFont` が `arimo` / `tinos` のときだけ。`default` ではヘッダは Phase 2 と同じ）: ヘッダに `from matplotlib import font_manager` を足し、`installed = {font.name for font in font_manager.fontManager.ttflist}`、`latin = [name for name in [候補…] if name in installed][:1]`、`plt.rcParams["font.family"] = latin + ["sans-serif"]` を書く。候補は `fonts.LATIN_FONTS` の並び（Arimo: `Arimo`、`Arial`、`Liberation Sans`。Tinos: `Tinos`、`Times New Roman`、`Liberation Serif`）。入っているフォントだけを選ぶのは、無い名前を `font.family` に並べると、matplotlib が描画のたびに `findfont` の警告を出すため（ローカルで実行しても警告を出さず、どれも無ければ日本語フォントで書く）。日本語の文字は、リストの後ろの `sans-serif`（`font.sans-serif` の日本語フォント）に、matplotlib の文字単位のフォールバックで回る。Tinos（`mathtext_fontset` = `stix`）のときは `plt.rcParams["mathtext.fontset"] = "stix"` も書く（数式も Times 系の字形にする。STIX は matplotlib 同梱）。
- `3. 図と軸`: `figsize` はインチ。`unit` が `in` なら `figsize=(幅, 高さ)`。`cm` / `mm` なら `CM_PER_INCH = 2.54`（`MM_PER_INCH = 25.4`）を定義し、`figsize=(幅 / CM_PER_INCH, 高さ / CM_PER_INCH)` と割る（コメントに単位と値を書く）。`1 / 2.54` を掛けると、20.32 cm が 7.999… inch になり、Agg の画素数（切り捨て）が 1 画素欠けるため、割り算にする（Python 側の `FigureSettings.width_in` も同じ割り算）。
- `8. 保存と表示`: `formats.savefig_rc(format, svg_text)` が返す rcParams を、`plt.rcParams["pdf.fonttype"] = 42` / `plt.rcParams["svg.fonttype"] = "path"|"none"` としてコメント付きで `fig.savefig(...)` の前に書く（runner が `rc_context` で適用する値と同じ）。`savefig` の `dpi` は PNG / JPG のときだけ入れ、値は `save.dpi`（コメントに「N dpi」）。PDF のときは、手元の日本語フォントが OpenType（CFF）形式（macOS のヒラギノなど）だと文字が正しく表示されないことがあるという注意を、コメント2行で添える（原因は §6）。
- 変数名は、`df`（データ）、`fig` / `ax` / `ax2`（第2Y軸）、系列ごとの `x` / `y` / `ok`（欠けた行を除くマスク）、棒グラフ（複数系列）の `bar_data` / `positions` / `x_labels` / `width`。列は常に `df.iloc[:, N]`（列番号）で参照し、GUI で選んだ列名と番号はコメントに書く（同名の列を区別できる）。列名はコードに入れない。
- 自動描画用の変種（`GeneratedScript.auto_render_text`）: 「データの読み込み」と「保存と表示」の行を空行にしたもの。行番号は表示中のスクリプトと同じなので、トレースバックの行番号がそのまま使える。GUI の自動描画は、これに読込済みの `df` を渡して実行する（ファイルを読み直さない）。
- 手順（`Step`）: 失敗しうる行の範囲と日本語メッセージ（`field` 付きのものもある）の対応表。系列の描画（`GENERIC_ERROR_MESSAGE`）、軸のスケール・範囲（X / Y / 第2Y）、`tight_layout`、`subplots_adjust`（余白）を登録している。
- **安全性（必須）**: 列名・タイトル・ラベル・色・ファイル名・文字コード・シート名・コメント記号・日時の書式・貼り付けたデータのファイル名などは信頼できない入力で、実行されるコードに入る。値は必ず `literal()`（str / int / 有限の float / bool / None だけを `repr` で出す。他の型は例外）を通して書き出し、コメントに入れる文字列は必ず `comment_text()`（改行・制御文字を空白にする）を通す。f 文字列などで、これ以外の方法で信頼できない文字列をコードに埋め込まないこと。`tests/unit/test_codegen.py`（と `test_load_options.py` / `test_datetime.py` / `test_multi_source.py` / `test_paste_tsv.py`）の注入テストが、シート名・ファイル名・コメント記号・日時の書式・列名で検査する。
- GUI の設定を、ユーザーが編集したコードの結果に上書き適用しない（A8）。編集モードのコードは、設定を使わずそのまま実行する。
- 機能追加（Phase 5〜）の手順: 描画の種類は `SERIES_EMITTERS`（プロット種別 → 系列の出力関数）に追加する。出力関数は `_Builder` に行を足し、失敗しうる行は `with b.step(メッセージ, field)` で包む。軸・グリッド・余白などは対応する `_emit_*` 関数に足す。データを見ないと決められないこと（列の割り当て、変換の要否、警告、データ由来のエラー）は `dataprep` の `PlotPlan` / `SeriesPlan` に項目を足して渡す（データ元ごとに違うことは `SeriesPlan.data_id` / `data_var` と `PlotPlan.sources` に持つ。読込の仕方に関わる引数は `SourceInfo.read_kwargs()` に足し、codegen の `_READ_COMMENTS` にコメントを足す）。設定項目を足すときは JS の `defaults.js` と `settings.py` の両方に足す。生成するコードは pandas / matplotlib / numpy だけを使う（ローカルの Python でそのまま動かすため）。新しい行を足したら、単体テストで「全体を実行した図」と「自動描画用の図」が一致することも確かめる。保存形式ごとの rcParams は `formats.savefig_rc` に足す（runner と codegen が同じ表を使う）。欧文フォントを足すときは `fonts.LATIN_FONTS`・`FONT_FILENAMES`、JS の `font-cache.js` の `FONT_URLS`・`bridge.js` の `LATIN_NAMES`、`settings.LATIN_FONTS`、`index.html` の選択肢を揃える。
- 生成スクリプトの保存ファイル名（`savefig` の引数）は `formats.build_filename` で決める。保存形式・解像度・形式ごとの rcParams は `formats.savefig_kwargs`（解像度は `save.dpi`）/ `formats.savefig_rc` で、GUI の「保存」と同じにする。

### runner（スクリプトの実行）

- `run_script(code, injected=, cwd=)` はコンテキストマネージャ。`matplotlib.rc_context()` の中で実行し、スクリプトが変えた rcParams を次の実行に持ち越さない。`cwd` を指定すると実行中だけ作業フォルダを移す（終了後に戻す）。
- stdout と stderr は1つのバッファに集めて `output` として返す。
- 図の選び方: 名前空間の `fig`（`Figure` のとき）を優先し、無ければ実行中に新しく作られた最後の図。どちらも無ければ「図が作られませんでした。」（`UserError`）。
- 実行中に作られた図は、`with` を抜けるときにすべて閉じる（呼び出し側は `with` の中で画像にする）。`linecache` の登録も消す。
- 失敗: `compile` エラーも実行時の例外も `SystemExit`（`exit()`）も `ScriptError` にする。トレースバックは `plot.py` のフレームだけを残し、メッセージには日本語の説明（`japanese_hint`。インデント、文法、`NameError`、`FileNotFoundError`、`ImportError` など）を付ける。
- `plt.show()` は Agg では何もせず警告を出すので、スクリプトの実行中だけ、この警告（`FigureCanvasAgg is non-interactive, and thus cannot be shown`）を無視する（§8）。

## 5. 描画パイプライン

- 描画は設定変更の 250 ms 後（デバウンス）。読込は、ファイル選択・ヘッダ変更・シート変更・桁区切り・小数点・日時の自動認識の変更で 0 ms、入力欄（区切り文字・ヘッダより前に読み飛ばす行数・コメント記号）の変更で 450 ms 後（`bridge.js` の `LOAD_DELAY_MS` / `SLOW_LOAD_PATHS`）。読込設定（`load.*`）の変更は全ファイルを読み直す。ファイル一覧のシート変更は、そのファイルだけを読み直す（`load.files` の変更に `fileId` が付く）。保存設定（`save.*`）の変更では再描画しない（画像の画素は保存設定に依存しないため）。`skipRows` の変更は Python を呼ばず、データ確認表のグレー表示だけ即時に更新する。
- 起動中の `#progress`（`aria-live="polite"`）は段階表示: 「Python 実行環境を読み込み中…」→「ライブラリを読み込み中…（pandas ✓, matplotlib …）」→「ライブラリを初期化中…」→ 準備完了で消える（フォント取得の表示が続く場合あり）。`<html>` の `data-startup-stage`（`runtime` / `packages` / `init` / `ready`）に現在の段階が入る。新しい id は無い。読込失敗の案内（`data-load-failed`）は上書きしない。
- 保存設定（`save.*`: ファイル名・形式・背景透過・DPI・SVG の文字）の変更は、GUI 同期のときだけ、250 ms 後に `script` API でコードだけを作り直す（`bridge.js` の `refreshScript`）。画像は描き直さず、コードの世代（`#customPyCode` の `data-generation`）は表示中の画像のまま（`code-state.getGeneratedGeneration()`）。描画が予約中・実行中のときは何もしない（描画が新しいコードを返す。実行中だったら終了後にもう一度確かめる）。コードの更新に失敗したら（保存設定の不正など）エラーを表示し、次に成功したときに直近の描画成功のステータスへ戻す。編集モードでは何もしない。
- 描画要求には世代番号を付ける。Python の描画は同時に最大1つ。実行中に新しい要求が来たら「やり直し」の印だけ付け、終了後に最新の設定で1回だけ描く（合流）。古い世代の結果は画像にもステータスにも反映しない。
- Python の起動前に選んだファイルや変えた設定は保持し、起動後に最新の内容で1回読み込んで描く（起動キュー）。
- ファイルの操作（Phase 4）: 「ファイルを選択」`#fileInput`（複数可）と貼り付けは、読み込み済みのデータをすべて置き換える（Python 側は `clearSources` を呼んでから読む）。「+ ファイルを追加」`#addFileBtn`（`#addFileInput`）とドロップの追加区画は追加。同じ名前のファイルは、その id のまま置き換えて読み直す。上限 10 個（超えた分は警告「読み込めるファイルは10個までです。…」で読み込まない）。削除（一覧の `file-<id>-remove`）は `removeSource` を呼び、そのファイルを使っていた系列は `source` を `""`、X / Y を自動に戻して警告を出す。最後のファイルを削除したら、起動直後の状態（図・データ確認・コード・ステータスを空にし、ファイルなし）に戻す（編集モードのコードはそのまま）。一部のファイルの読込に失敗しても、ほかのファイルは使える（失敗したファイルは一覧に残り、設定を変えると再試行する。それを使う系列はデータ元のエラーになる）。
- ドロップ: ページ全体で受ける（`dataTransfer.types` に `Files` があるときだけ `#dropOverlay` を出す。文字列のドラッグには反応しない）。未読込のとき `#dropLoad` の1区画、読み込み済みのとき `#dropReplace`（置き換え）と `#dropAdd`（追加）の2区画で、ポインタの下の区画で決める（区画の外は置き換え）。ドラッグ中の preventDefault でブラウザがファイルを開かない。`dragleave` の `types` が空のブラウザ（Safari）でも出しっぱなしにしない。Esc でも閉じる。フォルダは読み込めない（警告）。
- 貼り付け: `#pasteArea` への貼り付け（paste、または値が入った input）は常に読み込み、すべてのデータを置き換える。ページ上の paste（貼り付け先が input / textarea / select / contenteditable でないとき）は、データが未読込のときだけ読み込む。読込済みなら置き換えず、「「表を貼り付け」欄に貼り付けてください」と案内する警告を出す（うっかり置き換えない）。表とみなす条件は、タブを含む、または空でない行が2行以上。そうでなければ警告。改行は `\n` にそろえ、UTF-8 の `pasted_data.tsv` として `loadFile`（`pasted: true`）に渡す。`#savePastedBtn` は、データ元に貼り付けたデータがあるときだけ表示し、同じバイト列を JS だけでダウンロードする。
- コードタブの「最新でない」印: GUI 同期のとき、描画またはコードだけの更新（`refreshScript`）が失敗して新しいコードを作れなかったら、`#customPyCode` に `data-stale="true"` を付け、`#codeStaleNote`（既定は hidden）を出す。新しいコードを表示したとき・編集モードに入ったときに消える（`code-state.js` の `setCodeStale`）。既存の data 属性の値は変えない。
- Pythonコードタブのモード（`js/code-state.js`）:
  - `sync`: GUI の設定から生成したスクリプトを表示し、描画に成功するたびに更新する。
  - `edit`: 利用者が書き換えたコードを「実行」（Ctrl/Cmd+Enter）したときだけ描く。GUI の変更でも、ファイルの読込でも自動では描かず、コードも更新しない（ステータスに warning で「編集中のため反映されません」と出す）。読込は行い、ファイルは作業フォルダに置かれる。フォント取得後の描き直しも、実行したことがあるときだけ行う。
  - 「編集」で `edit`、「GUI から再生成」で `sync` に切り替える。切り替えのたびに、予約中・実行中の描画を無効にする（世代を進め、結果は画像にもコードにもステータスにも反映しない）。このため `data-render-generation` は、モード切替の直後に、表示中の画像の世代より先に進んだままになることがある。E2E は `tests/e2e/helpers.py` の専用ヘルパー（`wait_code_generated`、`wait_image_generation_changed`、`run_edited_code`、`wait_run_finished`）で待つこと。
  - `sync` の描画は読込済みデータが必要。`edit` は Python が動いていればよい（コードが自分でファイルを読む）。
- 欧文フォント（`plot.latinFont`）: 選んだときだけ取得する（既定の `default` では取得しない）。Python の起動前に選んでいたら、起動後に取得する。取得中の描画・保存・コピーは、`waitForFonts` が最大 `FONT_FIRST_RENDER_WAIT_MS`（8 秒）待つ。超えたらその種類は待ちを打ち切り、標準フォントで描き、取得・登録が済んだら（選択中のままなら）現在の設定で1回だけ描き直す（編集モードでは「実行」したことがあるときだけ）。取得は種類ごとにセッション中1回で、失敗しても再試行しない。失敗したら、選択中のあいだ警告「欧文フォント Arimo（または Tinos）を取得できなかったため、標準のフォントで描画しています。」を常時警告に1度だけ出し、標準（`default`）に戻すと消える（取得を再試行しない）。編集モードでも欧文フォントの取得・登録はするが、描画もコードも触らない。取得中は進捗バナーに「欧文フォントを取得中…」。
- 左パネルは `details.panel-section`（`#sectionLoad` データ読み込み（ファイル・貼り付け・シート・区切り文字・ヘッダ・読み飛ばす行数・桁区切り・小数点・コメント記号・日時の自動認識）、`#sectionSeries` 系列（描画から除外する先頭行数を含む）、`#sectionAxes` 軸・目盛、`#sectionStyle` 体裁、`#sectionSave` 保存）に分かれ、既定はすべて開く。折りたたみの状態は localStorage の `mplgui.panelSections` に持つ（`panelSections.js`）。ステータス（`#status`）は区分の外にあり、閉じていても見える。「注釈・解析」の区分は Phase 5 まで作らない。体裁区分は、プリセット（`#stylePreset`、「適用」`#applyPresetBtn`）、`#colorPalette`、`#latinFont`、`#fontSize`、図サイズ（`#figWidth` / `#figHeight` / `#figUnit`）、凡例位置、グリッド、余白。軸・目盛区分には数式の案内（`#mathtextHelp`。matplotlib 3.10.8 の mathtext ページへのリンク）と、X が日時の列のときだけ出る日時の書式（`#xDateFormatGroup`。line / scatter はどれかの系列の X、bar は `#xColumn` が日時の列のとき）がある。保存区分は `#saveDpi`（+ 任意の `#saveDpiCustom`）、SVG のときだけ `#svgTextGroup`（`#svgText`）、PDF のときだけ `#pdfHelp`、`#savePlotBtn`、`#copyPlotBtn`。
- 図サイズの単位を替えると、入力欄の数値を換算し（`convertLength`。空欄・不正な入力はそのまま）、図の大きさは変えない。ラベル（`図幅(inch)` など）と step は単位に合わせる。プリセットの「適用」は値を書き込むだけで、描画は通常の変更どおり。パレットを替えると、色の選択肢と各系列の色を描き直す。
- 「クリップボードにコピー」（`clipboard.js`）: 保存 DPI の PNG を `copyImage` で作り、`ClipboardItem` に `Promise<Blob>` として渡して `navigator.clipboard.write` する（Safari がクリックの中での呼び出しを要求するため、クリックの処理では何も `await` せずに `write` を呼び、画像は渡した Promise の中で作る）。対応は `window.isSecureContext`（https または localhost）、`navigator.clipboard.write`、`ClipboardItem`（`ClipboardItem.supports("image/png")` があれば true）。編集モードでは編集中のコードの図をコピーする。
- E2E が使う状態は `<html>` の data 属性: `data-app-state`（`starting` / `ready` / `failed`）、`data-data-state`（`none` / `loading` / `ready` / `error`）、`data-render-state`（`idle` / `pending` / `rendering`）、`data-render-generation`、`data-font-state`（日本語フォント。`idle` / `loading` / `ready` / `failed`）、`data-latin-font-state`（選択中の欧文フォント。`idle`（標準を選択中）/ `loading` / `ready` / `failed`）、`data-copy-state`（`idle` / `copying` / `done` / `failed` / `unsupported`）、`data-load-count`（読み込めたデータ元がある読込のまとまりの完了ごとに増える。ファイルを外しただけ・全ファイルの失敗では増えない）。複数ファイルのとき、`data-data-state` は読込中が1つでもあれば `loading`、読込中がなく失敗が1つでもあれば `error`、すべて成功なら `ready`、ファイルが無ければ `none`。表示中の画像は `#plotArea img` の `data-generation` と `data-summary`（`figure_summary` の JSON）を持つ。ステータスは `#status` の `data-kind`。Pythonコードタブ用に、`<html>` の `data-code-mode`（`sync` / `edit`）、`#customPyCode`（textarea）の `data-generation`（表示中のコードを生成した世代。GUI 同期のとき、同じ世代の画像と対応する）、`#codeOutput` の `data-kind`（`ok` / `error`）、`#codeSyncStatus` の `data-state`（`sync` / `edit`）、`#customPyCode` の `data-stale`（最新でないときだけ `true`）、`#codeStaleNote` がある。Phase 4 の画面の id: データ読み込み区分の `#fileInput` / `#addFileBtn` / `#addFileInput` / `#fileList` / `#pasteArea` / `#savePastedBtn` / `#sheetGroup` / `#sheetSelect` / `#skipLines`（+ `#skipLinesHelp`）/ `#thousands` / `#decimal` / `#commentChar` / `#parseDates`、系列区分の `#skipRowsHelp` / 系列カードの `series-<id>-source`、軸・目盛区分の `#xDateFormatGroup` / `#xDateFormat` / `#xDateFormatCustom`、データ確認の `#dataPreamble` / `#previewSource`（+ `#previewSourceGroup`）、ドロップの `#dropOverlay` / `#dropLoad` / `#dropReplace` / `#dropAdd`。

## 6. 起動とフォント

- PyScript 2026.7.3（Pyodide 314.0.3 / Python 3.14）。`pyscript.toml` は `packages = ["pandas", "matplotlib"]`、`packages_cache = "passthrough"`（micropip を使わない）。
- openpyxl と et_xmlfile は Pyodide 同梱ではないので、初めて .xlsx を読むときに `py/main.py` が、バージョン固定の wheel URL（`files.pythonhosted.org`）を `pyodide_js.loadPackage` に渡して導入する。起動時には導入しない。
- matplotlib のバックエンドは Agg（`py/main.py` で `matplotlib.use("Agg")`。pyplot を import する前に指定する）。
- 日本語フォントは、固定 URL の jsDelivr（`@expo-google-fonts/noto-sans-jp@0.4.4/400Regular/NotoSansJP_400Regular.ttf`、約5.7 MB。TrueType 版 Noto Sans JP）から取得し、Cache Storage（キャッシュ名 `mplgui-fonts-v1`）に保存する。2回目以降の訪問ではダウンロードしない。取得はセッション中1回で、失敗しても再試行せず、警告を1度だけ出してフォールバックフォントで続行する。
- Noto Sans CJK JP の OTF（CFF 形式、約16 MB）から替えた理由: matplotlib 3.10 は CFF 形式のフォントを `pdf.fonttype=42` で正しく埋め込めない（TrueType 用の FontFile2 に CFF を入れ、PDF が壊れる）。TrueType 版は同じデザイン・同じ文字幅。ハングルと中国語専用の漢字は含まれない（JIS 第1〜第4水準は含む）。旧 OTF のキャッシュ（URL `noto-cjk@Sans2.004/...NotoSansCJKjp-Regular.otf`）が `mplgui-fonts-v1` に残っていたら、日本語フォントの取得時に1回だけ削除する（失敗は無視する）。matplotlib に登録するフォント名は `Noto Sans JP`（`SANS_SERIF_PRIORITY` の先頭）。
- 欧文フォント（選んだときだけ取得。起動時には取得しない）: Arimo は `@expo-google-fonts/arimo@0.4.3/400Regular/Arimo_400Regular.ttf`、Tinos は `@expo-google-fonts/tinos@0.4.2/400Regular/Tinos_400Regular.ttf`（各 約0.3〜0.5 MB。jsDelivr、バージョン固定）。同じ Cache Storage に保存し、種類ごとにセッション中1回だけ取得する。ライセンスは3つとも SIL OFL 1.1（Noto Sans JP のライセンス全文: `https://cdn.jsdelivr.net/npm/@expo-google-fonts/noto-sans-jp@0.4.4/LICENSE_FONT`。Arimo は `@expo-google-fonts/arimo@0.4.3/LICENSE_FONT`、Tinos は `@expo-google-fonts/tinos@0.4.2/LICENSE_FONT`）。リポジトリにはフォントを置かない（実行時に取得するだけ）。登録は `registerFont(bytes, kind)`。画面用の Web フォントは `@fontsource/noto-sans-jp@5.3.0`（`index.html`）。
- フォント取得は、進みが 20 秒止まる（ヘッダが届かない、または本文が進まない）と失敗扱いにする（`FONT_STALL_MS`。日本語・欧文とも）。
- 日本語フォントは、最初の描画だけ取得を最大 8 秒待つ（`FONT_FIRST_RENDER_WAIT_MS`）。欧文フォントは、選んだフォントごとに1回だけ待つ。超えたらフォールバックフォントで描き、取得が終わったら現在の設定で1回だけ描き直す（§5）。保存とコピーも、取得中なら同じ時間まで待つ。
- テスト専用に、`window.__MPLGUI_TEST_OVERRIDES__ = {fontStallMs, fontFirstRenderWaitMs}` で上の時間を短縮できる。

## 7. 文字コード判定・数値変換警告・ステータス

- 文字コード（`loader.detect_encoding`）: BOM 付きなら utf-8-sig → UTF-8 → CP932 と EUC-JP。両方でデコードできるときは、半角カナ・私用領域・制御文字などの「文字化けらしい文字」が少ないほうを採用し、同数なら CP932。どれでも読めなければ日本語のエラーにする。判定結果は `#encodingLabel` に表示する。
- 数値に変換できず除外した値は、系列ごとに警告にする（`dataprep.dropped_warning`。`dataprep.plan_plot` が集める）。
- 数値に変換できず除外した値の例が「1,234」のような桁区切りの数で `thousands` がカンマでないとき、「1,5」のような小数点カンマで `decimal` がカンマでないときは、警告の文に「（桁区切りのカンマなら、「データ読み込み」の「桁区切り」をカンマにしてください）」「（小数点がカンマなら、「小数点」をカンマにしてください）」を添える（`dataprep.load_hint`。両方に当てはまる `1,234` は桁区切りのヒントだけ）。
- 日時の列の認識（`loader.detect_datetime_columns`。`load.parseDates` が true のときだけ。Excel の日付セル（もともと datetime の列）は設定にかかわらず日時）: 読込後に数値でない文字列の列のうち、空欄以外の半数以上が数値に読める列は除く。書式は年が先頭の固定の候補だけ（日付 `%Y-%m-%d` / `%Y/%m/%d` / `%Y年%m月%d日`、時刻は無し / ` %H:%M` / ` %H:%M:%S` / ` %H:%M:%S.%f`、`%Y-%m-%d` には ISO の `T` 区切りも、時刻のあるものには末尾 `%z`（`Z` と `+09:00`）も）。前後の空白を除いた先頭 100 個の空欄以外の値の 90% 以上が読める書式のうち最も多く読めるものを選び、列全体でも 90% 以上が読めれば日時の列にする。月日の順が曖昧な `01/02/2024`、時刻だけ、年月だけは認識しない。読めない値は NaT にして、列ごとに警告（「列「name」[i]: 日時として読めない値がN件あったため、欠損として扱います（例: …）」。例は最大3件）。`%z` 付きは、全行が同じオフセットなら書かれた時刻のまま、混在していれば UTC にそろえて警告する。日時の列は `columns[].kind` が `datetime` になり、データ確認の列見出しに「日時」の印が付く。日時の X で描くときの検査は §4.1。
- ステータス（`#status`）の種別は `ok` / `warning` / `error`。警告は成功メッセージに添えて表示し、`error` のときは `data-kind="error"`。日本語フォント取得失敗のような常時有効な警告は、以後の表示にも添える。欧文フォントの取得失敗の警告は、そのフォントを選んでいるあいだだけ常時警告に出し（1度だけ）、選び直すと消える（`removeStickyWarning`）。
- コピーのメッセージ: 成功は `ok`「図をクリップボードにコピーしました（PNG、{dpi} dpi、{幅} × {高さ} ピクセル）。」、非対応のブラウザは `warning`「このブラウザでは図をクリップボードにコピーできません。「保存する」で PNG を保存してください。」、ブラウザが書き込みを拒否したときは `error`「クリップボードにコピーできませんでした。ページをクリックしてから、もう一度試してください。」。Python 側の失敗（データ無し、保存設定の不正、画素数、数式など）は保存と同じ表示で、上の拒否のメッセージは重ねない。

## 8. 警告フィルタ

無視する警告は、次の4つだけ。それ以外の警告は無視しない（A10）。

- pandas の pyarrow 関連の `DeprecationWarning`（`runtime.configure_warnings`、起動時）
- matplotlib のグリフ不足の `UserWarning`（`runtime.configure_warnings`、起動時）
- `plt.show()` が Agg で出す `UserWarning`（`FigureCanvasAgg is non-interactive, and thus cannot be shown`）。生成スクリプトも `plt.show()` で終わるため、`runner._execute` の中だけ、`warnings.catch_warnings()` の範囲で無視する（スクリプトの実行が終われば元に戻る。グローバルには設定しない）。
- 区切り文字のエスケープ表記（`loader._decode_escapes`）で、`\d` のような未定義のエスケープを `unicode_escape` で解釈するときに出る `DeprecationWarning`（`... is an invalid escape sequence`）。文字はそのまま残る。`warnings.catch_warnings()` の中で、この種類とメッセージだけを無視する。

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
- Phase 3 で加えた単体テスト:
  - `test_settings.py`: 新しい既定値、単位ごとの図サイズ（インチへの換算と上限）、新しい項目の検証と日本語エラー、DPI の受け入れ（整数・整数に見える数値・数値文字列・空欄）、`migrate_settings`（v1 → v2 で dpi 120、既存の dpi を保つ、`save` が無い設定、3つのパーサ経由、v2 はそのまま、未対応バージョンはエラー）。
  - `test_codegen.py`: 単位ごとの `figsize` の実測値と、cm / mm の丸い値で画素数が欠けないこと、図サイズ部分の文面、`savefig` の `dpi` が PNG / JPG のときだけであること、PDF / SVG の rcParams の行（`formats` と同じ値）、PDF で TrueType が埋め込まれること、欧文フォントのヘッダ（`default` は従来どおり。入っていないフォントで `findfont` の警告が出ないこと、入っていれば使うこと）。
  - `test_runner.py`: PDF が Type 42 であること（スクリプトの助けなしで）、SVG の文字の切替、DPI で画素数が変わること、画素数の上限（ベクター形式には効かない）、`is_mathtext_error`、変換時の数式エラーが `field` 付きの `UserError` になること、`raster_pixels` が Agg と同じ切り捨てであること。
  - `test_api.py`: `save` の DPI と SVG の文字、v1 設定は 120 dpi、`copyImage`（PNG、保存 DPI、背景透過、編集モード、エラーの形）、PDF が TrueType 埋め込みで出力に font の行が混じらないこと、画素数の上限エラー、`registerFont` の種類と `fontStatus`、`script_json`（実行せずコードを返す、エラー）、数式エラー（GUI 同期の `render` / `save` / `copyImage`、軸ラベル・凡例名、編集モードの2経路）。
  - `test_fonts.py`（日本語の先頭が Noto Sans JP）、`test_js_modules.py`（node。単位換算が図の大きさを保つこと、プリセットの点サイズの規則、パレットと state、プリセット無しの `addSeries` が従来どおり）、`test_cdn_pinning.py`（`matplotlib.org` はバージョン付きのパスだけ許可）。
- Phase 3 で加えた E2E:
  - `test_panel_sections.py`（区分の順序・名前・既定で開く、閉じると中身が隠れる、閉じてもステータスが見える、リロードで状態が残る、localStorage が例外を投げても動く、折りたたみ後も描画できる）、`test_style_section.py`（単位切替で数値が換算され図の大きさが変わらない、空欄はそのまま、プリセットは「適用」でだけ効く、scatter の点サイズ、パレットで全系列と色選択パネルが塗り直される）、`test_save_section.py`（DPI の画素数とエラー、保存設定の変更にコードが追従して再描画しない、SVG の文字の切替と PDF の説明、PDF に日本語の TrueType が埋め込まれる）、`test_latin_font.py`（選んだときだけ取得、失敗の警告は1回で再試行しない、リロード後は Cache Storage から、遅いときはフォールバックで描いて1回だけ描き直す、編集モードでは取得するが描かない）、`test_clipboard.py`（保存 DPI の PNG、編集モード、データ無しのエラー、非対応のブラウザの警告）、`test_mathtext_help.py`（数式の案内とリンク、数式エラーの日本語メッセージと復帰）。`test_codegen_consistency.py` は、cm の図サイズなど Phase 3 の設定も一致確認の対象にした。
  - 実フォントを jsDelivr から取得するテストがある（`test_latin_font.py` の一部、`test_save_section.py` の PDF 埋め込みなど。インターネット接続が必要）。`test_font.py`（日本語フォントの失敗・停止・遅延・キャッシュ）は、matplotlib 同梱の小さな TTF を `page.route` で代役にして、5.7 MB の取得を避ける。
  - クリップボードのテストは `page.context.grant_permissions(["clipboard-read", "clipboard-write"])` を許可してから、`navigator.clipboard.read()` で画像を読み戻す。
  - `helpers.py` の Phase 3 用ヘルパー: `natural_size`、`act_and_wait_render`、`series_color`、`palette_grid_colors`、`ARIMO_GLOB` / `TINOS_GLOB`、`image_size`、`save_bytes`、`set_save_dpi`、`latin_font_state` / `wait_latin_state`、`copy_state` / `wait_copy_state`、`read_clipboard_png_size`、`wait_code_contains`。
- Phase 4 で加えた単体テスト:
  - `test_load_options.py`: `skip_lines` / `thousands` / `decimal` / `comment`（csv・xlsx）、前置き行（上限20行）と、指定漏れの ParserError のヒント、xlsx のシート（先頭・無い名前・`ExcelFile` の再利用と id ごとのキャッシュ）、区切り文字との衝突、区切り指定漏れの警告、decimal == 区切り文字の警告（引用符付きの値は読める）、`read_kwargs` が loader と codegen の共通定義であること、生成した読込部と loader の結果の一致、すべての読込引数が明記されること、シート名・ファイル名・コメント記号の注入、A7 のヒント、`split_lines`。
  - `test_datetime.py`: 書式ごとの認識、タイムゾーン（同一オフセット・`Z`・混在で UTC）、前後の空白、90% の境界と先頭 100 個、書式の選び方、警告（例は最大3件）、数値っぽい文字列・曖昧な書式は認識しない、`parseDates` false と Excel の日時セル、loader と生成コードの変換式の一致、日時軸・日時の棒グラフ・文字列の X（25 個超で間引き）の生成コード、`mdates` / `ticker` の import が必要なときだけであること、日時の書式と列名の注入、1万行の読込。
  - `test_multi_source.py`: `Session` の追加・置き換え・削除・全消去と作業フォルダ、一部の失敗、同名ファイル、データ元の解決とエラー、`plan_plot` のデータ元ごとの処理（`skipRows`、Y の自動割り当て、棒グラフは同じデータ元、日時の規則）、2ファイルのスクリプト（`DATA_FILE_N` / `dfN`、使うファイルだけ、番号は位置）、自動描画用の注入、悪意のあるファイル名。`test_paste_tsv.py`: `.tsv`（タブ区切り・空白を含む値・区切りの上書き）と、貼り付けたデータの読込部・使い方のコメント。`test_settings.py`: v3 の既定値と検証、v2 → v3 の移行（`parseDates` false）。`test_js_modules.py`: 新しい系列の `source` が空、`version` が 3。
- Phase 4 で加えた E2E: `test_drop_paste.py`（ドロップの読込とオーバーレイの出入り、文字列のドラッグは無反応、複数ファイル、未対応拡張子、`.tsv`、貼り付け（`#pasteArea`・input・ページ上）、表でない内容の警告、貼り付けたデータのコードと保存、編集モードで `pasted_data.tsv` を読めること、読込済みのときのページ上の貼り付けは置き換えず警告・`#pasteArea` は置き換え）、`test_load_options.py`（シート切替、前置き行の表示、ヨーロッパ形式の数値、コメント記号、桁区切りの警告とヒント、コードの追従、編集モードで読込設定を変えてもコードが変わらない、「最新でない」印）、`test_datetime.py`（日時軸、書式のプリセットと任意、不正な書式、X の範囲指定のエラー、`parseDates` を外す、日本語の日付の棒グラフ、Excel の日時セル、日時とそれ以外の X の混在、タイムゾーン混在の警告）、`test_multi_files.py`（一覧とデータ元の表示、2ファイルの系列、データ元の切替、データ確認の切替、削除と系列の戻し、置き換え、同名、上限、ドロップの追加・置き換え区画、一部の失敗と再試行、シート変更は該当ファイルだけ、編集モードで2ファイルを読む、貼り付けは全置き換え、全削除で初期状態、列が変わらない読込で系列カードを保つ）。`test_codegen_consistency.py` は、前置き行、ヨーロッパ形式、日時の線、xlsx の日時、2枚目のシート、2つの CSV、CSV と xlsx の2枚目、貼り付けたデータの各ケースも一致確認の対象にした。
  - `helpers.py` の Phase 4 用ヘルパー: `change_load_option` / `set_load_options`、`sheet_options`、`code_is_stale`、`drag_event` / `drop_files` / `drop_overlay_visible`、`paste_text`、`add_files`、`file_row_ids` / `file_row_states`、`settings_files`、`add_series_with_source`、`remove_file`。
- E2E は要素を id だけで選ぶ。`index.html` の id は安定させ、変えるときはテストも直す。アプリ固有の待機・操作は `tests/e2e/helpers.py` にまとめる。
- テストデータは `tests/fixtures/` の合成データだけ（公開リポジトリなので実データを置かない）。
- テスト用サーバー（`tests/e2e/server.py`）は listen backlog を 128 に広げている。既定の 5 だと、Chromium が ES モジュールを一斉に取得したときに接続が切れて、アプリが起動しないことがある。
- 環境変数 `E2E_BASE_PATH=/matplotlib_gui/` を付けると、Pages と同じサブパス配下で配信して検証する（絶対パス参照の検出）。`E2E_SERVE_DIR` で配信ディレクトリを変えられる（CI は Jekyll のビルド結果 `_site`）。

## 11. CI と GitHub Pages

- CI（`.github/workflows/tests.yml`）: push で単体テスト、プルリクエストで E2E。E2E は Jekyll でビルドした `_site` を `/matplotlib_gui/` 配下で配信して検証する。
- Jekyll は `_` で始まるファイルを既定で配信しない。`__init__.py` は `_config.yml` の `include` で明示している。開発用ファイル（`docs/`、`tests/`、`AGENTS.md`、`pyproject.toml`、`uv.lock`、`.github/` など）は `exclude`。
- `test_cdn_pinning.py` は、フォント（`@expo-google-fonts/*@x.y.z`、`@fontsource/*@x.y.z`）の jsDelivr URL と、バージョン付きのパスの `matplotlib.org`（取得しない説明リンク）を許可する。新しい JS モジュール（`js/units.js`、`js/ui/dropPaste.js`、`js/ui/fileList.js` など）は静的ファイルとしてそのまま公開される（`pyscript.toml` は Python ファイルだけ）。Phase 4 では新しい Python モジュールも CDN も足していない（`pyscript.toml` と CI の変更なし）。
- 新しい Python モジュールを追加したら、`pyscript.toml` の `[files]` に必ず追加する（`tests/unit/test_pages_publish.py` が参照ファイルの公開を確認する）。
- matplotlib 3.10 では `tight_layout()` 後に `PlaceHolderLayoutEngine` が残り、`savefig` が余分に全体を再描画する。`runner.drop_placeholder_layout_engine` がこれを外している（出力は同一）。

## 12. 運用ルール（必須）

- このリポジトリ配下のみを対象に作業する。リポジトリ外のファイルには触れない。
- push やプルリクエストの作成は、オーナーの確認を取ってから行う。
- ローカル環境のパスを、リポジトリ内の文書やコードに書かない。

## 13. オーナーが決めたこと

### 13.1 Phase 2（2026-10-08）

- 旧「Pythonコード(beta)」タブの名前空間（`get_plot_data`、従来形式の settings dict、`plotted_count`）は、互換を残さずに廃止した。
- 生成スクリプトの最後は `fig.savefig(...)`（GUI の「保存」と同じ形式・解像度）と `plt.show()`。
- 編集は明示的な「編集」ボタンで始める。`useCustomCode`（「使用する」）は廃止した。編集中は GUI の変更で、コードも図も変わらない。
- 棒グラフ（1系列・複数系列）は、カテゴリの目盛ラベルを保つ（Phase 1 の不具合を修正）。複数系列は、棒の位置にラベルを付ける（25個を超えたら間引く）。
- line / scatter で X が数値でない列（文字列・日時）のとき、Phase 1 と同じ見た目を保つため、生成コードに `ax.set_xscale("linear")` を入れる（目盛は位置の番号になる）。D5（日付軸）で見直す（Phase 4）。→ Phase 4 でやめた（§13.3）。
- ファイル選択欄に、選んだファイル名を欄の中に表示する（`#fileNameLabel`。`input` は選択のたびに空に戻すため、JS が表示する）。

### 13.2 Phase 3（2026-10-08）

- 手動確認（2026-10-08、オーナーが確認。いずれも問題なし）: Illustrator で PDF の文字を編集できること。Safari と Firefox の実機で、クリップボードへのコピーが動くこと。
- 保存 DPI の既定値は 300（U1）。選択肢は 72 / 150 / 300 / 600 と任意の値。プレビューは今までどおり dpi 100 で描く。
- 図サイズの既定の単位は inch（8×6 を維持。U2）。cm と mm も選べる。単位を切り替えたら入力欄の数値を換算する（図の大きさは変えない。例: 8 inch → 20.32 cm）。設定には「選んだ単位の値」と単位を持つ（インチに直して持たない）。
- 欧文フォントは Arimo（Arial 互換）と Tinos（Times 互換。U3）。ライセンスはどちらも SIL OFL 1.1（要件定義書の当初の「Apache 2.0」は誤り）。選んだときだけ、バージョン固定の jsDelivr から取得する。日本語の文字は Noto Sans JP で描く（matplotlib の文字単位のフォールバック）。Tinos のときは数式（mathtext）を STIX にする。
- 日本語フォントを、Noto Sans CJK JP（OTF、CFF 形式）から、同じデザインの TrueType 版 Noto Sans JP に替えた。matplotlib 3.10 は CFF 形式のフォントを `pdf.fonttype=42` で正しく埋め込めない（TrueType 用の FontFile2 に CFF を入れ、PDF が壊れる）ため。
- PDF は Type 42（`pdf.fonttype=42`）で書き出す。SVG の文字は「パスに変換」（既定）と「テキストのまま」を選べる。
- スタイルプリセット（標準 / 論文1段組 / 論文2段組 / スライド16:9）は「適用」ボタンで値をまとめて書き込むだけで、設定にプリセット名を残さない。点サイズは、点を表示している系列（scatter、または点サイズを入力した line）だけ書き換える（標準は点サイズを「自動」に戻す）。適用後に追加した系列は、直前に適用したプリセットの値（線幅と、scatter のときの点サイズ）を使う（セッション中だけ JS が覚える）。
- カラーパレット（UD カラー / tab10 / グレースケール）を切り替えたら、すべての系列を、系列の順に新しいパレットの色で塗り直す（個別に選んだ色も上書きする）。
- クリップボードにコピーする画像（C5）は、保存 DPI と同じ解像度の PNG。背景透過は保存設定に従う。
- 左パネルを「データ読み込み」「系列」「軸・目盛」「体裁」「保存」の区分に整理し、各区分を `<details>` で折りたためるようにする。折りたたみの状態は localStorage に保持する。「注釈・解析」の区分は Phase 5 まで作らない。
- 設定スキーマを version 2 にした。v1 からの移行では、v1 の保存が常に 120 dpi だったため `save.dpi` を 120 にする。
- 「描画設定: 先頭からスキップする行数」の欄名を「描画から除外する先頭行数」に改めた（「描画設定」の区分が無くなったため）。

### 13.3 Phase 4（2026-10-08）

- D6（複数ファイル）も Phase 4 に含める。読込設定（区切り文字、ヘッダ、読み飛ばす行数、桁区切り、小数点、コメント記号、日時の認識）は全ファイル共通で、シートだけファイルごとに選ぶ。棒グラフは、すべての系列が同じデータ元のときだけ描ける。同じ名前のファイルは置き換えとして扱う（作業フォルダと生成コードでファイルを名前で区別するため）。読み込めるのは 10 個まで。
- 設定スキーマを version 3 にした。v2 からの移行では `load.parseDates` を false にする（v2 までの出力を保つため。新しく作る設定の既定値は true）。
- ドラッグ&ドロップはページ全体で受ける。データを読み込み済みのときは、「置き換えて読み込む」「追加して読み込む」のどちらにドロップするかで選ぶ。
- 貼り付けたデータは `pasted_data.tsv`（UTF-8、タブ区切り）というファイルとして扱い、生成コードはこのファイルを読む（データはスクリプトに埋め込まない）。「貼り付けたデータを保存」で同じ内容を保存し、スクリプトと同じフォルダに置いてもらう。あわせて `.tsv` を対応する拡張子に加えた（既定の区切り文字はタブ）。
- 「ヘッダより前に読み飛ばす行数」は「データ読み込み」の区分に、「描画から除外する先頭行数」は「系列」の区分に置き、補足で何を数えるかを示す。読み飛ばした行は、データ確認タブの表の上に枠で囲んで表示する（描画から除外する行のグレー表示とは見た目を分ける）。
- 桁区切り・小数点・コメント記号は pandas の `thousands` / `decimal` / `comment` で扱い、生成コードの読込部には、すべての読込引数を既定値も含めて明記する。区切り文字の自動判定は加えない（指定漏れが疑われるときは警告で案内する）。
- 日時の列の認識（規則は §7）: 年が先頭の書式だけ。月日の順が曖昧な書式、時刻だけ、年月だけは認識しない。読めない値は欠損にして警告する。タイムゾーンは、同じオフセットなら書かれた時刻のまま、混在していたら UTC にそろえる（警告する）。Excel の日付セルは常に日時として扱う。
- 日時の X 軸の目盛は、自動（`AutoDateLocator` と `ConciseDateFormatter`）か、指定した書式（`DateFormatter`）にする。X が日時のときは、X 軸の対数と範囲の指定はできない（日本語のエラーで案内する）。棒グラフで X が日時のときは、表示書式で文字列にしてカテゴリとして並べる。
- Phase 2 で入れた `ax.set_xscale("linear")`（X が数値でない列のとき）はやめた。日時の列は日時軸にし、それ以外の文字列の列は目盛に値を出す（25個を超えるときは間引く）。
- Pythonコードタブが GUI 同期のとき、エラーで最新の設定のコードを作れなかったら、表示中のコードが最新でないことをタブ内に表示する（`#codeStaleNote`）。
- レビュー後の決定: 小数点と区切り文字が同じ記号のときはエラーにせず警告にする（引用符で囲まれた値は読めるため）。ページ上の貼り付け（`#pasteArea` 以外）は、読み込み済みのデータを置き換えない（未読込のときだけ読み込む。置き換えは「表を貼り付け」欄で行う）。最後のファイルを削除したら、起動直後の状態に戻す。
