"""Командний рядок ``sipl``: parse, tree, check, run, trace, term, visualize.

Кожна команда має режим ``--json``: результат друкується як JSON-конверт
стабільного формату (див. docs/schema/cli-output.schema.json).

Коди завершення:
    0 — успіх
    1 — синтаксична помилка у програмі
    2 — неправильні аргументи командного рядка
    3 — помилка виконання (результат невизначений, напр. неініціалізована змінна)
    4 — перевищено ліміт кроків (ймовірно, нескінченний цикл)
    5 — помилка введення/виведення (файл не знайдено тощо)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from sipl import __version__
from sipl.ast import variables
from sipl.errors import Diagnostic, SiplError, SiplSyntaxError, StepLimitExceeded
from sipl.interpreter import DEFAULT_MAX_STEPS, Interpreter, format_state
from sipl.parser import parse_tree, to_ast
from sipl.semantics import explain_term
from sipl.visualization import (
    from_ast,
    from_parse_tree,
    render_dot,
    render_html,
    render_leaves,
    render_svg,
    render_text,
)

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_SYNTAX = 1
EXIT_USAGE = 2
EXIT_RUNTIME = 3
EXIT_STEP_LIMIT = 4
EXIT_IO = 5


class UsageError(Exception):
    pass


class _Context:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.command: str = args.command
        self.file: str = args.file
        self.json: bool = getattr(args, "json", False)
        self.source: str = ""

    # ------------------------------------------------------------ виведення

    def envelope(self, ok: bool, result: Any, diagnostics: list[Diagnostic]) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "tool": "sipl",
            "version": __version__,
            "command": self.command,
            "file": self.file,
            "ok": ok,
            "result": result,
            "diagnostics": [d.to_dict() for d in diagnostics],
        }

    def emit_json(self, ok: bool, result: Any, diagnostics: list[Diagnostic] | None = None) -> None:
        print(json.dumps(self.envelope(ok, result, diagnostics or []), ensure_ascii=False, indent=2))

    def report(self, diag: Diagnostic, result: Any = None) -> None:
        if self.json:
            self.emit_json(False, result, [diag])
        else:
            print(diag.format(self.source or None, self.file), file=sys.stderr)

    def write(self, text: str) -> None:
        output = getattr(self.args, "output", None)
        if output:
            Path(output).write_text(text, encoding="utf-8")
            if not self.json:
                print(f"записано: {output}", file=sys.stderr)
        else:
            sys.stdout.write(text if text.endswith("\n") else text + "\n")


def _read(ctx: _Context) -> str:
    if ctx.file == "-":
        return sys.stdin.read()
    return Path(ctx.file).read_text(encoding="utf-8")


def parse_state(items: Sequence[str] | None) -> dict[str, int]:
    """``["X=5", "Y=2"]`` або ``["X=5,Y=2"]`` → ``{"X": 5, "Y": 2}``."""
    state: dict[str, int] = {}
    for item in items or []:
        for part in item.split(","):
            part = part.strip()
            if not part:
                continue
            name, sep, value = part.partition("=")
            name = name.strip()
            if not sep or not name.isidentifier():
                raise UsageError(f"неправильне значення стану '{part}', очікується ІМ'Я=ЧИСЛО")
            try:
                state[name] = int(value.strip())
            except ValueError:
                raise UsageError(f"значення змінної {name} має бути цілим числом: '{value.strip()}'") from None
    return state


# ---------------------------------------------------------------- команди

def cmd_check(ctx: _Context) -> int:
    program = to_ast(parse_tree(ctx.source))
    names = variables(program)
    if ctx.json:
        ctx.emit_json(True, {"variables": names})
    else:
        print(f"{ctx.file}: синтаксис коректний; змінні: {', '.join(names) or '—'}")
    return EXIT_OK


def cmd_parse(ctx: _Context) -> int:
    program = to_ast(parse_tree(ctx.source))
    if ctx.json:
        ctx.emit_json(True, {"ast": program.to_dict()})
        return EXIT_OK
    fmt = ctx.args.format
    vis = from_ast(program)
    if fmt == "dot":
        ctx.write(render_dot(vis, ctx.source, "ast"))
    elif fmt == "svg":
        ctx.write(render_svg(vis, ctx.source))
    else:
        ctx.write(render_text(vis, show_spans=ctx.args.spans))
    return EXIT_OK


def cmd_tree(ctx: _Context) -> int:
    tree = parse_tree(ctx.source)
    vis = from_parse_tree(tree)
    if ctx.json:
        ctx.emit_json(True, {"parse_tree": tree.to_dict(), "leaves": render_leaves(vis)})
        return EXIT_OK
    fmt = ctx.args.format
    if fmt == "dot":
        ctx.write(render_dot(vis, ctx.source, "parse_tree"))
    elif fmt == "svg":
        ctx.write(render_svg(vis, ctx.source))
    elif fmt == "leaves":
        ctx.write(render_leaves(vis))
    else:
        ctx.write(render_text(vis, show_spans=ctx.args.spans))
    return EXIT_OK


def cmd_run(ctx: _Context) -> int:
    program = to_ast(parse_tree(ctx.source))
    interp = Interpreter(ctx.args.max_steps)
    result = interp.run(program, ctx.state)
    if ctx.json:
        ctx.emit_json(True, {"state": result.state, "steps": result.steps})
    else:
        print(format_state(result.state))
    return EXIT_OK


def cmd_trace(ctx: _Context) -> int:
    program = to_ast(parse_tree(ctx.source))
    trace = Interpreter(ctx.args.max_steps).trace(program, ctx.state)
    result = {"events": [e.to_dict() for e in trace.events], "state": trace.state, "steps": trace.steps}
    if ctx.json:
        ctx.emit_json(trace.ok, result, [trace.error] if trace.error else [])
    else:
        print(trace.format())
        if trace.error:
            print(trace.error.format(ctx.source, ctx.file), file=sys.stderr)
    if trace.error is None:
        return EXIT_OK
    return EXIT_STEP_LIMIT if trace.error.code == StepLimitExceeded.code else EXIT_RUNTIME


def cmd_term(ctx: _Context) -> int:
    program = to_ast(parse_tree(ctx.source))
    term, steps = explain_term(program)
    ascii_mode = ctx.args.ascii
    if ctx.json:
        result: dict[str, Any] = {
            "term": term.render(),
            "term_ascii": term.render(ascii=True),
            "tree": term.to_dict(),
        }
        if ctx.args.explain:
            result["steps"] = [s.to_dict(ascii_mode) for s in steps]
        ctx.emit_json(True, result)
        return EXIT_OK
    if ctx.args.explain:
        for s in steps:
            print("  " * s.depth + s.render(ascii_mode))
        print()
    print(term.render(ascii_mode))
    return EXIT_OK


def cmd_visualize(ctx: _Context) -> int:
    title = Path(ctx.file).name if ctx.file != "-" else "SIPL"
    html = render_html(ctx.source, title)
    output = ctx.args.output or (str(Path(ctx.file).with_suffix(".html")) if ctx.file != "-" else None)
    if output:
        Path(output).write_text(html, encoding="utf-8")
    else:
        sys.stdout.write(html)
    if ctx.json:
        ctx.emit_json(True, {"output": output})
    elif output:
        print(f"записано: {output}", file=sys.stderr)
    return EXIT_OK


COMMANDS = {
    "check": cmd_check,
    "parse": cmd_parse,
    "tree": cmd_tree,
    "run": cmd_run,
    "trace": cmd_trace,
    "term": cmd_term,
    "visualize": cmd_visualize,
}


# ---------------------------------------------------------------- argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sipl",
        description="Інструменти для мови SIPL: синтаксис, виконання, семантичні терми, візуалізація.",
    )
    parser.add_argument("--version", action="version", version=f"sipl {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="КОМАНДА")

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("file", metavar="ФАЙЛ", help="SIPL-програма (.sipl) або '-' для stdin")
        p.add_argument("--json", action="store_true", help="вивести результат у JSON")
        return p

    def add_state(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "-s", "--set", action="append", metavar="X=N", dest="state",
            help="початкове значення змінної (можна повторювати або писати X=1,Y=2)",
        )
        p.add_argument(
            "--max-steps", type=int, default=DEFAULT_MAX_STEPS, metavar="N",
            help=f"ліміт елементарних кроків (за замовчуванням {DEFAULT_MAX_STEPS})",
        )

    add("check", "перевірити синтаксичну коректність програми")

    p = add("parse", "побудувати абстрактне синтаксичне дерево (AST)")
    p.add_argument("-f", "--format", choices=["text", "dot", "svg"], default="text")
    p.add_argument("--spans", action="store_true", help="показати позиції рядок:колонка")
    p.add_argument("-o", "--output", metavar="ФАЙЛ", help="записати у файл")

    p = add("tree", "побудувати дерево синтаксичного виводу (parse tree)")
    p.add_argument("-f", "--format", choices=["text", "dot", "svg", "leaves"], default="text")
    p.add_argument("--spans", action="store_true", help="показати позиції рядок:колонка")
    p.add_argument("-o", "--output", metavar="ФАЙЛ", help="записати у файл")

    add_state(add("run", "виконати програму і показати кінцевий стан"))
    add_state(add("trace", "виконати програму і показати всі події виконання"))

    p = add("term", "побудувати семантичний терм програми")
    p.add_argument("--explain", action="store_true", help="показати застосовані правила заміни")
    p.add_argument("--ascii", action="store_true", help="ASCII-нотація (=> замість ⇒, . замість ·)")

    p = add("visualize", "згенерувати HTML-сторінку: текст ↔ дерево виводу ↔ AST")
    p.add_argument("-o", "--output", metavar="ФАЙЛ", help="шлях до HTML (за замовчуванням поруч із програмою)")
    return parser


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover
                pass


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = _Context(args)

    try:
        ctx.state = parse_state(getattr(args, "state", None))
        if getattr(args, "max_steps", 1) <= 0:
            raise UsageError("--max-steps має бути додатним числом")
    except UsageError as err:
        if ctx.json:
            ctx.emit_json(False, None, [Diagnostic("usage-error", str(err))])
        else:
            parser.print_usage(sys.stderr)
            print(f"sipl: помилка: {err}", file=sys.stderr)
        return EXIT_USAGE

    try:
        ctx.source = _read(ctx)
    except OSError as err:
        ctx.report(Diagnostic("io-error", f"не вдалося прочитати файл: {err.strerror or err}"))
        return EXIT_IO

    try:
        return COMMANDS[args.command](ctx)
    except SiplSyntaxError as err:
        ctx.report(err.diagnostic)
        return EXIT_SYNTAX
    except StepLimitExceeded as err:
        ctx.report(err.diagnostic)
        return EXIT_STEP_LIMIT
    except SiplError as err:
        ctx.report(err.diagnostic)
        return EXIT_RUNTIME
    except OSError as err:
        ctx.report(Diagnostic("io-error", f"не вдалося записати файл: {err.strerror or err}"))
        return EXIT_IO


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
