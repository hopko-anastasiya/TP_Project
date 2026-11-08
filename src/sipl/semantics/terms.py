"""Семантичні терми програмної алгебри SIPL.

    AS^x(fa)          — присвоювання, st∇[x ↦ fa(st)]
    f1 · f2           — послідовне виконання (спочатку f1, потім f2)
    IF(fb, f1, f2)    — умовний оператор
    WH(fb, f)         — цикл
    id                — тотожна функція (skip)
    S2(f, g1, g2)     — суперпозиція бінарної функції (add, sub, mult, eq, gr, or)
    S1(neg, g)        — суперпозиція унарної функції
    x⇒                — розіменування змінної
    n                 — константа

Індекс присвоювання часто пишуть нижнім індексом (``ASR(1)``); тут він
позначається ``AS^R(1)``, щоб не зливатися з іменами змінних (``AS^FX`` і т. п.).
У режимі ``ascii=True`` символи ⇒ та · замінюються на ``=>`` та ``.``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sipl.ast import SourceSpan


@dataclass(frozen=True)
class Term:
    span: SourceSpan | None = field(default=None, compare=False, kw_only=True)

    def render(self, ascii: bool = False) -> str:
        return _render(self, ascii, in_comp=False)

    def __str__(self) -> str:
        return self.render()

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    def _base(self, kind: str) -> dict[str, Any]:
        return {"type": kind, "span": self.span.to_dict() if self.span else None}


@dataclass(frozen=True)
class Const(Term):
    value: int

    def to_dict(self):
        return {**self._base("const"), "value": self.value}


@dataclass(frozen=True)
class Deref(Term):
    """x⇒ — функція розіменування."""

    name: str

    def to_dict(self):
        return {**self._base("deref"), "name": self.name}


@dataclass(frozen=True)
class Superposition(Term):
    """S^n(f, g1, …, gn)."""

    func: str
    args: tuple[Term, ...]

    def to_dict(self):
        return {
            **self._base("superposition"),
            "arity": len(self.args),
            "func": self.func,
            "args": [a.to_dict() for a in self.args],
        }


@dataclass(frozen=True)
class AssignTerm(Term):
    """AS^x(fa)."""

    name: str
    expr: Term

    def to_dict(self):
        return {**self._base("assign"), "name": self.name, "expr": self.expr.to_dict()}


@dataclass(frozen=True)
class Compose(Term):
    """f1 · f2 — послідовне виконання."""

    first: Term
    second: Term

    def to_dict(self):
        return {**self._base("compose"), "first": self.first.to_dict(), "second": self.second.to_dict()}


@dataclass(frozen=True)
class IfTerm(Term):
    cond: Term
    then_term: Term
    else_term: Term

    def to_dict(self):
        return {
            **self._base("if"),
            "cond": self.cond.to_dict(),
            "then": self.then_term.to_dict(),
            "else": self.else_term.to_dict(),
        }


@dataclass(frozen=True)
class WhileTerm(Term):
    cond: Term
    body: Term

    def to_dict(self):
        return {**self._base("while"), "cond": self.cond.to_dict(), "body": self.body.to_dict()}


@dataclass(frozen=True)
class Group(Term):
    """(f) — результат правила NS_Stm_BE для begin S end."""

    inner: Term

    def to_dict(self):
        return {**self._base("group"), "inner": self.inner.to_dict()}


@dataclass(frozen=True)
class Identity(Term):
    def to_dict(self):
        return self._base("id")


def _render(t: Term, ascii: bool, in_comp: bool) -> str:
    dot = " . " if ascii else " · "
    if isinstance(t, Const):
        return str(t.value)
    if isinstance(t, Deref):
        return f"{t.name}{'=>' if ascii else '⇒'}"
    if isinstance(t, Superposition):
        args = ", ".join(_render(a, ascii, False) for a in t.args)
        return f"S{len(t.args)}({t.func}, {args})"
    if isinstance(t, AssignTerm):
        return f"AS^{t.name}({_render(t.expr, ascii, False)})"
    if isinstance(t, Compose):
        return _render(t.first, ascii, True) + dot + _render(t.second, ascii, True)
    if isinstance(t, IfTerm):
        parts = (_render(p, ascii, False) for p in (t.cond, t.then_term, t.else_term))
        return "IF(" + ", ".join(parts) + ")"
    if isinstance(t, WhileTerm):
        return f"WH({_render(t.cond, ascii, False)}, {_render(t.body, ascii, False)})"
    if isinstance(t, Group):
        inner = _render(t.inner, ascii, in_comp)
        # Дужки потрібні лише для композиції всередині іншої композиції.
        return f"({inner})" if in_comp and isinstance(t.inner, Compose) else inner
    if isinstance(t, Identity):
        return "id"
    raise TypeError(f"невідомий терм {t!r}")
