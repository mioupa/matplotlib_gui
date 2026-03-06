# matplotlibをブラウザGUIで操作するための実装方針（引き継ぎ用・詳細）

## 1. ゴール
- `index.html` をブラウザで開くだけで `matplotlib` 描画をGUI操作する。
- サーバー（FastAPI等）は使わず、ブラウザ内Python実行（PyScript / Pyodide）で完結する。
- 入力ファイルは `.xlsx / .csv / .txt` に対応する。

## 2. 現在の実装構成
- 実装ファイルは **`index.html` 単体**。
- 構成要素:
  - HTML/CSS: 画面UI（設定フォーム、タブ、データ表、色オーバーレイ）
  - JavaScript: 自動読込/自動描画の制御、系列カードUI、色選択UI、エラー抑制
  - Python（`<py-script>`内）:
    - 読み込み処理: `pandas`
    - 描画処理: `matplotlib`
    - DOM連携: `js` / `pyodide.ffi.create_proxy`
- `py-config` のパッケージ:
  - `pandas`
  - `matplotlib`
  - `openpyxl`

## 3. 画面仕様（現在）
### 3.1 データ読み込み
- 入力ファイル選択（`.xlsx/.csv/.txt`）
- 区切り文字
- ヘッダ有無
- 読み込みボタンは廃止済み（自動読込）

### 3.2 描画設定
- プロット種別: `line / scatter / bar`
- スキップ行数: 「描画設定」先頭に配置
- 系列はカード方式（`+ 系列を追加`）で複数追加可能
  - 各系列: X列、Y列、色、線幅、線種、点サイズ、凡例名（任意）、第2軸使用
- タイトル、X/Yラベル
- 第2Yラベル（第2軸系列が1つでもある時のみ表示）
- フォントサイズ（既定15）
- major/minor目盛線の表示切替
- 凡例位置（日本語ラベルで選択）
- 図幅/図高さ（既定 8x6）
- 描画ボタンは廃止済み（自動描画）

### 3.3 保存設定
- 保存ファイル名（空欄時は `plot.<拡張子>`）
- 保存形式: `png / jpg / svg / pdf`
- 保存ボタンでダウンロード

### 3.4 表示エリア
- タブ切替: `プロット / データ確認`
- データ確認は先頭100行を表示
- 行番号列 `#` を表示
- `skipRows` 対象の先頭行はグレーアウト（描画で除外される行を視覚化）

## 4. 自動処理の仕様
- ファイル選択・区切り文字変更・ヘッダ変更時: 自動で再読込。
- 描画設定変更時: 自動で再描画。
- 成功時はステータスに成功メッセージを表示。
- エラー時のみエラーメッセージを表示。

## 5. 系列と描画ロジック
- 同名列対応のため列指定値は `__idx__<列番号>` 形式を維持。
- `line` と `scatter` は系列ごとにX列指定可能。
- `bar` は共通X列を使用。
- `line` でも点表示可（点サイズ > 0 で表示）。
- 点サイズの既定:
  - `line`: 0
  - `scatter`: 24
- `scatter`選択時、点サイズが0以下なら自動で24に補正。
- `scatter` から `line` に戻す際、24のままなら0へ戻す。
- 線幅の既定は2。
- 各系列で第2軸を有効化可能（`twinx`）。

## 6. 色指定UI
- UDカラーセットを既定候補として提供:
  - `#FF4B00`, `#005AFF`, `#03AF7A`, `#4DC4FF`, `#F6AA00`, `#FFF100`, `#990099`, `#84919E`, `#000000`, `#804000`, `#FF8082`
- 色選択はオーバーレイパネル表示。
- 色チップは正方形固定。
- 「カスタム」ボタンは1クリックでカラーピッカーを開く。
- パネル外クリックでオーバーレイを閉じる。

## 7. 軸・目盛り・凡例
- 目盛りは内向き（`direction='in'`）。
- 不要側のヒゲは表示しない:
  - 主軸: 下・左
  - 第2軸: 右
- major/minor目盛線は個別ON/OFF可能。
- 凡例位置は選択可能。`none` で非表示。
- 第2軸あり時は主軸・第2軸のハンドルをマージして凡例表示。

## 8. 日本語フォント対応
- CSSは `Noto Sans JP` を既定フォントに設定。
- matplotlib側は `Noto Sans JP / Noto Sans CJK JP` を優先。
- 必要時はNoto CJKフォントをWeb取得して `font_manager.addfont` で登録。
- オフライン時や取得失敗時はフォールバックフォントで継続。

## 9. エラー/警告抑制（重要）
- `parentNode` 系例外は JS/Python 両側で抑制・回復。
- `PyodideTask exception was never retrieved` は `_spawn_task` で回収。
- pandas `pyarrow` DeprecationWarning は抑制。
- 日本語glyph不足のUserWarningは抑制。
- ただし、ユーザー入力や設定不整合による本来のエラーは表示する。

## 10. 主なPython関数
- `_read_upload`: ブラウザ選択ファイルをbytes取得
- `_load_dataframe`: 拡張子別にDataFrame化
- `_resolve_column` / `_parse_column_index` / `_get_series_from_request`: 列解決
- `_collect_series_settings`: 系列カードから設定収集
- `_get_plot_data` / `_get_per_series_xy_data`: 描画データ整形
- `_create_plot_figure`: 描画本体（line/scatter/bar + 二軸 + grid + 凡例）
- `_render_data_preview`: データ確認テーブル描画（skipRows可視化込み）
- `_render_plot_image`: 図をPNG data URIで表示
- `on_load_columns`, `on_render`, `on_save_plot`: 主処理

## 11. 引き継ぎ時の注意
- 「ブラウザ完結（サーバーなし）」前提を崩さないこと。
- 同名列対応のため、列指定は必ず列番号ベースを維持すること。
- `parentNode` 系の抑制・回復ロジックは削除しないこと。
- 自動読込/自動描画のUX（手動ボタンなし）を維持すること。
- データ確認タブの「skipRowsグレーアウト可視化」を維持すること。

## 12. 運用ルール（必須）
- このプロジェクトでは、`/Users/miura/Documents/projects/matplolib_gui` 配下のみを対象に作業する。
- このディレクトリ外のファイルには一切触れない。
