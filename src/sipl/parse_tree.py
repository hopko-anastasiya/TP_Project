"""Дерево синтаксичного виводу (parse tree, конкретний синтаксис).

Вузли підписані нетерміналами БНФ мови SIPL (``<програма>``, ``<оператор>``,
``<вираз>``, ``<умова>``, ``<змінна>``, ``<число>``) та іменами правил
(NP1, NS1–NS6, NA1–NA6, NB1–NB5). Листки — термінальні символи разом із
позицією у тексті. Обхід листків зліва направо відтворює текст програми —
саме так перевіряється синтаксична коректність.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from sipl.ast import SourceSpan

PROGRAM = "<програма>"
STATEMENT = "<оператор>"
EXPRESSION = "<вираз>"
CONDITION = "<умова>"
VARIABLE = "<змінна>"
NUMBER = "<число>"


@dataclass
class ParseNode:
    """Вузол дерева виводу.

    Для нетерміналів ``label`` — нетермінал (``<оператор>``), ``rule`` — ім'я правила.
    Для листків ``label`` — текст термінала, ``rule`` — None, ``token`` — тип лексеми.
    """

    label: str
    span: SourceSpan
    rule: str | None = None
    children: list["ParseNode"] = field(default_factory=list)
    token: str | None = None

    @property
    def is_leaf(self) -> bool:
        return self.token is not None

    def leaves(self) -> Iterator["ParseNode"]:
        if self.is_leaf:
            yield self
            return
        for child in self.children:
            yield from child.leaves()

    def walk(self) -> Iterator["ParseNode"]:
        yield self
        for child in self.children:
            yield from child.walk()

    def leaf_text(self) -> str:
        """Текст, отриманий обходом листків зліва направо."""
        return " ".join(leaf.label for leaf in self.leaves())

    def to_dict(self) -> dict[str, Any]:
        if self.is_leaf:
            return {
                "kind": "terminal",
                "token": self.token,
                "text": self.label,
                "span": self.span.to_dict(),
            }
        return {
            "kind": "nonterminal",
            "symbol": self.label,
            "rule": self.rule,
            "span": self.span.to_dict(),
            "children": [c.to_dict() for c in self.children],
        }
