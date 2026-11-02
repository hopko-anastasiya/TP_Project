"""CORE-01: граматика приймає коректні та відхиляє некоректні програми."""

import pytest

from sipl import SiplSyntaxError, parse, parse_tree
from sipl.parser import grammar_text

from conftest import invalid_examples, valid_examples

VALID = valid_examples()
INVALID = invalid_examples()


def test_enough_examples():
    assert len(VALID) >= 10
    assert len(INVALID) >= 10


@pytest.mark.parametrize("example", VALID, ids=lambda e: e.name)
def test_valid_program_is_accepted(example):
    program = parse(example.source)
    assert program.node_type == "Program"


@pytest.mark.parametrize("example", INVALID, ids=lambda e: e.name)
def test_invalid_program_is_rejected_at_expected_position(example):
    with pytest.raises(SiplSyntaxError) as info:
        parse(example.source)
    span = info.value.span
    assert (span.line, span.column) == (example.line, example.column), info.value.message


# Короткі програми для окремих правил БНФ (NS1–NS6, NA1–NA6, NB1–NB5).
POSITIVE = [
    "begin X := 1 end",                                   # NS1, NA1
    "begin X := Y end",                                   # NA2
    "begin X := 1; Y := 2; Z := 3 end",                   # NS2
    "begin if X > 0 then Y := 1 else Y := 2 end",         # NS3, NB2
    "begin while X > 0 do X := X - 1 end",                # NS4, NA4
    "begin begin skip end end",                           # NS5, NS6
    "begin X := (1 + 2) * 3 end",                         # NA3, NA5, NA6
    "begin if X = Y then skip else skip end",             # NB1
    "begin if X > 0 ∨ Y > 0 then skip else skip end",     # NB3
    "begin if ¬ X > 0 then skip else skip end",           # NB4
    "begin if (X > 0) then skip else skip end",           # NB5
    "begin X := -5 end",                                  # від'ємне число
    "begin endless := 1; beginner := endless end",        # ключове слово як префікс імені
]

NEGATIVE = [
    "",
    "begin end",
    "begin X := 1; end",
    "begin X := end",
    "begin if X > 0 then skip end",
    "begin while X > 0 skip end",
    "begin X := 1 X := 2 end",
    "begin 1 := X end",
    "begin X := Y > 1 end",
    "begin if X > Y > Z then skip else skip end",
    "begin X := (1 + 2 end",
    "begin do := 1 end",
]


@pytest.mark.parametrize("source", POSITIVE)
def test_positive_snippets(source):
    parse(source)


@pytest.mark.parametrize("source", NEGATIVE)
def test_negative_snippets(source):
    with pytest.raises(SiplSyntaxError):
        parse(source)


def test_grammar_text_is_available():
    text = grammar_text()
    assert "program: BEGIN stmt END" in text


@pytest.mark.parametrize("example", VALID, ids=lambda e: e.name)
def test_leaf_traversal_reproduces_tokens(example):
    """Перевірка синтаксичної коректності: обхід листків дає текст програми."""
    tree = parse_tree(example.source)
    leaves = list(tree.leaves())
    # Кожен листок — це дослівний фрагмент тексту в позиції, яку він зберігає.
    for leaf in leaves:
        assert example.source[leaf.span.start:leaf.span.end] == leaf.label
    # Листки йдуть зліва направо без перекриттів.
    offsets = [leaf.span.start for leaf in leaves]
    assert offsets == sorted(offsets)
