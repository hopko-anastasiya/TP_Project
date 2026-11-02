"""Типізоване абстрактне синтаксичне дерево (AST) мови SIPL.

Кожен вузол зберігає ``span`` — позицію у вихідному тексті (SourceSpan).
Вузли незмінні (frozen dataclasses) і серіалізуються в JSON через ``to_dict``.
Дужки в AST не зберігаються: це конкретний синтаксис (його видно в дереві
синтаксичного виводу, див. :mod:`sipl.parse_tree`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Iterator, Union


@dataclass(frozen=True)
class SourceSpan:
    """Діапазон у вихідному тексті.

    Рядки та колонки нумеруються з 1; ``end_column`` і ``end`` — виключні межі.
    ``start``/``end`` — зміщення в символах від початку тексту.
    """

    line: int
    column: int
    end_line: int
    end_column: int
    start: int
    end: int

    def to_dict(self) -> dict[str, int]:
        return {
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "start": self.start,
            "end": self.end,
        }

    def __str__(self) -> str:
        return f"{self.line}:{self.column}-{self.end_line}:{self.end_column}"

    @staticmethod
    def merge(first: "SourceSpan", last: "SourceSpan") -> "SourceSpan":
        return SourceSpan(first.line, first.column, last.end_line, last.end_column, first.start, last.end)


@dataclass(frozen=True)
class Node:
    """Базовий клас вузлів AST."""

    span: SourceSpan | None = field(default=None, compare=False, kw_only=True)

    @property
    def node_type(self) -> str:
        return type(self).__name__

    def children(self) -> Iterator["Node"]:
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, Node):
                yield value

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.node_type}
        for f in fields(self):
            if f.name == "span":
                continue
            value = getattr(self, f.name)
            result[f.name] = value.to_dict() if isinstance(value, Node) else value
        result["span"] = self.span.to_dict() if self.span else None
        return result

    def walk(self) -> Iterator["Node"]:
        """Обхід дерева в прямому порядку."""
        yield self
        for child in self.children():
            yield from child.walk()


# ---------- арифметичні вирази (Aexp) ----------

@dataclass(frozen=True)
class Num(Node):
    value: int


@dataclass(frozen=True)
class Var(Node):
    name: str


@dataclass(frozen=True)
class BinOp(Node):
    """a1 + a2, a1 - a2, a1 * a2."""

    op: str  # "+", "-", "*"
    left: "Aexp"
    right: "Aexp"


Aexp = Union[Num, Var, BinOp]


# ---------- умови (Bexp) ----------

@dataclass(frozen=True)
class Compare(Node):
    """a1 = a2, a1 > a2."""

    op: str  # "=", ">"
    left: Aexp
    right: Aexp


@dataclass(frozen=True)
class Or(Node):
    left: "Bexp"
    right: "Bexp"


@dataclass(frozen=True)
class Not(Node):
    operand: "Bexp"


Bexp = Union[Compare, Or, Not]


# ---------- оператори (Stm) ----------

@dataclass(frozen=True)
class Assign(Node):
    name: str
    expr: Aexp


@dataclass(frozen=True)
class Seq(Node):
    first: "Stm"
    second: "Stm"


@dataclass(frozen=True)
class If(Node):
    cond: Bexp
    then_branch: "Stm"
    else_branch: "Stm"


@dataclass(frozen=True)
class While(Node):
    cond: Bexp
    body: "Stm"


@dataclass(frozen=True)
class Block(Node):
    """begin S end всередині програми (NS5)."""

    body: "Stm"


@dataclass(frozen=True)
class Skip(Node):
    pass


Stm = Union[Assign, Seq, If, While, Block, Skip]


@dataclass(frozen=True)
class Program(Node):
    """begin S end — уся програма (NP1)."""

    body: Stm


AEXP_TYPES = (Num, Var, BinOp)
BEXP_TYPES = (Compare, Or, Not)
STM_TYPES = (Assign, Seq, If, While, Block, Skip)


def variables(node: Node) -> list[str]:
    """Усі імена змінних, що зустрічаються в дереві (у порядку першої появи)."""
    seen: dict[str, None] = {}
    for n in node.walk():
        if isinstance(n, Var):
            seen.setdefault(n.name)
        elif isinstance(n, Assign):
            seen.setdefault(n.name)
    return list(seen)
