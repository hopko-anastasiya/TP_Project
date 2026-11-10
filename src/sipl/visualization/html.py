"""VIS-02: інтерактивна HTML-сторінка «вихідний текст ↔ дерево виводу ↔ AST».

Сторінка самодостатня (без зовнішніх скриптів). Дані генеруються з
реальних структур: дерево виводу та AST серіалізуються в JSON і вбудовуються
в сторінку. Вибір вузла в будь-якому дереві підсвічує відповідний фрагмент
тексту та відповідні вузли іншого дерева (за збігом SourceSpan); клік у
тексті вибирає найглибший вузол AST у цій позиції.
"""

from __future__ import annotations

import json
from html import escape

from sipl.parser import parse_tree, to_ast
from sipl.visualization.exporters import render_svg
from sipl.visualization.tree import from_ast, from_parse_tree


def render_html(source: str, title: str = "SIPL") -> str:
    """Будує HTML-сторінку для програми. Кидає SiplSyntaxError для некоректного тексту."""
    ptree = parse_tree(source)
    program = to_ast(ptree)
    vis_parse = from_parse_tree(ptree)
    vis_ast = from_ast(program)
    data = {
        "source": source,
        "parseTree": vis_parse.to_dict(),
        "ast": vis_ast.to_dict(),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    stats = (
        f"дерево виводу: {vis_parse.count()} вузлів "
        f"({sum(1 for n in vis_parse.walk() if n.kind == 'terminal')} листків-терміналів) · "
        f"AST: {vis_ast.count()} вузлів"
    )
    return (
        _TEMPLATE.replace("{{TITLE}}", escape(title))
        .replace("{{STATS}}", escape(stats))
        .replace("{{PARSE_SVG}}", render_svg(vis_parse, source, "sipl-tree parse-svg"))
        .replace("{{AST_SVG}}", render_svg(vis_ast, source, "sipl-tree ast-svg"))
        .replace("{{DATA}}", payload)
    )


_TEMPLATE = r"""<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}} — дерево виводу та AST</title>
<style>
:root {
  --bg: #f7f8fa; --panel: #ffffff; --text: #1d2433; --muted: #5d6678; --border: #dde1e8;
  --accent: #d9480f; --mark: #ffe08a; --approx: #ffd8c2;
  --nt: #2f5597; --term: #9a6a00; --stm: #2f5597; --aexp: #2f7a4b; --bexp: #6b4ea0;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14171c; --panel: #1c2027; --text: #e6e9ef; --muted: #9aa3b2; --border: #2e3440;
    --accent: #ff8a4c; --mark: #6b5310; --approx: #5a3420;
    --nt: #8fb3ff; --term: #f0c060; --stm: #8fb3ff; --aexp: #7fd39b; --bexp: #c4a8ff;
  }
}
:root[data-theme="dark"] {
  --bg: #14171c; --panel: #1c2027; --text: #e6e9ef; --muted: #9aa3b2; --border: #2e3440;
  --accent: #ff8a4c; --mark: #6b5310; --approx: #5a3420;
  --nt: #8fb3ff; --term: #f0c060; --stm: #8fb3ff; --aexp: #7fd39b; --bexp: #c4a8ff;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
header { padding: 14px 16px 6px; }
h1 { font-size: 18px; margin: 0 0 2px; }
.stats, .hint { color: var(--muted); font-size: 12.5px; }
main { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 12px; padding: 10px 16px 16px; }
@media (max-width: 1000px) { main { grid-template-columns: minmax(0, 1fr); } }
section { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  display: flex; flex-direction: column; min-height: 0; max-height: 80vh; }
section h2 { font-size: 13px; margin: 0; padding: 8px 12px; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.body { overflow: auto; padding: 8px 12px; flex: 1; }
pre#src { margin: 0; font: 13px/1.5 ui-monospace, Consolas, monospace; white-space: pre; cursor: text; }
mark { background: var(--mark); color: inherit; border-radius: 2px; }
ul.tree, ul.tree ul { list-style: none; margin: 0; padding-left: 16px; }
ul.tree { padding-left: 0; font: 12.5px/1.6 ui-monospace, Consolas, monospace; }
.toggle { display: inline-block; width: 14px; color: var(--muted); cursor: pointer; user-select: none; }
.node { cursor: pointer; padding: 0 3px; border-radius: 3px; white-space: nowrap; }
.node:hover { outline: 1px solid var(--border); }
.node.match { background: var(--mark); }
.node.approx { background: var(--approx); }
.node.selected { outline: 2px solid var(--accent); }
.k-nonterminal { color: var(--nt); } .k-terminal { color: var(--term); }
.k-stm, .k-program { color: var(--stm); } .k-aexp { color: var(--aexp); } .k-bexp { color: var(--bexp); }
.detail { color: var(--muted); font-size: 11px; margin-left: 4px; }
li.collapsed > ul { display: none; }
.tabs button { font: inherit; font-size: 12px; background: none; color: var(--muted);
  border: 1px solid var(--border); border-radius: 5px; padding: 1px 8px; cursor: pointer; }
.tabs button.on { color: var(--text); border-color: var(--accent); }
.svgwrap { display: none; } .svgwrap svg { background: #fff; border-radius: 6px; }
.svgwrap svg .node { cursor: pointer; }
.svgwrap svg .node.match rect, .svgwrap svg .node.approx rect { fill: #ffe08a; }
.svgwrap svg .node.selected rect { stroke: #d9480f; stroke-width: 2.5; }
section.svg-mode .svgwrap { display: block; } section.svg-mode ul.tree { display: none; }
#info { font: 12px ui-monospace, Consolas, monospace; color: var(--muted); padding: 6px 12px;
  border-top: 1px solid var(--border); min-height: 2.2em; }
</style>
</head>
<body>
<header>
  <h1>{{TITLE}}: конкретний і абстрактний синтаксис</h1>
  <div class="stats">{{STATS}}</div>
  <div class="hint">Клікніть вузол у будь-якому дереві або місце в тексті: відповідні фрагменти
    підсвітяться в усіх трьох поданнях. Жовтий колір позначає точний збіг позиції, помаранчевий —
    найменший вузол AST, що містить вибраний фрагмент (наприклад, для дужок і терміналів, яких в AST немає).</div>
</header>
<main>
  <section id="p-src">
    <h2>Вихідний текст</h2>
    <div class="body"><pre id="src"></pre></div>
    <div id="info">—</div>
  </section>
  <section id="p-parse">
    <h2><span>Дерево синтаксичного виводу (parse tree)</span>
      <span class="tabs"><button class="on" data-mode="list">список</button><button data-mode="svg">SVG</button></span></h2>
    <div class="body"><ul class="tree" id="parse"></ul><div class="svgwrap">{{PARSE_SVG}}</div></div>
  </section>
  <section id="p-ast">
    <h2><span>Абстрактне синтаксичне дерево (AST)</span>
      <span class="tabs"><button class="on" data-mode="list">список</button><button data-mode="svg">SVG</button></span></h2>
    <div class="body"><ul class="tree" id="ast"></ul><div class="svgwrap">{{AST_SVG}}</div></div>
  </section>
</main>
<script id="sipl-data" type="application/json">{{DATA}}</script>
<script>
(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("sipl-data").textContent);
  var src = data.source;
  var pre = document.getElementById("src");
  var info = document.getElementById("info");
  var registry = { parse: [], ast: [] };

  function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  function build(node, container, treeName, depth) {
    var li = document.createElement("li");
    var tog = document.createElement("span");
    tog.className = "toggle";
    tog.textContent = node.children.length ? "▾" : "";
    tog.onclick = function (e) {
      e.stopPropagation();
      li.classList.toggle("collapsed");
      tog.textContent = li.classList.contains("collapsed") ? "▸" : "▾";
    };
    var label = document.createElement("span");
    label.className = "node k-" + node.kind;
    label.textContent = node.kind === "terminal" ? "'" + node.label + "'" : node.label;
    if (node.detail && node.kind !== "terminal") {
      var d = document.createElement("span");
      d.className = "detail";
      d.textContent = node.detail;
      label.appendChild(d);
    }
    if (node.span) {
      label.dataset.start = node.span.start;
      label.dataset.end = node.span.end;
      registry[treeName].push({ el: label, s: node.span.start, e: node.span.end, depth: depth, span: node.span, label: node.label });
    }
    label.onclick = function (e) { e.stopPropagation(); select(node.span.start, node.span.end, label); };
    li.appendChild(tog);
    li.appendChild(label);
    if (node.children.length) {
      var ul = document.createElement("ul");
      node.children.forEach(function (c) { build(c, ul, treeName, depth + 1); });
      li.appendChild(ul);
    }
    container.appendChild(li);
  }

  build(data.parseTree, document.getElementById("parse"), "parse", 0);
  build(data.ast, document.getElementById("ast"), "ast", 0);
  pre.innerHTML = esc(src);

  function svgNodes(cls) {
    return Array.prototype.slice.call(document.querySelectorAll("svg." + cls + " g.node"));
  }
  var svgSets = { parse: svgNodes("parse-svg"), ast: svgNodes("ast-svg") };
  Object.keys(svgSets).forEach(function (k) {
    svgSets[k].forEach(function (g) {
      g.addEventListener("click", function (e) {
        e.stopPropagation();
        select(+g.dataset.start, +g.dataset.end, g);
      });
    });
  });

  function clear() {
    document.querySelectorAll(".match, .approx, .selected").forEach(function (el) {
      el.classList.remove("match", "approx", "selected");
    });
  }

  function markTree(name, s, e) {
    var exact = registry[name].filter(function (r) { return r.s === s && r.e === e; });
    var list = exact;
    var cls = "match";
    if (!exact.length) {
      var containing = registry[name].filter(function (r) { return r.s <= s && r.e >= e; });
      containing.sort(function (a, b) { return (a.e - a.s) - (b.e - b.s) || b.depth - a.depth; });
      list = containing.slice(0, 1);
      cls = "approx";
    }
    list.forEach(function (r) {
      r.el.classList.add(cls);
      var li = r.el.parentElement;
      while (li && li.tagName === "LI") { li.classList.remove("collapsed"); li = li.parentElement.parentElement; }
    });
    svgSets[name].forEach(function (g) {
      var gs = +g.dataset.start, ge = +g.dataset.end;
      if (list.some(function (r) { return r.s === gs && r.e === ge; })) g.classList.add(cls);
    });
    return list;
  }

  function select(s, e, el) {
    clear();
    pre.innerHTML = esc(src.slice(0, s)) + "<mark>" + esc(src.slice(s, e)) + "</mark>" + esc(src.slice(e));
    var m = pre.querySelector("mark");
    if (m && m.scrollIntoView) m.scrollIntoView({ block: "nearest" });
    var p = markTree("parse", s, e);
    var a = markTree("ast", s, e);
    if (el) el.classList.add("selected");
    var first = (p[0] || a[0]);
    var span = first ? first.span : null;
    info.textContent = (span ? span.line + ":" + span.column + "–" + span.end_line + ":" + span.end_column + "  " : "") +
      "parse: " + (p.map(function (r) { return r.label; }).join(", ") || "—") +
      "  |  AST: " + (a.map(function (r) { return r.label; }).join(", ") || "—");
  }

  pre.addEventListener("click", function () {
    var sel = window.getSelection();
    if (!sel || !sel.rangeCount) return;
    var range = sel.getRangeAt(0).cloneRange();
    range.setStart(pre, 0);
    var offset = range.toString().length;
    var hits = registry.ast.filter(function (r) { return r.s <= offset && offset < r.e; });
    if (!hits.length) return;
    hits.sort(function (x, y) { return (x.e - x.s) - (y.e - y.s); });
    select(hits[0].s, hits[0].e, hits[0].el);
  });

  document.querySelectorAll(".tabs").forEach(function (tabs) {
    tabs.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      tabs.querySelectorAll("button").forEach(function (x) { x.classList.toggle("on", x === b); });
      tabs.closest("section").classList.toggle("svg-mode", b.dataset.mode === "svg");
    });
  });
})();
</script>
</body>
</html>
"""
