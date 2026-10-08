"""JS から呼ばれる JSON 入出力の API（純粋な Python。js / pyodide には依存しない）。

py/main.py はこの関数を window.mplgui に登録するだけ。引数・戻り値はすべて JSON 文字列（ファイル/フォントはバイト列）。
成功: {"ok": true, ...}  失敗: {"ok": false, "error": {"message", "field"?, "detail"?}}
"""
from __future__ import annotations

import base64
import json
import struct
import traceback
from pathlib import Path

from . import fonts
from .codegen import GENERIC_ERROR_MESSAGE, GeneratedScript, generate_script
from .dataprep import plan_plot
from .errors import UserError
from .formats import build_filename
from .loader import PREVIEW_ROWS, SourceInfo, build_preview, column_options, load_file
from .runner import MathtextError, ScriptError, is_mathtext_error, run_to_image
from .settings import Settings, parse_load_settings, parse_save_settings, parse_settings

PREVIEW_DPI = 100
MATHTEXT_ERROR = (
    "タイトル・軸ラベル・凡例名の数式（$ で囲んだ部分）を解釈できませんでした。書き方を確認してください"
    "（例: m$^2$、H$_2$O、$\\alpha$）。$ を文字として使うときは \\$ と書きます。"
)
INTERNAL_ERROR_MESSAGE = "内部エラーが発生しました。もう一度操作してください。"


class Session:
    """読み込み済みデータ（ブラウザのタブごとに1つ）。"""

    def __init__(self):
        self.df = None
        self.filename = None
        self.source: SourceInfo | None = None
        self.workdir: Path | None = None  # 設定すると、アップロードしたファイルを元の名前でここに置く
        self._written: Path | None = None

    def forget(self) -> None:
        self.df = None
        self.filename = None
        self.source = None
        self._remove_written()

    def _remove_written(self) -> None:
        if self._written is not None:
            try:
                self._written.unlink()
            except OSError:
                pass
            self._written = None

    def write_upload(self, name: str, data: bytes) -> None:
        """編集モードのスクリプトが読めるように、アップロードしたファイルを workdir に置く（前のファイルは消す）。"""
        if self.workdir is None:
            return
        base = Path(name).name
        if base in {"", ".", ".."}:
            self._remove_written()
            return
        target = self.workdir / base
        if self._written is not None and self._written != target:
            self._remove_written()
        target.write_bytes(data)
        self._written = target


SESSION = Session()


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _error_payload(exc: BaseException, context: str) -> dict:
    if isinstance(exc, UserError):
        payload = {"ok": False, "error": exc.to_dict()}
        output = getattr(exc, "output", None)
        if output is not None:
            payload["output"] = output
        return payload
    detail = f"context: {context}\ntype: {type(exc).__name__}\nmessage: {exc}\n\ntraceback:\n{traceback.format_exc().strip()}"
    return {"ok": False, "error": {"message": INTERNAL_ERROR_MESSAGE, "detail": detail}}


def _guard(context: str):
    def deco(fn):
        def wrapper(*args, **kwargs):
            try:
                return _dumps(fn(*args, **kwargs))
            except Exception as exc:  # noqa: BLE001 - 境界。UserError 以外は内部エラーとして詳細つきで返す
                return _dumps(_error_payload(exc, context))

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return deco


def _parse_json(text: str) -> dict:
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        raise UserError("設定を解釈できませんでした。ページを再読み込みしてください。", detail=str(exc)) from exc
    return data


@_guard("load_file")
def load_file_json(name: str, data: bytes, load_settings_json: str) -> dict:
    """ファイルを読み込み、列の選択肢とプレビューを返す。失敗時は読込済みデータを破棄する。"""
    SESSION.forget()
    load = parse_load_settings(_parse_json(load_settings_json))
    raw = bytes(data)
    loaded = load_file(raw, name, load.delimiter, load.has_header)
    SESSION.df = loaded.df
    SESSION.filename = name
    SESSION.source = loaded.source
    SESSION.write_upload(name, raw)
    return {
        "ok": True,
        "encoding": loaded.encoding,
        "columns": column_options(loaded.df),
        "preview": build_preview(loaded.df, PREVIEW_ROWS),
        "warnings": [],
    }


def _source_info() -> SourceInfo:
    if SESSION.source is not None:
        return SESSION.source
    name = Path(SESSION.filename or "data.csv").name
    kind = Path(name).suffix.lower().lstrip(".") or "csv"
    return SourceInfo(filename=name, kind=kind, encoding="utf-8", separator=",", has_header=True,
                      sheet_name="Sheet1" if kind == "xlsx" else None)


def _step_error(script: GeneratedScript, err: ScriptError) -> ScriptError:
    """生成コードの実行時エラーを、失敗した手順に応じた日本語メッセージにする（数式の書き間違いは専用のメッセージ）。"""
    if is_mathtext_error(err.exc):
        return ScriptError(
            MATHTEXT_ERROR, field="数式", detail=err.detail, traceback_text=err.traceback_text,
            line=err.line, output=err.output, exc=err.exc,
        )
    step = script.step_for_line(err.line)
    mapped = ScriptError(
        step.message if step else GENERIC_ERROR_MESSAGE,
        field=step.field if step else None,
        detail=err.detail,
        traceback_text=err.traceback_text,
        line=err.line,
        output=err.output,
        exc=err.exc,
    )
    return mapped


def _generate(settings: Settings):
    if SESSION.df is None:
        raise UserError("先にファイルを読み込んでください。")
    plan = plan_plot(SESSION.df, settings)
    return plan, generate_script(settings, _source_info(), plan)


def _run(settings: Settings | None, code: str | None, *, file_format: str, transparent: bool, dpi: int, svg_text: str = "path"):
    """GUI 同期（code が None）: 設定から生成したスクリプトを、読込済みの df で実行する（読込・保存の行は空にする）。
    編集モード（code が文字列）: そのスクリプトを、アップロードしたファイルのある作業フォルダで実行する。設定は使わない。"""
    if code is None:
        plan, script = _generate(settings)
        try:
            result = run_to_image(
                script.auto_render_text(), file_format=file_format, transparent=transparent, dpi=dpi, svg_text=svg_text,
                injected={"df": SESSION.df},
            )
        except ScriptError as err:
            raise _step_error(script, err) from err
        except MathtextError as err:  # スクリプトは動いたが、画像にするときに数式の誤りが見つかった
            mapped = UserError(MATHTEXT_ERROR, field="数式", detail=err.detail)
            mapped.output = getattr(err, "output", "")
            raise mapped from err
        return plan, script, result
    return None, None, run_to_image(
        code, file_format=file_format, transparent=transparent, dpi=dpi, svg_text=svg_text, cwd=SESSION.workdir
    )


def _data_uri(result) -> str:
    return f"data:{result.mime};base64,{base64.b64encode(result.data).decode('ascii')}"


@_guard("script")
def script_json(settings_json: str) -> dict:
    """設定から生成したスクリプトだけを返す（実行しない）。保存設定の変更で、表示中のコードを更新するのに使う。"""
    settings = parse_settings(_parse_json(settings_json))
    _, script = _generate(settings)
    return {"ok": True, "code": script.text}


@_guard("render")
def render_json(settings_json: str, code: str | None = None) -> dict:
    """PNG（data URI）を返す。code が None なら設定どおりに描き、文字列ならそのコードを実行する。"""
    settings = parse_settings(_parse_json(settings_json)) if code is None else None
    plan, script, result = _run(settings, code, file_format="png", transparent=False, dpi=PREVIEW_DPI)
    payload = {"ok": True, "image": _data_uri(result), "output": result.output, "summary": result.summary}
    if plan is not None:
        payload.update(seriesCount=plan.plotted_count, skipRows=plan.skip_rows, warnings=list(plan.warnings), code=script.text)
    return payload


def _save_settings(settings_json: str, code: str | None):
    """保存系の API が使う保存設定を返す。編集モードは保存設定だけを検証する（描画設定が不正でも保存できる）。"""
    raw = _parse_json(settings_json)
    settings = parse_settings(raw) if code is None else None
    save = settings.save if settings is not None else parse_save_settings(raw)
    return settings, save


@_guard("save")
def save_json(settings_json: str, code: str | None = None) -> dict:
    """保存設定の形式・解像度で図を書き出し、data URI とファイル名を返す（ダウンロードは JS が行う）。"""
    settings, save = _save_settings(settings_json, code)
    _, _, result = _run(
        settings, code, file_format=save.format, transparent=save.transparent, dpi=save.dpi, svg_text=save.svg_text
    )
    return {
        "ok": True,
        "filename": build_filename(save.filename, result.ext),
        "mime": result.mime,
        "dataUri": _data_uri(result),
        "output": result.output,
    }


@_guard("copy_image")
def copy_image_json(settings_json: str, code: str | None = None) -> dict:
    """クリップボードにコピーする画像。保存形式にかかわらず、保存 DPI の PNG（背景透過は保存設定に従う）。"""
    settings, save = _save_settings(settings_json, code)
    _, _, result = _run(settings, code, file_format="png", transparent=save.transparent, dpi=save.dpi)
    width, height = struct.unpack(">II", result.data[16:24])  # PNG の IHDR（幅・高さ）
    return {
        "ok": True,
        "mime": result.mime,
        "dataUri": _data_uri(result),
        "width": width,
        "height": height,
        "output": result.output,
    }


def script_filename(save_filename: str) -> str:
    """「.py で保存」のファイル名。保存ファイル名と同じ規則（formats.build_filename）で拡張子を .py にする。"""
    return build_filename(str(save_filename or ""), "py")


def register_font(data: bytes, kind: str = "japanese") -> str:
    """JS が取得したフォントを登録する。kind は "japanese" | "arimo" | "tinos"（種類ごとに1回だけ登録する）。"""
    try:
        if kind not in fonts.FONT_FILENAMES:
            raise UserError(f"未対応のフォントの種類です（{kind}）。", field="フォント")
        return _dumps({"ok": True, "registered": fonts.register_font_bytes(bytes(data), kind=kind), "kind": kind})
    except Exception as exc:  # noqa: BLE001
        return _dumps(_error_payload(exc, "register_font"))


def font_status() -> str:
    return _dumps({"ok": True, "registered": fonts.is_registered(), "kinds": fonts.registered_kinds()})
