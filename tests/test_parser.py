"""CORE-02: парсер будує власне типізоване AST з SourceSpan та зрозумілі діагностики."""

import json

import pytest

from sipl import SiplSyntaxError, ast, parse, parse_tree, to_source
from sipl.errors import Diagnostic

from conftest import valid_examples

POWER = """begin
  R := 1;
  while Y > 0 do
  begin
    R := R * X;
    Y := Y - 1
  end
end"""


def test_power_program_ast_shape():
    p = parse(POWER)
    assert isinstance(p, ast.Program)
    seq = p.body
    assert isinstance(seq, ast.Seq)
    assert seq.first == ast.Assign("R", ast.Num(1))
    loop = seq.second
    assert isinstance(loop, ast.While)
    assert loop.cond == ast.Compare(">", ast.Var("Y"), ast.Num(0))
    assert isinstance(loop.body, ast.Block)
    body = loop.body.body
    assert body == ast.Seq(
        ast.Assign("R", ast.BinOp("*", ast.Var("R"), ast.Var("X"))),
        ast.Assign("Y", ast.BinOp("-", ast.Var("Y"), ast.Num(1))),
    )


def test_ast_is_not_a_lark_tree():
    from lark import Tree

    for node in parse(POWER).walk():
        assert isinstance(node, ast.Node)
        assert not isinstance(node, Tree)


def test_spans_point_to_source():
    p = parse(POWER)
    assign = p.body.first
    assert assign.span.line == 2 and assign.span.column == 3
    assert POWER[assign.span.start:assign.span.end] == "R := 1"
    loop = p.body.second
    assert POWER[loop.span.start:loop.span.end].startswith("while Y > 0 do")
    assert POWER[loop.span.start:loop.span.end].endswith("end")
    cond = loop.cond
    assert POWER[cond.span.start:cond.span.end] == "Y > 0"


@pytest.mark.parametrize("example", valid_examples(), ids=lambda e: e.name)
def test_every_node_has_span(example):
    for node in parse(example.source).walk():
        assert node.span is not None
        assert 0 <= node.span.start < node.span.end <= len(example.source)


def test_precedence_mul_over_add():
    e = parse("begin X := 1 + 2 * 3 end").body.expr
    assert e == ast.BinOp("+", ast.Num(1), ast.BinOp("*", ast.Num(2), ast.Num(3)))


def test_left_associativity_of_minus():
    e = parse("begin X := 10 - 3 - 2 end").body.expr
    assert e == ast.BinOp("-", ast.BinOp("-", ast.Num(10), ast.Num(3)), ast.Num(2))


def test_parentheses_change_structure():
    e = parse("begin X := 10 - (3 - 2) end").body.expr
    assert e == ast.BinOp("-", ast.Num(10), ast.BinOp("-", ast.Num(3), ast.Num(2)))


def test_not_binds_tighter_than_or():
    c = parse("begin if ¬ X > 0 ∨ Y = 1 then skip else skip end").body.cond
    assert isinstance(c, ast.Or)
    assert isinstance(c.left, ast.Not)


def test_seq_is_lowest_priority_and_right_associative():
    p = parse("begin while X > 0 do X := X - 1; Y := 1; Z := 2 end")
    assert isinstance(p.body, ast.Seq)
    assert isinstance(p.body.first, ast.While)
    assert isinstance(p.body.second, ast.Seq)


def test_if_branches_take_single_statement():
    p = parse("begin if X > 0 then Y := 1 else Y := 2; Z := 3 end")
    assert isinstance(p.body, ast.Seq)
    assert isinstance(p.body.first, ast.If)


def test_negative_number_and_minus():
    assert parse("begin X := -1 end").body.expr == ast.Num(-1)
    assert parse("begin X := Y -1 end").body.expr == ast.BinOp("-", ast.Var("Y"), ast.Num(1))


def test_ascii_and_unicode_operators_give_same_ast():
    a = parse("begin if not (X > 0) or X = 0 then skip else skip end")
    b = parse("begin if ¬(X > 0) ∨ X = 0 then skip else skip end")
    assert a == b


def test_ast_to_dict_is_json_serializable():
    d = parse(POWER).to_dict()
    text = json.dumps(d, ensure_ascii=False)
    assert d["type"] == "Program"
    assert d["body"]["type"] == "Seq"
    assert d["span"]["line"] == 1
    assert "Assign" in text


def test_variables_helper():
    assert ast.variables(parse(POWER)) == ["R", "Y", "X"]


@pytest.mark.parametrize("example", valid_examples(), ids=lambda e: e.name)
def test_printer_round_trip(example):
    """to_source(AST) знову розбирається в те саме AST."""
    p = parse(example.source)
    assert parse(to_source(p)) == p


def test_printer_parenthesizes_when_needed():
    p = parse("begin X := (A + B) * (C - (D - E)); if ¬(X > 0 ∨ X = 0) then skip else skip end")
    text = to_source(p)
    assert "(A + B) * (C - (D - E))" in text
    assert "¬(X > 0 ∨ X = 0)" in text


# ------------------------------------------------------------ дерево виводу

def test_parse_tree_uses_nonterminal_labels():
    t = parse_tree("begin X := 1 end")
    assert (t.label, t.rule) == ("<програма>", "NP1")
    assign = t.children[1]
    assert (assign.label, assign.rule) == ("<оператор>", "NS1")
    assert [c.label for c in assign.children] == ["<змінна>", ":=", "<вираз>"]
    expr = assign.children[2]
    assert expr.rule == "NA1"
    assert expr.children[0].label == "<число>"
    assert expr.children[0].children[0].label == "1"


def test_parse_tree_keeps_parentheses():
    t = parse_tree("begin X := (1) end")
    expr = t.children[1].children[2]
    assert expr.rule == "NA6"
    assert [c.label for c in expr.children] == ["(", "<вираз>", ")"]


def test_parse_tree_to_dict():
    d = parse_tree("begin skip end").to_dict()
    assert d["symbol"] == "<програма>"
    assert d["children"][0] == {
        "kind": "terminal",
        "token": "BEGIN",
        "text": "begin",
        "span": {"line": 1, "column": 1, "end_line": 1, "end_column": 6, "start": 0, "end": 5},
    }


# ------------------------------------------------------------ діагностика

@pytest.mark.parametrize(
    "source, fragment",
    [
        ("begin X := 1; end", "перед 'end' вона не ставиться"),
        ("begin X := 1 Y := 2 end", "пропущено ';'"),
        ("begin X = 1 end", "':='"),
        ("begin end", "порожній блок"),
        ("begin skip := 1 end", "ключове слово"),
        ("begin if X > 0 then A := 1; B := 2 else skip end", "begin … end"),
        ("begin skip end skip", "після завершального 'end'"),
        ("begin X := 1", "неочікуваний кінець програми"),
        ("begin X := 1 $ end", "недопустимий символ '$'"),
    ],
)
def test_error_messages_explain_problem(source, fragment):
    with pytest.raises(SiplSyntaxError) as info:
        parse(source)
    assert fragment in info.value.message


def test_diagnostic_format_has_caret():
    source = "begin\n  X := 1;\nend"
    with pytest.raises(SiplSyntaxError) as info:
        parse(source)
    text = info.value.diagnostic.format(source, "a.sipl")
    lines = text.splitlines()
    assert lines[0].startswith("a.sipl:3:1: помилка:")
    assert lines[1] == "  end"
    assert lines[2] == "  ^^^"


def test_diagnostic_without_span():
    d = Diagnostic("io-error", "файл не знайдено")
    assert d.format() == "<input>: помилка: файл не знайдено"
    assert d.to_dict()["span"] is None
