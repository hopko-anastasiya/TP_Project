"""CORE-03 та CORE-04: виконання програм, ліміт кроків, події та trace."""

import json

import pytest

from sipl import StepLimitExceeded, UndefinedVariableError, ast, parse
from sipl.errors import SiplRuntimeError
from sipl.interpreter import (
    AfterStatement,
    BeforeStatement,
    ConditionEvaluated,
    Interpreter,
    ProgramFinished,
    ProgramStarted,
    VariableChanged,
    eval_aexp,
    eval_bexp,
    format_state,
    run,
    trace,
)

from conftest import valid_examples

POWER = "begin R := 1; while Y > 0 do begin R := R * X; Y := Y - 1 end end"


@pytest.mark.parametrize("example", valid_examples(), ids=lambda e: e.name)
def test_examples_produce_expected_state(example):
    assert example.expect, f"{example.name}: немає // expect:"
    state = run(example.source, example.input)
    for name, value in example.expect.items():
        assert state.get(name) == value, f"{name}: {state}"


def test_power_example_state():
    """st = [X ↦ 5, Y ↦ 2] → [X ↦ 5, Y ↦ 0, R ↦ 25]."""
    assert run(POWER, {"X": 5, "Y": 2}) == {"X": 5, "Y": 0, "R": 25}


@pytest.mark.parametrize("x, y", [(1, 1), (2, 5), (10, 3)])
def test_power_on_class_of_inputs(x, y):
    assert run(POWER, {"X": x, "Y": y})["R"] == x ** y


@pytest.mark.parametrize("x, y", [(5, 2), (7, 7), (10, 4)])
def test_binomial_on_class_of_inputs(x, y):
    from math import comb

    source = next(e for e in valid_examples() if e.name == "binomial").source
    assert run(source, {"X": x, "Y": y})["R"] == comb(x, y)


def test_input_state_is_not_mutated():
    st = {"X": 2, "Y": 3}
    run(POWER, st)
    assert st == {"X": 2, "Y": 3}


def test_run_accepts_ast():
    assert run(parse("begin X := 2 * 3 end")) == {"X": 6}


def test_skip_is_identity():
    assert run("begin skip end", {"A": 1}) == {"A": 1}


def test_if_both_branches():
    src = "begin if X > 0 then R := 1 else R := 2 end"
    assert run(src, {"X": 5})["R"] == 1
    assert run(src, {"X": 0})["R"] == 2


def test_while_with_false_condition_does_nothing():
    assert run("begin while X > 0 do X := X - 1 end", {"X": -1}) == {"X": -1}


def test_arithmetic_and_conditions():
    st = {"A": 7, "B": -3}
    assert eval_aexp(ast.BinOp("-", ast.Var("A"), ast.Var("B")), st) == 10
    assert eval_aexp(ast.BinOp("*", ast.Var("A"), ast.Var("B")), st) == -21
    assert eval_aexp(ast.BinOp("+", ast.Num(1), ast.Var("B")), st) == -2
    assert eval_bexp(ast.Compare("=", ast.Var("A"), ast.Num(7)), st) is True
    assert eval_bexp(ast.Compare(">", ast.Var("B"), ast.Num(0)), st) is False
    gt = ast.Compare(">", ast.Var("A"), ast.Num(0))
    assert eval_bexp(ast.Or(ast.Not(gt), gt), st) is True
    assert eval_bexp(ast.Not(ast.Or(gt, gt)), st) is False


def test_unknown_nodes_raise_runtime_error():
    with pytest.raises(SiplRuntimeError):
        eval_aexp(ast.Skip(), {})
    with pytest.raises(SiplRuntimeError):
        eval_bexp(ast.Num(1), {})
    with pytest.raises(SiplRuntimeError):
        Interpreter().run(ast.Program(ast.Num(1)))


def test_undefined_variable():
    with pytest.raises(UndefinedVariableError) as info:
        run("begin\n  R := Z + 1\nend")
    assert info.value.name == "Z"
    assert (info.value.span.line, info.value.span.column) == (2, 8)


def test_or_is_strict_like_superposition():
    """S2(or, b1, b2) обчислює обидва аргументи: невизначений b2 → невизначена умова."""
    with pytest.raises(UndefinedVariableError):
        run("begin if 1 = 1 ∨ Z = 1 then skip else skip end")


def test_infinite_loop_hits_step_limit():
    with pytest.raises(StepLimitExceeded) as info:
        run("begin while 1 = 1 do skip end", max_steps=1000)
    assert info.value.limit == 1000


def test_step_limit_counts_elementary_actions():
    interp = Interpreter(max_steps=10_000)
    result = interp.run(parse(POWER), {"X": 2, "Y": 3})
    # 1 присвоювання + 4 перевірки умови + 3 * 2 присвоювання = 11
    assert result.steps == 11


def test_max_steps_must_be_positive():
    with pytest.raises(ValueError):
        Interpreter(max_steps=0)


# ------------------------------------------------------------ події / trace

def test_event_sequence_for_power():
    events = list(Interpreter().events(parse(POWER), {"X": 5, "Y": 1}))
    kinds = [e.kind for e in events]
    assert kinds[0] == "program_started"
    assert kinds[-1] == "program_finished"
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    changes = [(e.name, e.old, e.new) for e in events if isinstance(e, VariableChanged)]
    assert changes == [("R", None, 1), ("R", 1, 5), ("Y", 1, 0)]
    conds = [e.value for e in events if isinstance(e, ConditionEvaluated)]
    assert conds == [True, False]


def test_before_and_after_are_balanced():
    events = list(Interpreter().events(parse(POWER), {"X": 2, "Y": 2}))
    depth = 0
    for e in events:
        if isinstance(e, BeforeStatement):
            depth += 1
        elif isinstance(e, AfterStatement):
            depth -= 1
            assert depth >= 0
    assert depth == 0


def test_events_are_lazy_for_debuggers():
    """Генератор можна зупинити на першому операторі, як на breakpoint."""
    gen = Interpreter().events(parse("begin while 1 = 1 do skip end"))
    assert isinstance(next(gen), ProgramStarted)
    first = next(gen)
    assert isinstance(first, BeforeStatement)
    assert isinstance(first.node, ast.While)
    gen.close()


def test_listener_receives_all_events():
    seen = []
    Interpreter().run(parse(POWER), {"X": 2, "Y": 1}, listener=seen.append)
    assert isinstance(seen[-1], ProgramFinished)


def test_trace_to_json():
    t = trace(POWER, {"X": 5, "Y": 2})
    assert t.ok
    d = t.to_dict()
    json.dumps(d, ensure_ascii=False)
    assert d["state"] == {"X": 5, "Y": 0, "R": 25}
    assert d["error"] is None
    first_stmt = d["events"][1]
    assert first_stmt["kind"] == "before_statement"
    assert first_stmt["text"] == "R := 1"
    assert first_stmt["span"]["column"] == 7
    cond = next(e for e in d["events"] if e["kind"] == "condition_evaluated")
    assert cond["construct"] == "while" and cond["text"] == "Y > 0" and cond["value"] is True
    change = next(e for e in d["events"] if e["kind"] == "variable_changed")
    assert change == {**change, "name": "R", "old": None, "new": 1}


def test_trace_keeps_events_on_error():
    t = trace("begin X := 1; Y := Z end")
    assert not t.ok
    assert t.state is None
    assert t.error.code == "undefined-variable"
    assert any(isinstance(e, VariableChanged) and e.name == "X" for e in t.events)


def test_trace_text_format():
    text = trace("begin if X > 0 then skip else skip end", {"X": 1}).format()
    assert "condition  if X > 0 = true" in text
    assert "finish" in text


def test_format_state_notation():
    assert format_state({"X": 5, "R": 1}) == "[X ↦ 5, R ↦ 1]"
