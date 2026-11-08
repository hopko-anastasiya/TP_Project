"""SEM-01: побудова семантичного терму з AST.

Golden-файли лежать у tests/golden/terms/<приклад>.txt.
Оновити їх після свідомої зміни нотації:  SIPL_UPDATE_GOLDEN=1 pytest
"""

import json
import os
from pathlib import Path

import pytest

from sipl import ast, parse
from sipl.semantics import (
    AssignTerm,
    Compose,
    Const,
    Deref,
    Group,
    Identity,
    IfTerm,
    Superposition,
    WhileTerm,
    build_term,
    explain_term,
)

from conftest import valid_examples

GOLDEN = Path(__file__).parent / "golden" / "terms"


def term_of(source: str) -> str:
    return build_term(parse(source)).render()


def test_power_term():
    """Терм для x^y, побудований вручну (індекс присвоювання записано як AS^x)."""
    source = "begin R := 1; while Y > 0 do begin R := R * X; Y := Y - 1 end end"
    assert term_of(source) == (
        "AS^R(1) · WH(S2(gr, Y⇒, 0), AS^R(S2(mult, R⇒, X⇒)) · AS^Y(S2(sub, Y⇒, 1)))"
    )


def test_binomial_term():
    """Терм для C(x, y), побудований вручну."""
    source = next(e for e in valid_examples() if e.name == "binomial").source
    expected = (
        "AS^FX(1) · AS^N(X⇒) · WH(S2(gr, N⇒, 0), AS^FX(S2(mult, FX⇒, N⇒)) · AS^N(S2(sub, N⇒, 1))) · "
        "AS^FY(1) · AS^N(Y⇒) · WH(S2(gr, N⇒, 0), AS^FY(S2(mult, FY⇒, N⇒)) · AS^N(S2(sub, N⇒, 1))) · "
        "AS^FXY(1) · AS^N(S2(sub, X⇒, Y⇒)) · WH(S2(gr, N⇒, 0), AS^FXY(S2(mult, FXY⇒, N⇒)) · AS^N(S2(sub, N⇒, 1))) · "
        "AS^DEN(S2(mult, FY⇒, FXY⇒)) · AS^R(0) · "
        "WH(S2(or, S2(gr, FX⇒, DEN⇒), S2(eq, FX⇒, DEN⇒)), AS^FX(S2(sub, FX⇒, DEN⇒)) · AS^R(S2(add, R⇒, 1)))"
    )
    assert term_of(source) == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        ("begin X := 1 end", "AS^X(1)"),
        ("begin X := Y end", "AS^X(Y⇒)"),
        ("begin X := Y + 1 end", "AS^X(S2(add, Y⇒, 1))"),
        ("begin X := Y - 1 end", "AS^X(S2(sub, Y⇒, 1))"),
        ("begin X := Y * 2 end", "AS^X(S2(mult, Y⇒, 2))"),
        ("begin X := (Y + 1) * 2 end", "AS^X(S2(mult, S2(add, Y⇒, 1), 2))"),
        ("begin skip end", "id"),
        ("begin X := 1; skip end", "AS^X(1) · id"),
        ("begin if X = 0 then skip else X := 0 end", "IF(S2(eq, X⇒, 0), id, AS^X(0))"),
        ("begin while X > 0 do X := X - 1 end", "WH(S2(gr, X⇒, 0), AS^X(S2(sub, X⇒, 1)))"),
        ("begin if ¬(X = 0) then skip else skip end", "IF(S1(neg, S2(eq, X⇒, 0)), id, id)"),
        (
            "begin if X > 0 ∨ X = 0 then skip else skip end",
            "IF(S2(or, S2(gr, X⇒, 0), S2(eq, X⇒, 0)), id, id)",
        ),
        ("begin begin X := 1 end end", "AS^X(1)"),
    ],
)
def test_each_rule(source, expected):
    assert term_of(source) == expected


def test_block_in_sequence_keeps_parentheses():
    """NS_Stm_BE: sem_S(begin S end) = (sem_S(S)) — дужки видно всередині композиції."""
    assert term_of("begin A := 1; begin B := 2; C := 3 end end") == "AS^A(1) · (AS^B(2) · AS^C(3))"


def test_sequence_is_flat_without_blocks():
    assert term_of("begin A := 1; B := 2; C := 3 end") == "AS^A(1) · AS^B(2) · AS^C(3)"


def test_term_structure():
    t = build_term(parse("begin while X > 0 do begin X := X - 1 end end"))
    assert t == WhileTerm(
        Superposition("gr", (Deref("X"), Const(0))),
        Group(AssignTerm("X", Superposition("sub", (Deref("X"), Const(1))))),
    )


def test_term_nodes_keep_source_spans():
    source = "begin\n  X := 1;\n  skip\nend"
    t = build_term(parse(source))
    assert isinstance(t, Compose)
    assert source[t.first.span.start:t.first.span.end] == "X := 1"
    assert isinstance(t.second, Identity)
    assert t.second.span.line == 3


def test_ascii_rendering():
    t = build_term(parse("begin X := Y; skip end"))
    assert t.render(ascii=True) == "AS^X(Y=>) . id"


def test_term_to_dict():
    d = build_term(parse("begin if X > 0 then X := 1 else skip end")).to_dict()
    json.dumps(d)
    assert d["type"] == "if"
    assert d["cond"] == {
        **d["cond"],
        "type": "superposition",
        "func": "gr",
        "arity": 2,
    }
    assert d["then"]["type"] == "assign"
    assert d["else"]["type"] == "id"


def test_explanation_steps():
    source = "begin R := 1; while Y > 0 do begin R := R * X; Y := Y - 1 end end"
    term, steps = explain_term(parse(source))
    rules = [s.rule for s in steps]
    assert rules[:4] == ["NS_Prog", "NS_Stm_Seq", "NS_Stm_As", "NS_A_Num"]
    assert "NS_Stm_Wh" in rules and "NS_Stm_BE" in rules and "NS_A_Mult" in rules
    assert steps[2].render() == "[NS_Stm_As] sem_S(R := 1) = AS^R(sem_A(1))"
    wh = next(s for s in steps if s.rule == "NS_Stm_Wh")
    assert wh.lhs == "sem_S(while Y > 0 do begin R := R * X; Y := Y - 1 end)"
    assert wh.rhs == "WH(sem_B(Y > 0), sem_S(begin R := R * X; Y := Y - 1 end))"
    assert steps[0].result.render() == term.render()
    d = steps[-1].to_dict()
    assert d["rule"] == "NS_A_Num" and d["result"] == "1"


def test_every_ast_node_is_explained_once():
    source = next(e for e in valid_examples() if e.name == "gcd").source
    program = parse(source)
    _, steps = explain_term(program)
    assert len(steps) == sum(1 for _ in program.walk())


def test_unknown_node_rejected():
    with pytest.raises(TypeError):
        build_term(ast.Node())


@pytest.mark.parametrize("example", valid_examples(), ids=lambda e: e.name)
def test_golden_terms(example):
    path = GOLDEN / f"{example.name}.txt"
    actual = build_term(parse(example.source)).render() + "\n"
    if os.environ.get("SIPL_UPDATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    assert path.exists(), f"немає golden-файлу {path.name}; запустіть із SIPL_UPDATE_GOLDEN=1"
    assert path.read_text(encoding="utf-8") == actual
