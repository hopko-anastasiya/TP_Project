"""Спільна модель дерева для візуалізації дерева виводу та AST.

Обидва дерева перетворюються на :class:`VisNode`, тож експортери
(текст, DOT, SVG, HTML) не залежать від того, яке саме дерево малюють.
Кожен вузол несе ``span`` — через нього вузли пов'язані з фрагментами
вихідного тексту та між собою.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from sipl import ast
from sipl.ast import SourceSpan
from sipl.parse_tree import ParseNode


@dataclass
class VisNode:
    label: str
    kind: str  # "nonterminal" | "terminal" | "stm" | "aexp" | "bexp" | "program"
    span: SourceSpan | None
    children: list["VisNode"] = field(default_factory=list)
    detail: str | None = None  # напр. ім'я правила БНФ

    def walk(self) -> Iterator["VisNode"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def count(self) -> int:
        return sum(1 for _ in self.walk())

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "kind": self.kind,
            "detail": self.detail,
            "span": self.span.to_dict() if self.span else None,
            "children": [c.to_dict() for c in self.children],
        }


def from_parse_tree(node: ParseNode) -> VisNode:
    if node.is_leaf:
        return VisNode(node.label, "terminal", node.span, detail=node.token)
    return VisNode(
        node.label,
        "nonterminal",
        node.span,
        [from_parse_tree(c) for c in node.children],
        detail=node.rule,
    )


def _ast_label(n: ast.Node) -> str:
    if isinstance(n, ast.Num):
        return f"Num {n.value}"
    if isinstance(n, ast.Var):
        return f"Var {n.name}"
    if isinstance(n, ast.BinOp):
        return f"BinOp {n.op}"
    if isinstance(n, ast.Compare):
        return f"Compare {n.op}"
    if isinstance(n, ast.Assign):
        return f"Assign {n.name}"
    return n.node_type


def _ast_kind(n: ast.Node) -> str:
    if isinstance(n, ast.Program):
        return "program"
    if isinstance(n, ast.STM_TYPES):
        return "stm"
    if isinstance(n, ast.BEXP_TYPES):
        return "bexp"
    return "aexp"


_FIELD_ROLES = {
    "If": ("cond", "then", "else"),
    "While": ("cond", "body"),
    "Seq": ("first", "second"),
}


def from_ast(node: ast.Node) -> VisNode:
    children = [from_ast(c) for c in node.children()]
    roles = _FIELD_ROLES.get(node.node_type)
    if roles:
        for child, role in zip(children, roles):
            child.detail = role
    return VisNode(_ast_label(node), _ast_kind(node), node.span, children)
