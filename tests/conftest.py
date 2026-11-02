"""Спільні допоміжні функції тестів: читання прикладів із заголовками.

Формат заголовків у examples/*.sipl:
    // input: X=5, Y=2      — початковий стан
    // expect: R=25         — значення змінних у кінцевому стані
У examples/invalid/*.sipl:
    // error: 5:1           — рядок:колонка очікуваної синтаксичної помилки
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

_PAIR = re.compile(r"([A-Za-z_]\w*)\s*=\s*(-?\d+)")


def _pairs(text: str) -> dict[str, int]:
    return {k: int(v) for k, v in _PAIR.findall(text)}


@dataclass
class Example:
    path: Path
    source: str
    input: dict[str, int]
    expect: dict[str, int]

    @property
    def name(self) -> str:
        return self.path.stem


@dataclass
class InvalidExample:
    path: Path
    source: str
    line: int
    column: int

    @property
    def name(self) -> str:
        return self.path.stem


def valid_examples() -> list[Example]:
    result = []
    for path in sorted(EXAMPLES.glob("*.sipl")):
        source = path.read_text(encoding="utf-8")
        inp = re.search(r"//\s*input:(.*)", source)
        exp = re.search(r"//\s*expect:(.*)", source)
        result.append(Example(path, source, _pairs(inp.group(1)) if inp else {}, _pairs(exp.group(1)) if exp else {}))
    return result


def invalid_examples() -> list[InvalidExample]:
    result = []
    for path in sorted((EXAMPLES / "invalid").glob("*.sipl")):
        source = path.read_text(encoding="utf-8")
        m = re.search(r"//\s*error:\s*(\d+):(\d+)", source)
        assert m, f"{path.name}: немає заголовка // error: L:C"
        result.append(InvalidExample(path, source, int(m.group(1)), int(m.group(2))))
    return result
