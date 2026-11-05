"""Подієва модель виконання SIPL (trace).

Події генеруються інтерпретатором по одній (генератором), тому їх можна
обробляти «наживо» — наприклад, у налагоджувачі зупинятися на BeforeStatement
— або зібрати в :class:`Trace` і серіалізувати в JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from sipl import ast
from sipl.errors import Diagnostic
from sipl.printer import to_source

State = dict[str, int]


def _node_info(node: ast.Node) -> dict[str, Any]:
    return {
        "node": node.node_type,
        "text": to_source(node),
        "span": node.span.to_dict() if node.span else None,
    }


@dataclass
class Event:
    kind: ClassVar[str] = "event"
    seq: int = field(default=0, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "kind": self.kind}


@dataclass
class ProgramStarted(Event):
    kind: ClassVar[str] = "program_started"
    state: State

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "state": dict(self.state)}


@dataclass
class BeforeStatement(Event):
    """Оператор (присвоювання, skip, if, while) от-от почне виконуватись."""

    kind: ClassVar[str] = "before_statement"
    node: ast.Node
    state: State

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), **_node_info(self.node), "state": dict(self.state)}


@dataclass
class AfterStatement(Event):
    kind: ClassVar[str] = "after_statement"
    node: ast.Node
    state: State

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), **_node_info(self.node), "state": dict(self.state)}


@dataclass
class VariableChanged(Event):
    """Присвоювання змінило стан: st∇[x ↦ new]."""

    kind: ClassVar[str] = "variable_changed"
    node: ast.Assign
    name: str
    old: int | None
    new: int

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            **_node_info(self.node),
            "name": self.name,
            "old": self.old,
            "new": self.new,
        }


@dataclass
class ConditionEvaluated(Event):
    """Обчислено умову оператора if або while."""

    kind: ClassVar[str] = "condition_evaluated"
    owner: ast.Node
    cond: ast.Node
    value: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            **_node_info(self.cond),
            "construct": "while" if isinstance(self.owner, ast.While) else "if",
            "value": self.value,
        }


@dataclass
class ProgramFinished(Event):
    kind: ClassVar[str] = "program_finished"
    state: State
    steps: int

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "state": dict(self.state), "steps": self.steps}


@dataclass
class Trace:
    """Повний запис виконання: події, кінцевий стан або помилка."""

    events: list[Event]
    state: State | None
    steps: int
    error: Diagnostic | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "state": self.state,
            "steps": self.steps,
            "error": self.error.to_dict() if self.error else None,
        }

    def format(self) -> str:
        """Читабельний текст trace для консолі."""
        lines = []
        for e in self.events:
            d = e.to_dict()
            prefix = f"{e.seq:>4}  "
            if isinstance(e, ProgramStarted):
                lines.append(prefix + f"start      {format_state(e.state)}")
            elif isinstance(e, BeforeStatement):
                lines.append(prefix + f"before     [{_line(e.node)}] {d['text']}")
            elif isinstance(e, AfterStatement):
                lines.append(prefix + f"after      [{_line(e.node)}] {format_state(e.state)}")
            elif isinstance(e, VariableChanged):
                old = "⊥" if e.old is None else e.old
                lines.append(prefix + f"assign     {e.name}: {old} → {e.new}")
            elif isinstance(e, ConditionEvaluated):
                lines.append(prefix + f"condition  {d['construct']} {d['text']} = {str(e.value).lower()}")
            elif isinstance(e, ProgramFinished):
                lines.append(prefix + f"finish     {format_state(e.state)} (кроків: {e.steps})")
        return "\n".join(lines)


def _line(node: ast.Node) -> str:
    return f"{node.span.line}:{node.span.column}" if node.span else "?"


def format_state(state: State) -> str:
    """Стан у вигляді [X ↦ 5, Y ↦ 2]."""
    return "[" + ", ".join(f"{k} ↦ {v}" for k, v in state.items()) + "]"
