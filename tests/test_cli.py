"""CORE-05: інтеграційні тести командного рядка, коди завершення та JSON-схема."""

import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from sipl import __version__
from sipl.cli import (
    EXIT_IO,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_STEP_LIMIT,
    EXIT_SYNTAX,
    EXIT_USAGE,
    UsageError,
    main,
    parse_state,
)

from conftest import EXAMPLES, ROOT

SCHEMA = json.loads((ROOT / "docs" / "schema" / "cli-output.schema.json").read_text(encoding="utf-8"))
POWER = str(EXAMPLES / "power.sipl")
INVALID = str(EXAMPLES / "invalid" / "trailing_semicolon.sipl")


def run_cli(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def run_json(capsys, *argv):
    code, out, err = run_cli(capsys, *argv, "--json")
    data = json.loads(out)
    jsonschema.validate(data, SCHEMA)
    return code, data


# ------------------------------------------------------------ текстовий режим

def test_check_ok(capsys):
    code, out, _ = run_cli(capsys, "check", POWER)
    assert code == EXIT_OK
    assert "синтаксис коректний" in out and "R, Y, X" in out


def test_check_syntax_error(capsys):
    code, out, err = run_cli(capsys, "check", INVALID)
    assert code == EXIT_SYNTAX
    assert out == ""
    assert "trailing_semicolon.sipl:5:1: помилка:" in err
    assert "^^^" in err


def test_run_text(capsys):
    code, out, _ = run_cli(capsys, "run", POWER, "-s", "X=5", "-s", "Y=2")
    assert code == EXIT_OK
    assert out.strip() == "[X ↦ 5, Y ↦ 0, R ↦ 25]"


def test_run_undefined_variable(capsys):
    code, _, err = run_cli(capsys, "run", POWER, "-s", "X=5")
    assert code == EXIT_RUNTIME
    assert "змінна 'Y'" in err


def test_step_limit(capsys, tmp_path):
    f = tmp_path / "loop.sipl"
    f.write_text("begin while 1 = 1 do skip end", encoding="utf-8")
    code, _, err = run_cli(capsys, "run", str(f), "--max-steps", "10")
    assert code == EXIT_STEP_LIMIT
    assert "ліміт кроків" in err


def test_trace_text(capsys):
    code, out, _ = run_cli(capsys, "trace", POWER, "-s", "X=3,Y=1")
    assert code == EXIT_OK
    assert "assign     R: ⊥ → 1" in out
    assert "finish" in out


def test_trace_runtime_error(capsys, tmp_path):
    f = tmp_path / "bad.sipl"
    f.write_text("begin X := 1; Y := Z end", encoding="utf-8")
    code, out, err = run_cli(capsys, "trace", str(f))
    assert code == EXIT_RUNTIME
    assert "assign     X" in out
    assert "змінна 'Z'" in err


@pytest.mark.parametrize("fmt, marker", [("text", "Program"), ("dot", "digraph"), ("svg", "<svg")])
def test_parse_formats(capsys, fmt, marker):
    code, out, _ = run_cli(capsys, "parse", POWER, "-f", fmt)
    assert code == EXIT_OK and marker in out


def test_parse_with_spans(capsys):
    _, out, _ = run_cli(capsys, "parse", POWER, "--spans")
    assert "Assign R  [5:3-5:9]" in out


@pytest.mark.parametrize(
    "fmt, marker",
    [("text", "<програма> NP1"), ("dot", "digraph"), ("svg", "<svg"), ("leaves", "1 begin 2 R 3 :=")],
)
def test_tree_formats(capsys, fmt, marker):
    code, out, _ = run_cli(capsys, "tree", POWER, "-f", fmt)
    assert code == EXIT_OK and marker in out


def test_tree_output_file(capsys, tmp_path):
    target = tmp_path / "tree.dot"
    code, out, err = run_cli(capsys, "tree", POWER, "-f", "dot", "-o", str(target))
    assert code == EXIT_OK and out == ""
    assert target.read_text(encoding="utf-8").startswith("digraph")
    assert "записано" in err


def test_term_text(capsys):
    code, out, _ = run_cli(capsys, "term", POWER)
    assert code == EXIT_OK
    assert out.strip() == "AS^R(1) · WH(S2(gr, Y⇒, 0), AS^R(S2(mult, R⇒, X⇒)) · AS^Y(S2(sub, Y⇒, 1)))"


def test_term_explain_ascii(capsys):
    _, out, _ = run_cli(capsys, "term", POWER, "--explain", "--ascii")
    assert "[NS_Prog] sem_P(" in out
    assert "  [NS_Stm_Seq]" in out
    assert out.strip().splitlines()[-1].startswith("AS^R(1) . WH(S2(gr, Y=>, 0)")


def test_visualize_default_output(capsys, tmp_path):
    src = tmp_path / "prog.sipl"
    src.write_text(Path(POWER).read_text(encoding="utf-8"), encoding="utf-8")
    code, _, err = run_cli(capsys, "visualize", str(src))
    assert code == EXIT_OK
    html = (tmp_path / "prog.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in html and "prog.sipl" in html
    assert "записано" in err


def test_visualize_stdin_to_stdout(capsys, monkeypatch):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("begin skip end"))
    code, out, _ = run_cli(capsys, "visualize", "-")
    assert code == EXIT_OK and out.startswith("<!doctype html>")


def test_missing_file(capsys):
    code, _, err = run_cli(capsys, "check", "no-such-file.sipl")
    assert code == EXIT_IO
    assert "не вдалося прочитати файл" in err


def test_bad_state_is_usage_error(capsys):
    code, _, err = run_cli(capsys, "run", POWER, "-s", "X")
    assert code == EXIT_USAGE and "ІМ'Я=ЧИСЛО" in err


def test_bad_max_steps(capsys):
    code, _, err = run_cli(capsys, "run", POWER, "--max-steps", "0")
    assert code == EXIT_USAGE and "--max-steps" in err


def test_argparse_usage_error(capsys):
    with pytest.raises(SystemExit) as info:
        main(["frobnicate"])
    assert info.value.code == EXIT_USAGE
    capsys.readouterr()


def test_parse_state_helper():
    assert parse_state(["X=1, Y=-2", "Z = 3"]) == {"X": 1, "Y": -2, "Z": 3}
    assert parse_state(None) == {}
    with pytest.raises(UsageError):
        parse_state(["1X=2"])
    with pytest.raises(UsageError):
        parse_state(["X=abc"])


# ------------------------------------------------------------ JSON-режим

def test_json_check(capsys):
    code, data = run_json(capsys, "check", POWER)
    assert code == EXIT_OK
    assert data["ok"] is True and data["command"] == "check"
    assert data["version"] == __version__
    assert data["result"] == {"variables": ["R", "Y", "X"]}
    assert data["diagnostics"] == []


def test_json_syntax_error(capsys):
    code, data = run_json(capsys, "check", INVALID)
    assert code == EXIT_SYNTAX
    assert data["ok"] is False and data["result"] is None
    (diag,) = data["diagnostics"]
    assert diag["code"] == "syntax-error"
    assert (diag["span"]["line"], diag["span"]["column"]) == (5, 1)


def test_json_parse(capsys):
    _, data = run_json(capsys, "parse", POWER)
    assert data["result"]["ast"]["type"] == "Program"


def test_json_tree(capsys):
    _, data = run_json(capsys, "tree", POWER)
    assert data["result"]["parse_tree"]["symbol"] == "<програма>"
    assert data["result"]["leaves"].startswith("1 begin")


def test_json_run(capsys):
    code, data = run_json(capsys, "run", POWER, "-s", "X=5,Y=2")
    assert code == EXIT_OK
    assert data["result"] == {"state": {"X": 5, "Y": 0, "R": 25}, "steps": 8}


def test_json_run_errors(capsys):
    code, data = run_json(capsys, "run", POWER, "-s", "X=5")
    assert code == EXIT_RUNTIME
    assert data["diagnostics"][0]["code"] == "undefined-variable"


def test_json_trace(capsys):
    code, data = run_json(capsys, "trace", POWER, "-s", "X=5,Y=2")
    assert code == EXIT_OK
    kinds = {e["kind"] for e in data["result"]["events"]}
    assert kinds == {
        "program_started", "before_statement", "after_statement",
        "variable_changed", "condition_evaluated", "program_finished",
    }
    assert data["result"]["state"]["R"] == 25


def test_json_trace_step_limit(capsys, tmp_path):
    f = tmp_path / "loop.sipl"
    f.write_text("begin while 1 = 1 do skip end", encoding="utf-8")
    code, data = run_json(capsys, "trace", str(f), "--max-steps", "4")
    assert code == EXIT_STEP_LIMIT
    assert data["ok"] is False
    assert data["result"]["state"] is None
    assert data["diagnostics"][0]["code"] == "step-limit"


def test_json_term(capsys):
    _, data = run_json(capsys, "term", POWER, "--explain")
    assert data["result"]["term"].startswith("AS^R(1) · WH(")
    assert data["result"]["term_ascii"].startswith("AS^R(1) . WH(")
    assert data["result"]["tree"]["type"] == "compose"
    assert data["result"]["steps"][0]["rule"] == "NS_Prog"


def test_json_visualize(capsys, tmp_path):
    out_file = tmp_path / "v.html"
    _, data = run_json(capsys, "visualize", POWER, "-o", str(out_file))
    assert data["result"] == {"output": str(out_file)}
    assert out_file.exists()


def test_json_io_and_usage_errors(capsys):
    code, data = run_json(capsys, "run", "missing.sipl")
    assert code == EXIT_IO and data["diagnostics"][0]["code"] == "io-error"
    code, data = run_json(capsys, "run", POWER, "-s", "oops")
    assert code == EXIT_USAGE and data["diagnostics"][0]["code"] == "usage-error"


# ------------------------------------------------------------ окремий процес

def test_module_entry_point_subprocess():
    proc = subprocess.run(
        [sys.executable, "-m", "sipl", "run", POWER, "-s", "X=2,Y=3", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    jsonschema.validate(data, SCHEMA)
    assert data["result"]["state"]["R"] == 8


def test_subprocess_exit_code_on_syntax_error():
    proc = subprocess.run(
        [sys.executable, "-m", "sipl", "check", INVALID],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == EXIT_SYNTAX
    assert "помилка" in proc.stderr
