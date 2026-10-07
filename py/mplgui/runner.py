"""Figure を画像（data URI）にする。保存ファイル名の組み立ても行う（DOM / js には依存しない）。"""
import base64
import io


def figure_to_data_uri(fig, file_format: str, transparent: bool = False) -> tuple[str, str]:
    fmt = (file_format or "").lower()
    if fmt == "png":
        save_format = "png"
        mime = "image/png"
        ext = "png"
    elif fmt == "jpg":
        save_format = "jpeg"
        mime = "image/jpeg"
        ext = "jpg"
    elif fmt == "svg":
        save_format = "svg"
        mime = "image/svg+xml"
        ext = "svg"
    elif fmt == "pdf":
        save_format = "pdf"
        mime = "application/pdf"
        ext = "pdf"
    else:
        raise ValueError("保存形式が不正です。")

    if transparent and fmt not in {"png", "svg"}:
        raise ValueError("背景透過を有効にした場合、保存形式はpngまたはsvgを選択してください。")

    buffer = io.BytesIO()
    save_kwargs = {}
    if save_format in {"png", "jpeg"}:
        save_kwargs["dpi"] = 120
    if save_format == "jpeg":
        save_kwargs["facecolor"] = "white"
    if transparent:
        save_kwargs["transparent"] = True

    fig.savefig(buffer, format=save_format, **save_kwargs)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:{mime};base64,{encoded}", ext


def build_filename(raw_filename: str, ext: str) -> str:
    """保存ファイル名を作る。空欄時は plot.<ext>。入力中の拡張子は取り除いて ext を付ける。"""
    raw_filename = (raw_filename or "").strip()
    if raw_filename:
        filename_base = raw_filename.rstrip(".")
        if "." in filename_base:
            filename_base = filename_base.rsplit(".", 1)[0]
        filename_base = filename_base.strip() or "plot"
        return f"{filename_base}.{ext}"
    return f"plot.{ext}"
