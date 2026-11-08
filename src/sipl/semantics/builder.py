"""Побудова семантичного терму з AST за правилами заміни.

    sem_P(begin S end)        = sem_S(S)                               NS_Prog
    sem_S(x := a)             = AS^x(sem_A(a))                         NS_Stm_As
    sem_S(S1; S2)             = sem_S(S1) · sem_S(S2)                  NS_Stm_Seq
    sem_S(if b then S1 else S2) = IF(sem_B(b), sem_S(S1), sem_S(S2))   NS_Stm_If
    sem_S(while b do S)       = WH(sem_B(b), sem_S(S))                 NS_Stm_Wh
    sem_S(begin S end)        = (sem_S(S))                             NS_Stm_BE
    sem_S(skip)               = id                                     NS_Stm_skip
    sem_A(n) = n; sem_A(x) = x⇒; sem_A(a1 ∘ a2) = S2(add|sub|mult, …)  NS_A_*
    sem_B(a1 = a2), sem_B(a1 > a2), sem_B(b1 ∨ b2) = S2(eq|gr|or, …)   NS_B_*
    sem_B(¬b) = S1(neg, sem_B(b))                                      NS_B_neg

Правила NS_A_Par та NS_B_Par (дужки) застосовуються неявно: в AST дужок
немає, їхню роль уже виконала структура дерева.

Кожне застосування правила записується як :class:`RuleStep` — це пояснення
побудови: правило, ліва та права частини, результат.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sipl import ast
from sipl.printer import to_source
from sipl.semantics.terms import (
    AssignTerm,
    Compose,
    Const,
    Deref,
    Group,
    Identity,
    IfTerm,
    Superposition,
    Term,
    WhileTerm,
)

_ARITH = {"+": ("add", "NS_A_Add"), "-": ("sub", "NS_A_Sub"), "*": ("mult", "NS_A_Mult")}
_COMPARE = {"=": ("eq", "NS_B_eq"), ">": ("gr", "NS_B_gr")}


@dataclass
class RuleStep:
    """Одне застосування правила заміни: ``lhs = rhs``, а ``result`` — готовий підтерм."""

    rule: str
    lhs: str
    rhs: str
    result: Term
    depth: int

    def render(self, ascii: bool = False) -> str:
        rhs = self.rhs
        if ascii:
            rhs = rhs.replace("⇒", "=>").replace(" · ", " . ")
        return f"[{self.rule}] {self.lhs} = {rhs}"

    def to_dict(self, ascii: bool = False) -> dict[str, Any]:
        span = self.result.span
        return {
            "rule": self.rule,
            "lhs": self.lhs,
            "rhs": self.rhs if not ascii else self.rhs.replace("⇒", "=>").replace(" · ", " . "),
            "result": self.result.render(ascii),
            "depth": self.depth,
            "span": span.to_dict() if span else None,
        }


def _sem_name(node: ast.Node) -> str:
    if isinstance(node, ast.Program):
        return "sem_P"
    if isinstance(node, ast.STM_TYPES):
        return "sem_S"
    if isinstance(node, ast.BEXP_TYPES):
        return "sem_B"
    return "sem_A"


def _call(node: ast.Node) -> str:
    return f"{_sem_name(node)}({to_source(node)})"


class _Builder:
    def __init__(self) -> None:
        self.steps: list[RuleStep] = []

    def build(self, node: ast.Node, depth: int = 0) -> Term:
        index = len(self.steps)
        self.steps.append(None)  # type: ignore[arg-type]  # місце для кроку (прямий порядок)
        rule, rhs, term = self._apply(node, depth)
        self.steps[index] = RuleStep(rule, _call(node), rhs, term, depth)
        return term

    def _apply(self, n: ast.Node, d: int) -> tuple[str, str, Term]:
        span = n.span
        if isinstance(n, ast.Program):
            body = self.build(n.body, d + 1)
            # Терм програми — це терм її тіла, але з позицією всієї програми.
            return "NS_Prog", _call(n.body), body
        if isinstance(n, ast.Assign):
            expr = self.build(n.expr, d + 1)
            return "NS_Stm_As", f"AS^{n.name}({_call(n.expr)})", AssignTerm(n.name, expr, span=span)
        if isinstance(n, ast.Seq):
            first = self.build(n.first, d + 1)
            second = self.build(n.second, d + 1)
            return "NS_Stm_Seq", f"{_call(n.first)} · {_call(n.second)}", Compose(first, second, span=span)
        if isinstance(n, ast.If):
            cond = self.build(n.cond, d + 1)
            then_t = self.build(n.then_branch, d + 1)
            else_t = self.build(n.else_branch, d + 1)
            rhs = f"IF({_call(n.cond)}, {_call(n.then_branch)}, {_call(n.else_branch)})"
            return "NS_Stm_If", rhs, IfTerm(cond, then_t, else_t, span=span)
        if isinstance(n, ast.While):
            cond = self.build(n.cond, d + 1)
            body = self.build(n.body, d + 1)
            return "NS_Stm_Wh", f"WH({_call(n.cond)}, {_call(n.body)})", WhileTerm(cond, body, span=span)
        if isinstance(n, ast.Block):
            inner = self.build(n.body, d + 1)
            return "NS_Stm_BE", f"({_call(n.body)})", Group(inner, span=span)
        if isinstance(n, ast.Skip):
            return "NS_Stm_skip", "id", Identity(span=span)
        if isinstance(n, ast.Num):
            return "NS_A_Num", str(n.value), Const(n.value, span=span)
        if isinstance(n, ast.Var):
            return "NS_A_Var", f"{n.name}⇒", Deref(n.name, span=span)
        if isinstance(n, ast.BinOp):
            func, rule = _ARITH[n.op]
            return self._binary(rule, func, n.left, n.right, d, span)
        if isinstance(n, ast.Compare):
            func, rule = _COMPARE[n.op]
            return self._binary(rule, func, n.left, n.right, d, span)
        if isinstance(n, ast.Or):
            return self._binary("NS_B_or", "or", n.left, n.right, d, span)
        if isinstance(n, ast.Not):
            operand = self.build(n.operand, d + 1)
            return "NS_B_neg", f"S1(neg, {_call(n.operand)})", Superposition("neg", (operand,), span=span)
        raise TypeError(f"невідомий вузол AST: {n!r}")

    def _binary(self, rule, func, left, right, d, span):
        lt = self.build(left, d + 1)
        rt = self.build(right, d + 1)
        rhs = f"S2({func}, {_call(left)}, {_call(right)})"
        return rule, rhs, Superposition(func, (lt, rt), span=span)


def build_term(node: ast.Node) -> Term:
    """sem_P / sem_S / sem_A / sem_B — семантичний терм для вузла AST."""
    return _Builder().build(node)


def explain_term(node: ast.Node) -> tuple[Term, list[RuleStep]]:
    """Терм і послідовність застосованих правил (у прямому порядку обходу)."""
    builder = _Builder()
    term = builder.build(node)
    return term, builder.steps
