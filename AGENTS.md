# matplotlib GUI 引き継ぎ資料（AI エージェント向け）

要件の正は `docs/REQUIREMENTS.md`。このファイルと食い違う場合は REQUIREMENTS.md を優先する。
この資料は Phase 1（基盤の刷新と不具合修正）完了時点の実装を説明する。各 Phase の完了時に実装に合わせて更新すること（要件 A11）。

## 1. ゴールと前提

- CSV / TXT / XLSX のデータから、ブラウザ上の GUI だけで matplotlib の図を作る。
- 利用形態は GitHub Pages 配信（公開 URL: https://mioupa.github.io/matplotlib_gui/）。`file://` で直接開く使い方は非対応。
- サーバー処理を持たない。計算はすべてブラウザ内の Python（PyScript / Pyodide）で行う。GitHub Pages は静的配信のみに使う。
- 読み込んだデータは外部に送信しない。外部への通信はライブラリとフォントの取得だけ。
- 列の指定は列番号（`__idx__N`）で行う。同名の列があっても区別できる。
- 自動読込・自動描画を保つ（「読み込む」「描画する」ボタンは置かない）。
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
| `js/state.js` | 設定オブジェクトの保持・更新・購読（`getSettings`、`setPath`、`updateSeries`、`addSeries`、`removeSeries`、`subscribe`、`toJson`） |
| `js/bridge.js` | Python（`window.mplgui`）の唯一の窓口。読込・描画・保存の制御、世代管理、フォント取得の起動 |
| `js/startup-progress.js` | Python 起動中の段階表示。Resource Timing（`PerformanceObserver`、取得済みエントリを含む）から Pyodide 本体（`pyodide.asm.wasm`・`python_stdlib.zip`）→ パッケージ wheel（pandas / matplotlib）→ 初期化（`/py/main.py` の取得）を推定する |
| `js/font-cache.js` | 日本語フォントの取得と Cache Storage への保存 |
| `js/ui/*.js` | 画面部品（`colorPicker`、`customCode`、`dataPreview`、`fileInfo`、`forms`、`notify`、`plotView`、`progress`、`saveFormat`、`series`、`tabs`） |
| `py/main.py` | PyScript のエントリ。JS と `mplgui` の橋渡しだけを書く（`window.mplgui` の登録、Excel 用ライブラリの遅延導入） |
| `py/mplgui/settings.py` | 設定スキーマ、既定値、検証、日本語エラー（凍結 dataclass へ変換） |
| `py/mplgui/loader.py` | バイト列から DataFrame（文字コード判定、区切り文字、プレビュー） |
| `py/mplgui/plotting.py` | 描画本体（暫定。Phase 2 で codegen に置き換える） |
| `py/mplgui/runner.py` | Figure の生成と、画像（PNG/JPG/SVG/PDF）への書き出し、カスタムコードの実行 |
| `py/mplgui/fonts.py` | 日本語フォントの登録と rcParams |
| `py/mplgui/errors.py` | `UserError`（利用者が直せるエラー） |
| `py/mplgui/api.py` | JS から呼ばれる JSON 入出力の関数 |
| `py/mplgui/runtime.py` | 警告フィルタ |
| `tests/unit/` | 単体テスト（CPython、Agg） |
| `tests/e2e/` | E2E テスト（pytest-playwright、Chromium） |
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
- カスタムコードの本文と「使用する」は設定オブジェクトには入れず、`render` / `save` の別引数で渡す。

## 4. Python ⇄ JS の API（`window.mplgui`）

Python が登録し、登録後に `mplgui-ready` イベントを送る。引数・戻り値は JSON 文字列（ファイルとフォントはバイト列）。

| 関数 | 引数 | 戻り値（`ok: true` のとき） |
|---|---|---|
| `ensureExcel()` | なし（非同期） | `{ok}`。初回の .xlsx 読込前に openpyxl を導入する |
| `loadFile(name, bytes, loadJson)` | ファイル名、内容、`{version, load}` | `{encoding, columns, preview, warnings}`（.xlsx は `encoding: null`） |
| `render(settingsJson, customCode)` | 設定 JSON、コード文字列または null | `{image, seriesCount, skipRows, warnings}`（`image` は PNG の data URI） |
| `save(settingsJson, customCode)` | 同上 | `{filename, mime, dataUri}` |
| `registerFont(bytes)` | フォントのバイト列 | `{registered}` |
| `fontStatus()` | なし | `{registered}` |
| `defaultCustomCode()` | なし | 文字列（JSON ではない） |

- `warnings` は `{series, message}` の配列（読込時は文字列配列の場合もある。JS の `warningTexts` が吸収する）。
- 失敗: `{ok: false, error: {message, field?, detail?}}`。
  - 利用者が直せる原因は `UserError`。`message` は日本語で、どの項目が悪いかを含める（`field`）。
  - それ以外の例外は内部エラー。短い日本語メッセージ（`INTERNAL_ERROR_MESSAGE`）に、`detail` として traceback を付ける（画面の「内部エラー詳細」に出る）。
- `loadFile` が失敗したら読込済みデータを破棄する。`render` は読込済みデータが無いと「先にファイルを読み込んでください。」を返す。

## 5. 描画パイプライン

- 描画は設定変更の 250 ms 後（デバウンス）。読込は、ファイル選択・ヘッダ変更で 0 ms、区切り文字の変更で 450 ms 後。保存設定（`save.*`）の変更では再描画しない。`skipRows` の変更は Python を呼ばず、データ確認表のグレー表示だけ即時に更新する。
- 起動中の `#progress`（`aria-live="polite"`）は段階表示: 「Python 実行環境を読み込み中…」→「ライブラリを読み込み中…（pandas ✓, matplotlib …）」→「ライブラリを初期化中…」→ 準備完了で消える（フォント取得の表示が続く場合あり）。`<html>` の `data-startup-stage`（`runtime` / `packages` / `init` / `ready`）に現在の段階が入る。新しい id は無い。読込失敗の案内（`data-load-failed`）は上書きしない。
- 描画要求には世代番号を付ける。Python の描画は同時に最大1つ。実行中に新しい要求が来たら「やり直し」の印だけ付け、終了後に最新の設定で1回だけ描く（合流）。古い世代の結果は画像にもステータスにも反映しない。
- Python の起動前に選んだファイルや変えた設定は保持し、起動後に最新の内容で1回読み込んで描く（起動キュー）。
- E2E が使う状態は `<html>` の data 属性: `data-app-state`（`starting` / `ready` / `failed`）、`data-data-state`（`none` / `loading` / `ready` / `error`）、`data-render-state`（`idle` / `pending` / `rendering`）、`data-render-generation`、`data-font-state`（`idle` / `loading` / `ready` / `failed`）、`data-load-count`。表示中の画像は `#plotArea img` の `data-generation` を持つ。ステータスは `#status` の `data-kind`。

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
- 数値に変換できず除外した値は、系列ごとに警告にする（`plotting.dropped_warning`）。
- ステータス（`#status`）の種別は `ok` / `warning` / `error`。警告は成功メッセージに添えて表示し、`error` のときは `data-kind="error"`。日本語フォント取得失敗のような常時有効な警告は、以後の表示にも添える。

## 8. 警告フィルタ

`runtime.configure_warnings` が無視するのは、次の2つだけ。それ以外の警告は無視しない（A10）。

- pandas の pyarrow 関連の `DeprecationWarning`
- matplotlib のグリフ不足の `UserWarning`

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
