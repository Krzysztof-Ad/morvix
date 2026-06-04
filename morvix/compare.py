# Comparison strategies: how "correct" is decided for output (Section 14).
#
# A comparator answers one question: given the bytes a program produced and the
# bytes (or hash, or checker) we expected, does it pass? It knows nothing about
# language or execution model. The exit-status, signal and memory dimensions are
# judged separately and combined by judge.py - keeping them apart is what lets a
# case require "exit 0 AND output matches AND no leaks" (Section 14.7).
#
# exact and whitespace live here as the references; float, hash and checker
# register themselves from comparators.py.

import difflib
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from morvix.cases import TestCase


@dataclass
class CompareInput:
    observed: bytes
    expected: bytes               # expected output bytes (may be empty for hash/checker)
    case: TestCase
    project: object
    params: dict                  # the project's comparison settings (epsilon, checker, ...)


@dataclass
class Verdict:
    passed: bool
    detail: str = ""
    diff: Optional[str] = None    # a unified diff when one is meaningful (never for hash)


CompareFn = Callable[[CompareInput], Verdict]

_REGISTRY: Dict[str, CompareFn] = {}


def register_comparator(name: str, fn: CompareFn) -> None:
    _REGISTRY[name] = fn


def get_comparator(name: str) -> CompareFn:
    _load_builtins()
    if name not in _REGISTRY:
        from morvix.errors import UserError

        known = ", ".join(sorted(_REGISTRY))
        raise UserError(f"Unknown comparison strategy '{name}'.", hint=f"Choose one of: {known}.")
    return _REGISTRY[name]


def list_strategies():
    _load_builtins()
    return sorted(_REGISTRY)


def compare(strategy: str, ci: CompareInput) -> Verdict:
    return get_comparator(strategy)(ci)


def make_diff(expected: bytes, observed: bytes, context: int = 3) -> str:
    """A unified diff of expected vs observed, decoded leniently for display."""
    exp = expected.decode("utf-8", "replace").splitlines()
    obs = observed.decode("utf-8", "replace").splitlines()
    lines = difflib.unified_diff(exp, obs, "expected", "observed", n=context, lineterm="")
    return "\n".join(lines)


# --- exact (byte-for-byte, Section 14.1) ---

def _exact(ci: CompareInput) -> Verdict:
    if ci.observed == ci.expected:
        return Verdict(True)
    return Verdict(False, "output differs", diff=make_diff(ci.expected, ci.observed))


# --- whitespace-insensitive (the sane default, Section 14.2) ---

def _normalize_ws(data: bytes) -> bytes:
    # Collapse runs of whitespace to single spaces and strip each line, so
    # "two  spaces" and trailing newlines never fail a correct answer.
    text = data.decode("utf-8", "replace")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).encode("utf-8")


def _whitespace(ci: CompareInput) -> Verdict:
    if _normalize_ws(ci.observed) == _normalize_ws(ci.expected):
        return Verdict(True)
    return Verdict(False, "output differs (ignoring whitespace)",
                   diff=make_diff(ci.expected, ci.observed))


register_comparator("exact", _exact)
register_comparator("whitespace", _whitespace)


_loaded = False


def _load_builtins() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    from morvix import comparators  # noqa: F401  (registers float, hash, checker)
