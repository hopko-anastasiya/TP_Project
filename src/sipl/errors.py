"""Помилки та діагностика SIPL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sipl.ast import SourceSpan


@dataclass
class Diagnostic:
    """Повідомлення для користувача, прив'язане до місця у тексті."""

    code: str
    message: str
    span: SourceSpan | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "span": self.span.to_dict() if self.span else None,
        }

    def format(self, source: str | None = None, filename: str = "<input>") -> str:
        """Текст у стилі компілятора: ``file:рядок:колонка: помилка: …`` + рядок коду з ``^``."""
        severity = {"error": "помилка", "warning": "попередження"}.get(self.severity, self.severity)
        if self.span is None:
            return f"{filename}: {severity}: {self.message}"
        head = f"{filename}:{self.span.line}:{self.span.column}: {severity}: {self.message}"
        if source is None:
            return head
        lines = source.splitlines()
        if not 1 <= self.span.line <= len(lines):
            return head
        text = lines[self.span.line - 1]
        width = 1
        if self.span.end_line == self.span.line:
            width = max(1, self.span.end_column - self.span.column)
        caret = " " * (self.span.column - 1) + "^" * width
        return f"{head}\n  {text}\n  {caret}"


class SiplError(Exception):
    """Базовий клас помилок SIPL."""

    code = "error"

    def __init__(self, message: str, span: SourceSpan | None = None):
        super().__init__(message)
        self.message = message
        self.span = span

    @property
    def diagnostic(self) -> Diagnostic:
        return Diagnostic(self.code, self.message, self.span)

    def __str__(self) -> str:
        if self.span:
            return f"{self.span.line}:{self.span.column}: {self.message}"
        return self.message


class SiplSyntaxError(SiplError):
    code = "syntax-error"


class SiplRuntimeError(SiplError):
    """Результат програми невизначений (наприклад, читання неініціалізованої змінної)."""

    code = "runtime-error"


class UndefinedVariableError(SiplRuntimeError):
    code = "undefined-variable"

    def __init__(self, name: str, span: SourceSpan | None = None):
        super().__init__(
            f"змінна '{name}' не має значення у поточному стані (st({name}) невизначено)", span
        )
        self.name = name


class StepLimitExceeded(SiplRuntimeError):
    code = "step-limit"

    def __init__(self, limit: int, span: SourceSpan | None = None):
        super().__init__(
            f"перевищено ліміт кроків виконання ({limit}); можливо, цикл не завершується", span
        )
        self.limit = limit
