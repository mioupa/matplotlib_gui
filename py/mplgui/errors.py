"""エラー型。UserError はユーザーの入力・操作が原因のエラー（日本語メッセージをそのまま画面に出す）。

それ以外の例外は内部エラーとして扱い、短い日本語メッセージと traceback を表示する。
"""


class UserError(Exception):
    """ユーザーが直せる原因のエラー。message は日本語で、どの項目が悪いかを含める。"""

    def __init__(self, message: str, field: str | None = None, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.detail = detail

    def to_dict(self) -> dict:
        out: dict = {"message": self.message}
        if self.field:
            out["field"] = self.field
        if self.detail:
            out["detail"] = self.detail
        return out
