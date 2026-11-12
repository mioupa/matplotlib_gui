"""式で新しい列を作るための、式の解釈・評価・コード生成（G6）。

標準ライブラリ・numpy・pandas だけに依存する純粋なモジュール。
`eval` / `exec` / `compile` / `ast` は使わない。字句解析と構文解析は自前で行い、
生成するコードには利用者の入力文字列を写さない（列の変数名・数値の文字列は呼び出し側が決める）。
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MAX_LENGTH = 200
MAX_DEPTH = 30
MAX_WINDOW = 1000
ELEMENTWISE = ("abs", "sqrt", "exp", "log", "log10", "sin", "cos", "tan")
AGGREGATES = ("min", "max", "mean", "median", "std", "first", "last")
SERIES_FUNCS = ("rolling_mean", "diff", "cumsum")
_ALL_FUNCS = ELEMENTWISE + AGGREGATES + SERIES_FUNCS

_DEPTH_MESSAGE = f"入れ子が深すぎます（{MAX_DEPTH} 段まで）"
_NAME_HINT = "列は [N] か大文字の列記号（A, B, …）で、関数は max( のように書いてください"
_CONST_MESSAGE = "計算できない定数があります（0 での割り算など）"

_KIND_ORDER = {"const": 0, "scalar": 1, "series": 2}


class ExprError(Exception):
    """式の誤り。`position` は元の文字列の 1 始まりの文字位置（無ければ None）。"""

    def __init__(self, message: str, position: int | None = None):
        super().__init__(message)
        self.message = message
        self.position = position

    def __str__(self) -> str:
        if self.position is None:
            return self.message
        return f"{self.position}文字目: {self.message}"


# ---- ノード -----------------------------------------------------------------


@dataclass(frozen=True)
class Number:
    value: float
    pos: int
    kind: str = field(default="const", compare=False, repr=False)


@dataclass(frozen=True)
class Column:
    index: int
    pos: int
    kind: str = field(default="series", compare=False, repr=False)


@dataclass(frozen=True)
class Unary:
    op: str
    operand: "Node"
    pos: int
    kind: str = field(default="const", compare=False, repr=False)


@dataclass(frozen=True)
class Binary:
    op: str
    left: "Node"
    right: "Node"
    pos: int
    kind: str = field(default="const", compare=False, repr=False)


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple
    pos: int
    kind: str = field(default="const", compare=False, repr=False)


Node = Number | Column | Unary | Binary | Call


# ---- 字句解析 ---------------------------------------------------------------

_NUMBER = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_COLUMN = re.compile(r"\[[ \t]*([0-9]+)[ \t]*\]")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class _Tok:
    kind: str  # num / col / func / op / ( / ) / , / eof
    text: str
    pos: int
    value: object = None


def _normalize(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif ch == "　":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _show(ch: str) -> str:
    return ch if ch.isprintable() else repr(ch)[1:-1]


def _excel_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _tokenize(s: str) -> list[_Tok]:
    toks: list[_Tok] = []
    n = len(s)
    i = 0
    while i < n:
        c = s[i]
        pos = i + 1
        if c in " \t":
            i += 1
        elif c in "0123456789" or (c == "." and i + 1 < n and s[i + 1] in "0123456789"):
            m = _NUMBER.match(s, i)
            toks.append(_Tok("num", m.group(), pos, float(m.group())))
            i = m.end()
        elif c == "[":
            m = _COLUMN.match(s, i)
            if m is None:
                raise ExprError("列は [0] のように、角括弧の中に番号を書いてください", pos)
            toks.append(_Tok("col", m.group(), pos, int(m.group(1))))
            i = m.end()
        elif c.isascii() and (c.isalpha() or c == "_"):
            m = _IDENT.match(s, i)
            name = m.group()
            j = m.end()
            while j < n and s[j] in " \t":
                j += 1
            paren = j < n and s[j] == "("
            if name.isalpha() and name.isupper():
                if paren:
                    raise ExprError(f"関数名は小文字で書いてください（{name.lower()}）", pos)
                if len(name) > 3:
                    raise ExprError(f"「{name}」は使えません。{_NAME_HINT}", pos)
                toks.append(_Tok("col", name, pos, _excel_index(name)))
            elif name in _ALL_FUNCS:
                if not paren:
                    raise ExprError(
                        f"「{name}」は関数です。{name}( のように、括弧で値を指定してください", pos
                    )
                toks.append(_Tok("func", name, pos, name))
            elif paren:
                raise ExprError(
                    f"「{name}」という関数はありません。使える関数: {', '.join(_ALL_FUNCS)}", pos
                )
            else:
                raise ExprError(f"「{name}」は使えません。{_NAME_HINT}", pos)
            i = m.end()
        elif c == "*":
            if i + 1 < n and s[i + 1] == "*":
                toks.append(_Tok("op", "**", pos))
                i += 2
            else:
                toks.append(_Tok("op", "*", pos))
                i += 1
        elif c == "^":
            toks.append(_Tok("op", "^", pos, "**"))
            i += 1
        elif c in "+-/":
            toks.append(_Tok("op", c, pos))
            i += 1
        elif c in "(),":
            toks.append(_Tok(c, c, pos))
            i += 1
        else:
            raise ExprError(f"「{_show(c)}」は使えません", pos)
    toks.append(_Tok("eof", "", n + 1))
    return toks


# ---- ノードの生成（種類の判定と定数の畳み込み） --------------------------------


def _max_kind(*kinds: str) -> str:
    return max(kinds, key=_KIND_ORDER.__getitem__)


def _fold(compute: Callable[[], object], pos: int) -> Number:
    with np.errstate(all="ignore"):
        v = float(compute())
    if not np.isfinite(v):
        raise ExprError(_CONST_MESSAGE, pos)
    return Number(v, pos)


_BINARY_OPS = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "**": operator.pow,
}


def _make_number(value: float, pos: int) -> Number:
    if not np.isfinite(value):
        raise ExprError(_CONST_MESSAGE, pos)
    return Number(value, pos)


def _make_unary(operand: Node, pos: int) -> Node:
    if isinstance(operand, Number):
        return _fold(lambda: -np.float64(operand.value), pos)
    return Unary("-", operand, pos, operand.kind)


def _make_binary(op: str, left: Node, right: Node, pos: int) -> Node:
    if isinstance(left, Number) and isinstance(right, Number):
        fn = _BINARY_OPS[op]
        return _fold(lambda: fn(np.float64(left.value), np.float64(right.value)), pos)
    return Binary(op, left, right, pos, _max_kind(left.kind, right.kind))


def _make_call(name: str, args: list[Node], pos: int) -> Node:
    if name == "rolling_mean":
        if len(args) != 2:
            raise ExprError("rolling_mean には「式, 窓の幅」の2つを指定してください", pos)
    elif len(args) != 1:
        raise ExprError(f"{name} には値を1つ指定してください", pos)
    first = args[0]
    if name in ELEMENTWISE:
        if isinstance(first, Number):
            fn = getattr(np, name)
            return _fold(lambda: fn(np.float64(first.value)), pos)
        return Call(name, (first,), pos, first.kind)
    if first.kind != "series":
        raise ExprError(f"{name} の中には列を含めてください", pos)
    if name == "rolling_mean":
        w = args[1]
        if not (
            isinstance(w, Number)
            and w.value == int(w.value)
            and 1 <= w.value <= MAX_WINDOW
        ):
            raise ExprError(
                f"rolling_mean の窓の幅は 1〜{MAX_WINDOW} の整数で指定してください", w.pos
            )
    kind = "scalar" if name in AGGREGATES else "series"
    return Call(name, tuple(args), pos, kind)


# ---- 構文解析 ---------------------------------------------------------------


class _Parser:
    def __init__(self, toks: list[_Tok]):
        self.toks = toks
        self.i = 0
        self.depth = 0

    @property
    def cur(self) -> _Tok:
        return self.toks[self.i]

    def advance(self) -> _Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def enter(self, pos: int) -> None:
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ExprError(_DEPTH_MESSAGE, pos)

    def leave(self) -> None:
        self.depth -= 1

    def _is_value_start(self, t: _Tok) -> bool:
        return t.kind in ("num", "col", "func", "(")

    def _unexpected(self, lparen: _Tok | None) -> ExprError:
        """式の途中で、演算子や閉じ括弧でないものが来たときの誤り。"""
        t = self.cur
        if t.kind == "eof" and lparen is not None:
            return ExprError("閉じ括弧「)」が足りません", lparen.pos)
        if self._is_value_start(t):
            return ExprError("値と値の間に演算子（+ - * / など）がありません", t.pos)
        if t.kind == ")":
            return ExprError("「)」に対応する「(」がありません", t.pos)
        if t.kind == ",":
            return ExprError("「,」は関数の引数の区切りにだけ使えます", t.pos)
        return ExprError("式を解釈できません", t.pos)

    def parse_top(self) -> Node:
        node = self.expr()
        if self.cur.kind != "eof":
            raise self._unexpected(None)
        return node

    def expr(self) -> Node:
        left = self.term()
        while self.cur.kind == "op" and self.cur.text in "+-":
            op = self.advance().text
            right = self.term()
            left = _make_binary(op, left, right, left.pos)
        return left

    def term(self) -> Node:
        left = self.unary()
        while self.cur.kind == "op" and self.cur.text in ("*", "/"):
            op = self.advance().text
            right = self.unary()
            left = _make_binary(op, left, right, left.pos)
        return left

    def unary(self) -> Node:
        t = self.cur
        if t.kind == "op" and t.text in "+-":
            self.enter(t.pos)
            self.advance()
            operand = self.unary()
            self.leave()
            return operand if t.text == "+" else _make_unary(operand, t.pos)
        return self.power()

    def power(self) -> Node:
        base = self.atom()
        t = self.cur
        if t.kind == "op" and t.text in ("**", "^"):
            self.enter(t.pos)
            self.advance()
            exponent = self.unary()
            self.leave()
            return _make_binary("**", base, exponent, base.pos)
        return base

    def _missing_operand(self) -> ExprError:
        t = self.cur
        if self.i == 0:
            if t.kind == ")":
                return ExprError("「)」に対応する「(」がありません", t.pos)
            return ExprError(f"「{t.text}」の前に値がありません", t.pos)
        prev = self.toks[self.i - 1]
        return ExprError(f"「{prev.text}」の後に値がありません", prev.pos)

    def atom(self) -> Node:
        t = self.cur
        if t.kind == "num":
            self.advance()
            return _make_number(t.value, t.pos)
        if t.kind == "col":
            self.advance()
            return Column(t.value, t.pos)
        if t.kind == "func":
            self.advance()
            lp = self.advance()  # tokenizer guarantees "("
            self.enter(t.pos)
            args: list[Node] = []
            if self.cur.kind != ")":
                args.append(self.expr())
                while self.cur.kind == ",":
                    self.advance()
                    args.append(self.expr())
                if self.cur.kind != ")":
                    raise self._unexpected(lp)
            self.advance()
            self.leave()
            return _make_call(t.value, args, t.pos)
        if t.kind == "(":
            self.enter(t.pos)
            self.advance()
            inner = self.expr()
            if self.cur.kind != ")":
                raise self._unexpected(t)
            self.advance()
            self.leave()
            return inner
        raise self._missing_operand()


def parse(text: str) -> Node:
    if len(text) > MAX_LENGTH:
        raise ExprError(f"式は{MAX_LENGTH}文字までです")
    s = _normalize(text)
    if not s.strip(" \t"):
        raise ExprError("式を入力してください")
    toks = _tokenize(s)
    try:
        node = _Parser(toks).parse_top()
    except RecursionError:
        raise ExprError(_DEPTH_MESSAGE) from None
    if node.kind == "const":
        raise ExprError("式に列（[N] か A, B, …）を1つ以上含めてください")
    return node


# ---- 木の調査 ---------------------------------------------------------------


def _children(node: Node) -> tuple:
    if isinstance(node, Unary):
        return (node.operand,)
    if isinstance(node, Binary):
        return (node.left, node.right)
    if isinstance(node, Call):
        return node.args
    return ()


def column_refs(node: Node) -> tuple[tuple[int, int], ...]:
    refs: list[tuple[int, int]] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, Column):
            refs.append((n.index, n.pos))
        stack.extend(reversed(_children(n)))
    return tuple(refs)


def column_indices(node: Node) -> tuple[int, ...]:
    return tuple(sorted({i for i, _ in column_refs(node)}))


def is_series(node: Node) -> bool:
    return node.kind == "series"


# ---- 評価 -------------------------------------------------------------------

# pandas の集計は、全部欠損のとき Python の float を返すものがある（mean など）。
# Python の float だと 0 での割り算が ZeroDivisionError になるため、必ず np.float64 にそろえる。
_AGG_METHODS = {
    "min": lambda x: np.float64(x.min()),
    "max": lambda x: np.float64(x.max()),
    "mean": lambda x: np.float64(x.mean()),
    "median": lambda x: np.float64(x.median()),
    "std": lambda x: np.float64(x.std()),
    "first": lambda x: np.float64(x.bfill().iloc[0]),
    "last": lambda x: np.float64(x.ffill().iloc[-1]),
}


def evaluate(
    node: Node, columns: Mapping[int, pd.Series], index: pd.Index
) -> tuple[pd.Series, int]:
    """式を評価する。戻り値は (float の Series, 計算できなかった行数)。"""
    n = len(index)
    bad = np.zeros(n, dtype=bool)

    def mark(result, operands) -> None:
        r = np.asarray(result, dtype=float)
        ok = np.ones((), dtype=bool)
        for o in operands:
            ok = ok & np.isfinite(np.asarray(o, dtype=float))
        b = ~np.isfinite(r) & ok
        if b.ndim == 0:
            if b:
                bad[:] = True
        else:
            bad[...] |= b

    def go(nd: Node):
        if isinstance(nd, Number):
            return float(nd.value)
        if isinstance(nd, Column):
            return columns[nd.index]
        if isinstance(nd, Unary):
            x = go(nd.operand)
            res = -x
            mark(res, [x])
            return res
        if isinstance(nd, Binary):
            a = go(nd.left)
            b = go(nd.right)
            res = _BINARY_OPS[nd.op](a, b)
            mark(res, [a, b])
            return res
        name = nd.name
        x = go(nd.args[0])
        if name in ELEMENTWISE:
            res = getattr(np, name)(x)
            mark(res, [x])
            return res
        if name in AGGREGATES:
            res = _AGG_METHODS[name](x)
            if np.isfinite(np.asarray(x, dtype=float)).any() and not np.isfinite(res):
                bad[:] = True
            return res
        if name == "rolling_mean":
            return x.rolling(int(nd.args[1].value), center=True).mean()
        if name == "diff":
            return x.diff()
        return x.cumsum()

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        val = go(node)
    if isinstance(val, pd.Series):
        arr = val.to_numpy(dtype=float)
    else:
        arr = np.full(n, float(val))
    arr = np.where(np.isinf(arr), np.nan, arr)
    count = int((bad & np.isnan(arr)).sum())
    return pd.Series(arr, index=index, dtype=float), count


# ---- コード生成 -------------------------------------------------------------

_P_ADD, _P_MUL, _P_UNARY, _P_POW, _P_ATOM = 1, 2, 3, 4, 5
_OP_PREC = {"+": _P_ADD, "-": _P_ADD, "*": _P_MUL, "/": _P_MUL, "**": _P_POW}


def to_code(
    node: Node, column_var: Callable[[int], str], number: Callable[[float], str]
) -> str:
    """評価と同じ意味の pandas / numpy の式を文字列にする（入力文字列は写さない）。"""

    def method_base(arg: Node) -> str:
        s, _ = go(arg)
        return s if isinstance(arg, Column) else f"({s})"

    def go(nd: Node) -> tuple[str, int]:
        if isinstance(nd, Number):
            s = number(float(nd.value))
            return s, (_P_UNARY if s.startswith("-") else _P_ATOM)
        if isinstance(nd, Column):
            return column_var(nd.index), _P_ATOM
        if isinstance(nd, Unary):
            s, p = go(nd.operand)
            if p <= _P_UNARY:
                s = f"({s})"
            return f"-{s}", _P_UNARY
        if isinstance(nd, Binary):
            op = nd.op
            prec = _OP_PREC[op]
            ls, lp = go(nd.left)
            rs, rp = go(nd.right)
            if op == "**":
                lparen, rparen = lp <= _P_POW, rp < _P_UNARY
            else:
                lparen, rparen = lp < prec, rp <= prec
            if lparen:
                ls = f"({ls})"
            if rparen:
                rs = f"({rs})"
            return f"{ls} {op} {rs}", prec
        name = nd.name
        if name in ELEMENTWISE:
            s, _ = go(nd.args[0])
            return f"np.{name}({s})", _P_ATOM
        base = method_base(nd.args[0])
        if name in AGGREGATES:
            tail = {
                "first": ".bfill().iloc[0]",
                "last": ".ffill().iloc[-1]",
            }.get(name, f".{name}()")
            return f"np.float64({base}{tail})", _P_ATOM
        if name == "rolling_mean":
            return f"{base}.rolling({int(nd.args[1].value)}, center=True).mean()", _P_ATOM
        return f"{base}.{name}()", _P_ATOM

    return go(node)[0]
