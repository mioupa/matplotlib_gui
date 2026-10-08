"""JS から呼ばれる JSON 入出力の API（純粋な Python。js / pyodide には依存しない）。

py/main.py はこの関数を window.mplgui に登録するだけ。引数・戻り値はすべて JSON 文字列（ファイル/フォントはバイト列）。
成功: {"ok": true, ...}  失敗: {"ok": false, "error": {"message", "field"?, "detail"?}}
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import struct
import traceback
from pathlib import Path

from . import fonts, loader
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


@dataclasses.dataclass
class LoadedSource:
    """読み込み済みの1つのファイル（データN）。"""

    id: str
    name: str
    df: object
    info: SourceInfo
    written: Path | None = None  # 作業フォルダに書き出したファイル


class Session:
    """読み込み済みデータ（ブラウザのタブごとに1つ）。ファイル id（"d1", "d2", ...）ごとに DataFrame を持つ。"""

    def __init__(self):
        self.sources: dict[str, LoadedSource] = {}
        self.workdir: Path | None = None  # 設定すると、アップロードしたファイルを元の名前でここに置く
        self.excels: dict[str, tuple[str, object]] = {}  # id → (バイト列のハッシュ, 開いた pd.ExcelFile)。シートの切り替えを速くする

    # ---- 先頭のデータ元（1ファイルのときの従来の窓口）----
    def _first(self) -> LoadedSource | None:
        return next(iter(self.sources.values()), None)

    @property
    def df(self):
        first = self._first()
        return first.df if first else None

    @property
    def filename(self):
        first = self._first()
        return first.name if first else None

    @property
    def source(self) -> SourceInfo | None:
        first = self._first()
        return first.info if first else None

    @property
    def excel(self):
        entry = self.excels.get("d1") or next(iter(self.excels.values()), None)
        return entry[1] if entry else None

    # ---- データ元の操作 ----
    def forget(self, keep_excel: bool = False) -> None:
        """すべてのデータ元と、作業フォルダに書き出したファイルを破棄する。"""
        for sid in list(self.sources):
            self.forget_source(sid, keep_excel=True)
        if not keep_excel:
            for sid in list(self.excels):
                self.drop_excel(sid)

    def forget_source(self, sid: str, keep_excel: bool = False) -> None:
        src = self.sources.pop(sid, None)
        if src is not None:
            self._remove_written(src)
        if not keep_excel:
            self.drop_excel(sid)

    def drop_excel(self, sid: str) -> None:
        entry = self.excels.pop(sid, None)
        if entry is not None:
            try:
                entry[1].close()
            except Exception:  # noqa: BLE001 - 閉じられなくても続行する
                pass

    def excel_for(self, sid: str, raw: bytes):
        """raw（xlsx のバイト列）の ExcelFile。同じバイト列なら開き直さない。"""
        key = hashlib.sha256(raw).hexdigest()
        entry = self.excels.get(sid)
        if entry is None or entry[0] != key:
            self.drop_excel(sid)
            self.excels[sid] = (key, loader.open_excel(raw))
        return self.excels[sid][1]

    def _remove_written(self, src: LoadedSource) -> None:
        path, src.written = src.written, None
        if path is None or any(o.written == path for o in self.sources.values() if o is not src):
            return  # 同じ名前のファイルを別のデータ元も使っているときは消さない
        try:
            path.unlink()
        except OSError:
            pass

    def write_upload(self, src: LoadedSource, data: bytes) -> None:
        """編集モードのスクリプトが読めるように、アップロードしたファイルを workdir に置く。"""
        if self.workdir is None:
            return
        base = Path(src.name).name
        if base in {"", ".", ".."}:
            return
        target = self.workdir / base
        target.write_bytes(data)
        src.written = target


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
def load_file_json(name: str, data: bytes, load_settings_json: str, source_id: str = "d1", pasted: bool = False) -> dict:
    """ファイルを読み込み、列の選択肢とプレビューを返す。同じ source_id のデータ元だけを置き換える。
    失敗したときは、その source_id のデータ元だけを破棄する（ほかのデータ元は残る）。

    xlsx のシートは、読み込み設定の load.files のうち source_id の項目から決める（無ければ先頭のシート）。"""
    SESSION.forget_source(source_id, keep_excel=True)
    load = parse_load_settings(_parse_json(load_settings_json))
    raw = bytes(data)
    sheet = next((f.sheet for f in load.files if f.id == source_id), "")
    excel = None
    if Path(name).suffix.lower() == ".xlsx":
        excel = SESSION.excel_for(source_id, raw)
    else:
        SESSION.drop_excel(source_id)
    loaded = load_file(
        raw, name, load.delimiter, load.has_header,
        skip_lines=load.skip_lines, thousands=load.thousands, decimal=load.decimal, comment=load.comment,
        sheet=sheet, excel=excel, parse_dates=load.parse_dates,
    )
    info = loaded.source
    if pasted:
        info = dataclasses.replace(info, pasted=True)
    src = LoadedSource(id=source_id, name=name, df=loaded.df, info=info)
    SESSION.sources[source_id] = src
    SESSION.write_upload(src, raw)
    return {
        "ok": True,
        "encoding": loaded.encoding,
        "columns": column_options(loaded.df),
        "preview": build_preview(loaded.df, PREVIEW_ROWS, preamble=(loaded.preamble_lines, loaded.preamble_total)),
        "sheets": list(info.sheets) if info.kind == "xlsx" else [],
        "sheet": info.sheet_name if info.kind == "xlsx" else None,
        "warnings": list(loaded.warnings),
    }


@_guard("remove_source")
def remove_source_json(source_id: str) -> dict:
    """データ元を1つ取り除く（作業フォルダに書き出したファイルも消す）。無い id でもエラーにしない。"""
    SESSION.forget_source(str(source_id))
    return {"ok": True}


@_guard("clear_sources")
def clear_sources_json() -> dict:
    """すべてのデータ元を取り除く（「置き換えて読み込む」の前）。"""
    SESSION.forget()
    return {"ok": True}


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
    if not SESSION.sources:
        raise UserError("先にファイルを読み込んでください。")
    plan = plan_plot({sid: src.df for sid, src in SESSION.sources.items()}, settings)
    infos = {sid: src.info for sid, src in SESSION.sources.items()}
    return plan, generate_script(settings, infos, plan)


def _run(settings: Settings | None, code: str | None, *, file_format: str, transparent: bool, dpi: int, svg_text: str = "path"):
    """GUI 同期（code が None）: 設定から生成したスクリプトを、読込済みの df で実行する（読込・保存の行は空にする）。
    編集モード（code が文字列）: そのスクリプトを、アップロードしたファイルのある作業フォルダで実行する。設定は使わない。"""
    if code is None:
        plan, script = _generate(settings)
        try:
            result = run_to_image(
                script.auto_render_text(), file_format=file_format, transparent=transparent, dpi=dpi, svg_text=svg_text,
                injected={src.var: SESSION.sources[src.id].df for src in plan.sources},
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
