"""Експорт дерев: текст, Graphviz DOT, SVG (власне розміщення, без залежностей)."""

from __future__ import annotations

from html import escape

from sipl.visualization.tree import VisNode


def _fragment(node: VisNode, source: str | None, limit: int = 60) -> str:
    if source is None or node.span is None:
        return ""
    text = " ".join(source[node.span.start:node.span.end].split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _picture_label(node: VisNode) -> str:
    """Підпис для DOT/SVG: лише нетермінал, без номера правила."""
    if node.kind == "nonterminal":
        return node.label
    return _full_label(node)


def _tooltip(node: VisNode, source: str | None) -> str:
    if node.span is None:
        return ""
    rule = f" ({node.detail})" if node.kind == "nonterminal" and node.detail else ""
    return f"{node.span}{rule}: {_fragment(node, source)}"


def _full_label(node: VisNode) -> str:
    if node.kind == "terminal":
        return node.label
    if node.kind == "nonterminal" and node.detail:
        return f"{node.label} {node.detail}"
    if node.detail:
        return f"{node.detail}: {node.label}"
    return node.label


# ------------------------------------------------------------------ текст

def render_text(root: VisNode, show_spans: bool = False) -> str:
    """Дерево псевдографікою; ``show_spans`` додає позиції рядок:колонка."""
    lines: list[str] = []

    def label(n: VisNode) -> str:
        text = f"'{n.label}'" if n.kind == "terminal" else _full_label(n)
        if show_spans and n.span:
            text += f"  [{n.span}]"
        return text

    def visit(n: VisNode, prefix: str, last: bool, is_root: bool) -> None:
        if is_root:
            lines.append(label(n))
            child_prefix = ""
        else:
            lines.append(prefix + ("└── " if last else "├── ") + label(n))
            child_prefix = prefix + ("    " if last else "│   ")
        for i, c in enumerate(n.children):
            visit(c, child_prefix, i == len(n.children) - 1, False)

    visit(root, "", True, True)
    return "\n".join(lines)


def render_leaves(root: VisNode) -> str:
    """Нумерований обхід листків зліва направо."""
    leaves = [n for n in root.walk() if not n.children]
    return " ".join(f"{i} {leaf.label}" for i, leaf in enumerate(leaves, 1))


# ------------------------------------------------------------------ DOT

def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def render_dot(root: VisNode, source: str | None = None, name: str = "sipl") -> str:
    """Graphviz DOT. Підказка (tooltip) вузла містить позицію та фрагмент коду."""
    lines = [
        f'digraph "{_dot_escape(name)}" {{',
        '  graph [ordering=out, fontname="Helvetica", nodesep=0.25, ranksep=0.35];',
        '  node [shape=plaintext, fontname="Helvetica", fontsize=11];',
        "  edge [arrowhead=normal, arrowsize=0.7];",
    ]
    ids: dict[int, str] = {}
    for i, n in enumerate(root.walk()):
        ids[id(n)] = f"n{i}"
        font = ', fontname="Helvetica-Bold"' if n.kind == "terminal" else ""
        lines.append(
            f'  n{i} [label="{_dot_escape(_picture_label(n))}"{font}, '
            f'tooltip="{_dot_escape(_tooltip(n, source))}"];'
        )
    for n in root.walk():
        for c in n.children:
            lines.append(f"  {ids[id(n)]} -> {ids[id(c)]};")
    lines.append("}")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ SVG

_CHAR_W = 7.4
_NODE_H = 24
_LEVEL_H = 60
_GAP = 12
_PAD = 16


def _layout(root: VisNode) -> tuple[dict[int, tuple[float, float, float]], float, float]:
    """Позиції вузлів: (центр x, y, ширина) — кожне піддерево отримує свою смугу."""
    widths: dict[int, float] = {}

    def node_w(n: VisNode) -> float:
        return max(20.0, len(_picture_label(n)) * _CHAR_W + 10)

    def measure(n: VisNode) -> float:
        own = node_w(n)
        if not n.children:
            widths[id(n)] = own
        else:
            kids = sum(measure(c) for c in n.children) + _GAP * (len(n.children) - 1)
            widths[id(n)] = max(own, kids)
        return widths[id(n)]

    total = measure(root)
    pos: dict[int, tuple[float, float, float]] = {}
    depth_max = 0

    def place(n: VisNode, left: float, depth: int) -> None:
        nonlocal depth_max
        depth_max = max(depth_max, depth)
        w = widths[id(n)]
        if n.children:
            kids = sum(widths[id(c)] for c in n.children) + _GAP * (len(n.children) - 1)
            x = left + (w - kids) / 2
            for c in n.children:
                place(c, x, depth + 1)
                x += widths[id(c)] + _GAP
            first, last = pos[id(n.children[0])][0], pos[id(n.children[-1])][0]
            cx = (first + last) / 2
        else:
            cx = left + w / 2
        pos[id(n)] = (cx, _PAD + depth * _LEVEL_H, node_w(n))

    place(root, _PAD, 0)
    return pos, total + 2 * _PAD, _PAD * 2 + depth_max * _LEVEL_H + _NODE_H


def render_svg(root: VisNode, source: str | None = None, css_class: str = "sipl-tree") -> str:
    """Самодостатній SVG: нетермінали, жирні термінали, стрілки від батька до дітей.

    Вузли мають data-start/data-end — зміщення у вихідному тексті; підказка показує позицію,
    правило БНФ і фрагмент коду.
    """
    pos, width, height = _layout(root)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="{css_class}" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" font-family="Helvetica, Arial, sans-serif" '
        f'font-size="12">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#1d2433"/></marker></defs>',
        "<style>"
        ".edge{stroke:#1d2433;stroke-width:1.2}"
        ".node rect{fill:transparent;stroke:none}"
        ".node text{fill:#1d2433;text-anchor:middle;dominant-baseline:central}"
        ".node.terminal text{font-weight:bold}"
        ".node.selected rect{stroke:#d9480f;stroke-width:2}"
        "</style>",
    ]
    gap = 4
    for n in root.walk():
        x1, y1, _ = pos[id(n)]
        for c in n.children:
            x2, y2, _ = pos[id(c)]
            out.append(
                f'<line class="edge" x1="{x1:.1f}" y1="{y1 + _NODE_H + gap:.1f}" '
                f'x2="{x2:.1f}" y2="{y2 - gap:.1f}" marker-end="url(#arrow)"/>'
            )
    for n in root.walk():
        x, y, w = pos[id(n)]
        span_attr = f' data-start="{n.span.start}" data-end="{n.span.end}"' if n.span else ""
        out.append(
            f'<g class="node {n.kind}"{span_attr}><title>{escape(_tooltip(n, source))}</title>'
            f'<rect x="{x - w / 2:.1f}" y="{y:.1f}" width="{w:.1f}" height="{_NODE_H}" rx="4"/>'
            f'<text x="{x:.1f}" y="{y + _NODE_H / 2:.1f}">{escape(_picture_label(n))}</text></g>'
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"
