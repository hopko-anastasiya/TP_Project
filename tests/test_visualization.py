"""VIS-01 (дерево виводу) та VIS-02 (AST і порівняння з деревом виводу)."""

import json
import re
import xml.etree.ElementTree as ET

import pytest

from sipl import parse, parse_tree
from sipl.errors import SiplSyntaxError
from sipl.visualization import (
    from_ast,
    from_parse_tree,
    render_dot,
    render_html,
    render_leaves,
    render_svg,
    render_text,
)

from conftest import valid_examples

POWER = next(e for e in valid_examples() if e.name == "power").source
SMALL = "begin X := (1 + Y) end"


def test_parse_tree_text():
    text = render_text(from_parse_tree(parse_tree(SMALL)))
    assert text.splitlines()[0] == "<програма> NP1"
    assert "├── <оператор> NS1" in text
    assert "<вираз> NA6" in text
    assert "'('" in text and "')'" in text


def test_ast_text_has_no_concrete_syntax():
    text = render_text(from_ast(parse(SMALL)))
    assert text == "Program\n└── Assign X\n    └── BinOp +\n        ├── Num 1\n        └── Var Y"


def test_leaves_numbering():
    assert render_leaves(from_parse_tree(parse_tree(POWER))) == (
        "1 begin 2 R 3 := 4 1 5 ; 6 while 7 Y 8 > 9 0 10 do 11 begin 12 R 13 := 14 R "
        "15 * 16 X 17 ; 18 Y 19 := 20 Y 21 - 22 1 23 end 24 end"
    )


def test_parse_tree_json_links_to_source():
    d = from_parse_tree(parse_tree(SMALL)).to_dict()
    json.dumps(d, ensure_ascii=False)

    def check(node):
        span = node["span"]
        fragment = SMALL[span["start"]:span["end"]]
        if node["kind"] == "terminal":
            assert fragment == node["label"]
        for c in node["children"]:
            check(c)

    check(d)


def test_dot_output():
    dot = render_dot(from_parse_tree(parse_tree(SMALL)), SMALL)
    assert dot.startswith('digraph "sipl" {')
    assert dot.rstrip().endswith("}")
    # у підписі лише нетермінал, правило — у підказці
    assert 'n0 [label="<програма>",' in dot
    assert 'tooltip="1:12-1:19 (NA6): (1 + Y)"' in dot
    assert 'label="begin", fontname="Helvetica-Bold"' in dot
    nodes = len(re.findall(r"^\s+n\d+ \[", dot, re.M))
    edges = len(re.findall(r"->", dot))
    assert edges == nodes - 1


def test_dot_escapes_quotes():
    from sipl.visualization.tree import VisNode

    dot = render_dot(VisNode('a"b', "terminal", None))
    assert 'label="a\\"b"' in dot


@pytest.mark.parametrize("example", valid_examples(), ids=lambda e: e.name)
def test_svg_is_well_formed_and_linked(example):
    tree = from_parse_tree(parse_tree(example.source))
    svg = render_svg(tree, example.source)
    root = ET.fromstring(svg)
    ns = "{http://www.w3.org/2000/svg}"
    groups = root.findall(f"{ns}g")
    assert len(groups) == tree.count()
    for g in groups:
        start, end = int(g.get("data-start")), int(g.get("data-end"))
        assert 0 <= start < end <= len(example.source)
    labels = [g.find(f"{ns}text").text for g in groups]
    assert not any(" NS" in t or " NA" in t or " NB" in t for t in labels)
    assert len(root.findall(f"{ns}line[@marker-end]")) == tree.count() - 1


def test_svg_nodes_do_not_overlap_on_same_level():
    from sipl.visualization.exporters import _layout

    tree = from_ast(parse(POWER))
    pos, _, _ = _layout(tree)
    by_level = {}
    for x, y, w in pos.values():
        by_level.setdefault(y, []).append((x - w / 2, x + w / 2))
    for boxes in by_level.values():
        boxes.sort()
        for (l1, r1), (l2, r2) in zip(boxes, boxes[1:]):
            assert r1 <= l2 + 0.01


def test_ast_is_smaller_than_parse_tree():
    assert from_ast(parse(POWER)).count() < from_parse_tree(parse_tree(POWER)).count()


def test_ast_and_parse_tree_share_spans():
    """Кожен вузол AST має відповідник у дереві виводу з тим самим span (крім знятих дужок)."""
    parse_spans = {(n.span.start, n.span.end) for n in from_parse_tree(parse_tree(POWER)).walk()}
    for n in from_ast(parse(POWER)).walk():
        assert (n.span.start, n.span.end) in parse_spans


def test_ast_roles_for_children():
    vis = from_ast(parse("begin if X > 0 then skip else skip end"))
    if_node = vis.children[0]
    assert [c.detail for c in if_node.children] == ["cond", "then", "else"]


def test_html_page():
    html = render_html(POWER, "power.sipl")
    assert html.startswith("<!doctype html>")
    assert "<title>power.sipl — дерево виводу та AST</title>" in html
    m = re.search(r'<script id="sipl-data" type="application/json">(.*?)</script>', html, re.S)
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert data["source"] == POWER
    assert data["parseTree"]["label"] == "<програма>"
    assert data["ast"]["label"] == "Program"
    assert html.count("<svg") == 2
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")


def test_html_escapes_script_end_in_source():
    html = render_html("begin skip // </script><b>\nend", "x")
    assert "</script><b>" not in html


def test_html_rejects_invalid_program():
    with pytest.raises(SiplSyntaxError):
        render_html("begin end")
