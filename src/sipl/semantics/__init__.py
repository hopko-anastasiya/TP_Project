"""Семантичні терми SIPL-програм (SEM-01)."""

from sipl.semantics.builder import RuleStep, build_term, explain_term
from sipl.semantics.terms import (
    AssignTerm,
    Compose,
    Const,
    Deref,
    Group,
    Identity,
    IfTerm,
    Superposition,
    Term,
    WhileTerm,
)

__all__ = [
    "AssignTerm",
    "Compose",
    "Const",
    "Deref",
    "Group",
    "Identity",
    "IfTerm",
    "RuleStep",
    "Superposition",
    "Term",
    "WhileTerm",
    "build_term",
    "explain_term",
]
