"""SIPL Language Toolkit — парсер, інтерпретатор, семантичні терми та візуалізація
для навчальної мови SIPL."""

from sipl.ast import Program, SourceSpan
from sipl.errors import (
    Diagnostic,
    SiplError,
    SiplRuntimeError,
    SiplSyntaxError,
    StepLimitExceeded,
    UndefinedVariableError,
)
from sipl.parse_tree import ParseNode
from sipl.parser import parse, parse_tree
from sipl.printer import to_source

__version__ = "0.1.0"

__all__ = [
    "Diagnostic",
    "ParseNode",
    "Program",
    "SiplError",
    "SiplRuntimeError",
    "SiplSyntaxError",
    "SourceSpan",
    "StepLimitExceeded",
    "UndefinedVariableError",
    "parse",
    "parse_tree",
    "to_source",
    "__version__",
]
