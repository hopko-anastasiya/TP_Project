"""Парсер SIPL: текст → дерево виводу → типізоване AST.

Lark використовується лише як генератор LALR-аналізатора. Сире дерево Lark
одразу перетворюється на власні структури: :class:`sipl.parse_tree.ParseNode`
(конкретний синтаксис) та вузли :mod:`sipl.ast` (абстрактний синтаксис).
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from lark import Lark, Token, Tree
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, UnexpectedToken

from sipl import ast
from sipl.ast import SourceSpan
from sipl.errors import SiplSyntaxError
from sipl.parse_tree import CONDITION, EXPRESSION, NUMBER, PROGRAM, STATEMENT, VARIABLE, ParseNode

# Lark-правило -> (нетермінал БНФ, ім'я правила)
_RULES: dict[str, tuple[str, str]] = {
    "program": (PROGRAM, "NP1"),
    "assign": (STATEMENT, "NS1"),
    "seq_stmt": (STATEMENT, "NS2"),
    "if_stmt": (STATEMENT, "NS3"),
    "while_stmt": (STATEMENT, "NS4"),
    "block": (STATEMENT, "NS5"),
    "skip_stmt": (STATEMENT, "NS6"),
    "num": (EXPRESSION, "NA1"),
    "var": (EXPRESSION, "NA2"),
    "add": (EXPRESSION, "NA3"),
    "sub": (EXPRESSION, "NA4"),
    "mul": (EXPRESSION, "NA5"),
    "paren": (EXPRESSION, "NA6"),
    "eq": (CONDITION, "NB1"),
    "gt": (CONDITION, "NB2"),
    "or_": (CONDITION, "NB3"),
    "not_": (CONDITION, "NB4"),
    "bparen": (CONDITION, "NB5"),
}

# Зрозумілі назви лексем для повідомлень про помилки.
_TOKEN_NAMES: dict[str, str] = {
    "BEGIN": "'begin'",
    "END": "'end'",
    "IF": "'if'",
    "THEN": "'then'",
    "ELSE": "'else'",
    "WHILE": "'while'",
    "DO": "'do'",
    "SKIP": "'skip'",
    "OR": "'∨'",
    "NOT": "'¬'",
    "ASSIGN": "':='",
    "SEMI": "';'",
    "PLUS": "'+'",
    "MINUS": "'-'",
    "STAR": "'*'",
    "EQ": "'='",
    "GT": "'>'",
    "LPAR": "'('",
    "RPAR": "')'",
    "NUMBER": "число",
    "VAR": "змінна",
    "$END": "кінець тексту",
}

_STATEMENT_START = {"VAR", "IF", "WHILE", "BEGIN", "SKIP"}
_KEYWORDS = {"BEGIN", "END", "IF", "THEN", "ELSE", "WHILE", "DO", "SKIP", "OR", "NOT"}
_KEYWORD_WORDS = {k.lower() for k in _KEYWORDS}


@lru_cache(maxsize=1)
def _lark() -> Lark:
    grammar = resources.files("sipl").joinpath("grammar/sipl.lark").read_text(encoding="utf-8")
    return Lark(grammar, parser="lalr", lexer="contextual", start="start")


def grammar_text() -> str:
    return resources.files("sipl").joinpath("grammar/sipl.lark").read_text(encoding="utf-8")


# ---------------------------------------------------------------- спани

def _offset_to_span(source: str, offset: int, length: int = 1) -> SourceSpan:
    line = source.count("\n", 0, offset) + 1
    line_start = source.rfind("\n", 0, offset) + 1
    column = offset - line_start + 1
    return SourceSpan(line, column, line, column + length, offset, offset + length)


def _token_span(tok: Token) -> SourceSpan:
    return SourceSpan(tok.line, tok.column, tok.end_line, tok.end_column, tok.start_pos, tok.end_pos)


# ---------------------------------------------------------------- помилки

def _accepted(err: UnexpectedInput) -> set[str]:
    """Точна множина лексем, які парсер прийняв би в цьому місці."""
    interactive = getattr(err, "interactive_parser", None)
    if interactive is not None:
        try:
            return set(interactive.accepts())
        except Exception:  # pragma: no cover - захист від змін API Lark
            pass
    return set(getattr(err, "expected", None) or [])


def _describe(names) -> str:
    pretty = sorted({_TOKEN_NAMES.get(n, n) for n in names if not n.startswith("__")})
    return ", ".join(pretty)


def _convert_error(err: UnexpectedInput, source: str) -> SiplSyntaxError:
    if isinstance(err, UnexpectedCharacters):
        ch = source[err.pos_in_stream] if err.pos_in_stream < len(source) else ""
        return SiplSyntaxError(f"недопустимий символ '{ch}'", _offset_to_span(source, err.pos_in_stream))

    expected = _accepted(err)
    if isinstance(err, UnexpectedEOF) or (
        isinstance(err, UnexpectedToken) and err.token.type == "$END"
    ):
        span = _offset_to_span(source, len(source.rstrip()))
        msg = "неочікуваний кінець програми"
        if expected:
            msg += f"; очікувалось: {_describe(expected)}"
        return SiplSyntaxError(msg, span)

    if isinstance(err, UnexpectedToken):
        tok = err.token
        span = _token_span(tok)
        found = _TOKEN_NAMES.get(tok.type, tok.type)
        if tok.type in ("VAR", "NUMBER"):
            found = f"{found} '{tok}'"
        before = source[: tok.start_pos].rstrip()
        words = before.split()
        prev_word = words[-1] if words else ""
        msg = f"неочікувана лексема {found}; очікувалось: {_describe(expected)}"
        if expected == {"$END"}:
            msg = f"зайвий текст після завершального 'end' програми: {found}"
        elif tok.type == "END" and before.endswith(";"):
            msg += " (у SIPL ';' розділяє оператори, тому перед 'end' вона не ставиться)"
        elif tok.type == "END" and before.endswith("begin"):
            msg += " (порожній блок: між begin і end має бути оператор, наприклад skip)"
        elif tok.type == "SEMI" and expected == {"ELSE"}:
            msg += " (гілка then містить один оператор; кілька операторів беруть у begin … end)"
        elif tok.type == "ASSIGN" and prev_word in _KEYWORD_WORDS:
            msg += f" ('{prev_word}' — ключове слово, його не можна використати як ім'я змінної)"
        elif tok.type in _KEYWORDS and "VAR" in expected:
            msg += f" ({found} — ключове слово, його не можна використати як ім'я змінної)"
        elif tok.type in _STATEMENT_START and "SEMI" in expected:
            msg += " (можливо, пропущено ';' між операторами)"
        elif tok.type == "EQ" and "ASSIGN" in expected:
            msg += " (присвоювання записується як ':=')"
        return SiplSyntaxError(msg, span)

    return SiplSyntaxError(str(err))  # pragma: no cover - запасний варіант


# ---------------------------------------------------------------- Lark → ParseNode

def _leaf(tok: Token) -> ParseNode:
    return ParseNode(label=str(tok), span=_token_span(tok), token=tok.type)


def _wrap(symbol: str, rule: str, tok: Token) -> ParseNode:
    leaf = _leaf(tok)
    return ParseNode(label=symbol, rule=rule, span=leaf.span, children=[leaf])


def _to_parse_node(tree: Tree) -> ParseNode:
    symbol, rule = _RULES[tree.data]
    children: list[ParseNode] = []
    for child in tree.children:
        if isinstance(child, Tree):
            children.append(_to_parse_node(child))
        elif child.type == "VAR":
            children.append(_wrap(VARIABLE, "NV", child))
        elif child.type == "NUMBER":
            children.append(_wrap(NUMBER, "NN", child))
        else:
            children.append(_leaf(child))
    span = SourceSpan.merge(children[0].span, children[-1].span)
    return ParseNode(label=symbol, rule=rule, span=span, children=children)


def parse_tree(source: str) -> ParseNode:
    """Будує дерево синтаксичного виводу або кидає :class:`SiplSyntaxError`."""
    try:
        tree = _lark().parse(source)
    except UnexpectedInput as err:
        raise _convert_error(err, source) from None
    return _to_parse_node(tree.children[0])


# ---------------------------------------------------------------- ParseNode → AST

_BINOPS = {"NA3": "+", "NA4": "-", "NA5": "*"}
_COMPARE = {"NB1": "=", "NB2": ">"}


def _leaf_value(node: ParseNode) -> str:
    """Текст єдиного листка у вузлі <змінна>/<число>."""
    return node.children[0].label


def to_ast(node: ParseNode) -> ast.Node:
    r, c, span = node.rule, node.children, node.span
    if r == "NP1":
        return ast.Program(to_ast(c[1]), span=span)
    if r == "NS1":
        return ast.Assign(_leaf_value(c[0]), to_ast(c[2]), span=span)
    if r == "NS2":
        return ast.Seq(to_ast(c[0]), to_ast(c[2]), span=span)
    if r == "NS3":
        return ast.If(to_ast(c[1]), to_ast(c[3]), to_ast(c[5]), span=span)
    if r == "NS4":
        return ast.While(to_ast(c[1]), to_ast(c[3]), span=span)
    if r == "NS5":
        return ast.Block(to_ast(c[1]), span=span)
    if r == "NS6":
        return ast.Skip(span=span)
    if r == "NA1":
        return ast.Num(int(_leaf_value(c[0])), span=span)
    if r == "NA2":
        return ast.Var(_leaf_value(c[0]), span=span)
    if r in _BINOPS:
        return ast.BinOp(_BINOPS[r], to_ast(c[0]), to_ast(c[2]), span=span)
    if r in ("NA6", "NB5"):
        return to_ast(c[1])
    if r in _COMPARE:
        return ast.Compare(_COMPARE[r], to_ast(c[0]), to_ast(c[2]), span=span)
    if r == "NB3":
        return ast.Or(to_ast(c[0]), to_ast(c[2]), span=span)
    if r == "NB4":
        return ast.Not(to_ast(c[1]), span=span)
    raise ValueError(f"невідоме правило {r}")  # pragma: no cover


def parse(source: str) -> ast.Program:
    """Розбирає текст SIPL-програми і повертає :class:`sipl.ast.Program`."""
    result = to_ast(parse_tree(source))
    assert isinstance(result, ast.Program)
    return result
