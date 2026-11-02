"""Перетворення AST назад у текст SIPL (однорядковий канонічний запис).

Дужки розставляються лише там, де без них змінився б розбір.
Використовується в trace (текст оператора) і в поясненнях побудови терму.
"""

from __future__ import annotations

from sipl import ast

_AEXP_PREC = {"+": 1, "-": 1, "*": 2}


def _aexp_prec(e: ast.Node) -> int:
    return _AEXP_PREC[e.op] if isinstance(e, ast.BinOp) else 3


def _aexp(e: ast.Node) -> str:
    if isinstance(e, ast.Num):
        return str(e.value)
    if isinstance(e, ast.Var):
        return e.name
    if isinstance(e, ast.BinOp):
        prec = _AEXP_PREC[e.op]
        left = _aexp(e.left)
        if _aexp_prec(e.left) < prec:
            left = f"({left})"
        right = _aexp(e.right)
        if _aexp_prec(e.right) <= prec:  # операції лівоасоціативні
            right = f"({right})"
        return f"{left} {e.op} {right}"
    raise TypeError(f"не арифметичний вираз: {e!r}")


def _bexp(b: ast.Node) -> str:
    if isinstance(b, ast.Compare):
        return f"{_aexp(b.left)} {b.op} {_aexp(b.right)}"
    if isinstance(b, ast.Not):
        inner = _bexp(b.operand)
        return f"¬{inner}" if isinstance(b.operand, ast.Not) else f"¬({inner})"
    if isinstance(b, ast.Or):
        right = _bexp(b.right)
        if isinstance(b.right, ast.Or):
            right = f"({right})"
        return f"{_bexp(b.left)} ∨ {right}"
    raise TypeError(f"не умова: {b!r}")


def _stm(s: ast.Node) -> str:
    if isinstance(s, ast.Assign):
        return f"{s.name} := {_aexp(s.expr)}"
    if isinstance(s, ast.Seq):
        return f"{_stm(s.first)}; {_stm(s.second)}"
    if isinstance(s, ast.If):
        return f"if {_bexp(s.cond)} then {_stm(s.then_branch)} else {_stm(s.else_branch)}"
    if isinstance(s, ast.While):
        return f"while {_bexp(s.cond)} do {_stm(s.body)}"
    if isinstance(s, ast.Block):
        return f"begin {_stm(s.body)} end"
    if isinstance(s, ast.Skip):
        return "skip"
    raise TypeError(f"не оператор: {s!r}")


def to_source(node: ast.Node) -> str:
    """Текст SIPL для будь-якого вузла AST."""
    if isinstance(node, ast.Program):
        return f"begin {_stm(node.body)} end"
    if isinstance(node, ast.STM_TYPES):
        return _stm(node)
    if isinstance(node, ast.BEXP_TYPES):
        return _bexp(node)
    return _aexp(node)
