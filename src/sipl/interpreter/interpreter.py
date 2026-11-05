"""Інтерпретатор SIPL.

Стан — відображення імен змінних у цілі числа (st = [X ↦ 5, Y ↦ 2]).
Виконання реалізоване генератором подій: ``Interpreter.events`` видає події
по одній, а ``run``/``trace`` — зручні обгортки над ним.

Семантика відповідає композиціям програмної алгебри:
присвоювання st∇[x ↦ a(st)], послідовне виконання, IF, WH, id (skip).
Читання змінної, якої немає у стані, означає невизначений результат
(UndefinedVariableError). Нескінченні цикли обмежуються лімітом кроків.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Mapping

from sipl import ast
from sipl.errors import SiplError, SiplRuntimeError, StepLimitExceeded, UndefinedVariableError
from sipl.interpreter.events import (
    AfterStatement,
    BeforeStatement,
    ConditionEvaluated,
    Event,
    ProgramFinished,
    ProgramStarted,
    State,
    Trace,
    VariableChanged,
)
from sipl.parser import parse

DEFAULT_MAX_STEPS = 100_000


def eval_aexp(expr: ast.Node, state: Mapping[str, int]) -> int:
    """Значення арифметичного виразу на стані (sem_A(a)(st))."""
    if isinstance(expr, ast.Num):
        return expr.value
    if isinstance(expr, ast.Var):
        if expr.name not in state:
            raise UndefinedVariableError(expr.name, expr.span)
        return state[expr.name]
    if isinstance(expr, ast.BinOp):
        left = eval_aexp(expr.left, state)
        right = eval_aexp(expr.right, state)
        if expr.op == "+":
            return left + right
        if expr.op == "-":
            return left - right
        if expr.op == "*":
            return left * right
    raise SiplRuntimeError(f"невідомий арифметичний вираз {expr.node_type}", expr.span)


def eval_bexp(expr: ast.Node, state: Mapping[str, int]) -> bool:
    """Значення умови на стані (sem_B(b)(st)).

    Як і суперпозиція S2(or, …), диз'юнкція обчислює обидва аргументи:
    якщо будь-який невизначений, невизначена й уся умова.
    """
    if isinstance(expr, ast.Compare):
        left = eval_aexp(expr.left, state)
        right = eval_aexp(expr.right, state)
        return left == right if expr.op == "=" else left > right
    if isinstance(expr, ast.Or):
        left = eval_bexp(expr.left, state)
        right = eval_bexp(expr.right, state)
        return left or right
    if isinstance(expr, ast.Not):
        return not eval_bexp(expr.operand, state)
    raise SiplRuntimeError(f"невідома умова {expr.node_type}", expr.span)


@dataclass
class ExecutionResult:
    state: State
    steps: int


class Interpreter:
    """Покрокове виконання SIPL-програми.

    ``max_steps`` обмежує кількість елементарних дій (присвоювань, skip та
    перевірок умов), щоб нескінченні цикли завершувались помилкою.
    """

    def __init__(self, max_steps: int = DEFAULT_MAX_STEPS):
        if max_steps <= 0:
            raise ValueError("max_steps має бути додатним")
        self.max_steps = max_steps
        self.steps = 0
        self._seq = 0

    # ------------------------------------------------------------ події

    def _emit(self, event: Event) -> Event:
        self._seq += 1
        event.seq = self._seq
        return event

    def _tick(self, node: ast.Node) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise StepLimitExceeded(self.max_steps, node.span)

    def events(self, program: ast.Program, state: Mapping[str, int] | None = None) -> Iterator[Event]:
        """Генератор подій виконання. Останньою подією є ProgramFinished."""
        self.steps = 0
        self._seq = 0
        st: State = dict(state or {})
        yield self._emit(ProgramStarted(dict(st)))
        yield from self._exec(program.body, st)
        yield self._emit(ProgramFinished(dict(st), self.steps))

    def _exec(self, stm: ast.Node, st: State) -> Iterator[Event]:
        if isinstance(stm, ast.Seq):
            yield from self._exec(stm.first, st)
            yield from self._exec(stm.second, st)
            return
        if isinstance(stm, ast.Block):
            yield from self._exec(stm.body, st)
            return

        yield self._emit(BeforeStatement(stm, dict(st)))
        if isinstance(stm, ast.Assign):
            self._tick(stm)
            value = eval_aexp(stm.expr, st)
            old = st.get(stm.name)
            st[stm.name] = value
            yield self._emit(VariableChanged(stm, stm.name, old, value))
        elif isinstance(stm, ast.Skip):
            self._tick(stm)
        elif isinstance(stm, ast.If):
            self._tick(stm.cond)
            cond = eval_bexp(stm.cond, st)
            yield self._emit(ConditionEvaluated(stm, stm.cond, cond))
            yield from self._exec(stm.then_branch if cond else stm.else_branch, st)
        elif isinstance(stm, ast.While):
            while True:
                self._tick(stm.cond)
                cond = eval_bexp(stm.cond, st)
                yield self._emit(ConditionEvaluated(stm, stm.cond, cond))
                if not cond:
                    break
                yield from self._exec(stm.body, st)
        else:
            raise SiplRuntimeError(f"невідомий оператор {stm.node_type}", stm.span)
        yield self._emit(AfterStatement(stm, dict(st)))

    # ------------------------------------------------------------ обгортки

    def run(
        self,
        program: ast.Program,
        state: Mapping[str, int] | None = None,
        listener: Callable[[Event], None] | None = None,
    ) -> ExecutionResult:
        final: State = {}
        for event in self.events(program, state):
            if listener:
                listener(event)
            if isinstance(event, ProgramFinished):
                final = event.state
        return ExecutionResult(final, self.steps)

    def trace(self, program: ast.Program, state: Mapping[str, int] | None = None) -> Trace:
        """Збирає всі події. Помилка виконання не губить уже зібрані події."""
        events: list[Event] = []
        try:
            for event in self.events(program, state):
                events.append(event)
        except SiplError as err:
            return Trace(events, None, self.steps, err.diagnostic)
        finished = events[-1]
        assert isinstance(finished, ProgramFinished)
        return Trace(events, finished.state, self.steps)


def _program(program: ast.Program | str) -> ast.Program:
    return parse(program) if isinstance(program, str) else program


def run(
    program: ast.Program | str,
    state: Mapping[str, int] | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> State:
    """Виконує програму (текст або AST) і повертає кінцевий стан."""
    return Interpreter(max_steps).run(_program(program), state).state


def trace(
    program: ast.Program | str,
    state: Mapping[str, int] | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> Trace:
    """Виконує програму і повертає повний :class:`Trace`."""
    return Interpreter(max_steps).trace(_program(program), state)
