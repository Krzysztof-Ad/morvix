# Metamorphic relations (Section 13).
#
# A metamorphic relation transforms an input in a way whose effect on the OUTPUT
# is known, then checks that the solution's two outputs relate as expected. For
# example, for an order-independent problem (sum, max, count) permuting the input
# must leave the output unchanged. A violation means the solution is sensitive to
# something it shouldn't be - a real bug - found WITHOUT any reference answer.
#
# Honesty: every relation compares two of the SOLUTION's own outputs. It never
# reads, computes, or asserts a "correct" answer. If either run crashes or hangs
# the result is inconclusive, never a violation. The user picks the relation that
# should hold for their problem.

import random
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from morvix.errors import UserError


@dataclass
class RelationVerdict:
    holds: Optional[bool]  # True/False, or None when inconclusive (a run misbehaved)
    detail: str = ""


@dataclass
class Relation:
    name: str
    summary: str
    transform: Callable  # (rng, text, params) -> follow-up input text


RELATIONS: Dict[str, Relation] = {}


def register_relation(rel: Relation) -> Relation:
    RELATIONS[rel.name] = rel
    return rel


def list_relations():
    return sorted(RELATIONS)


def get_relation(name: str) -> Relation:
    if name not in RELATIONS:
        known = ", ".join(list_relations())
        raise UserError(f"Unknown relation '{name}'.", hint=f"Try one of: {known}")
    return RELATIONS[name]


def _per_line(text, fn):
    """Apply fn to the whitespace tokens of each line, preserving line structure."""
    out = []
    for line in text.split("\n"):
        toks = line.split()
        out.append(" ".join(fn(toks)) if len(toks) > 1 else line)
    return "\n".join(out)


def _permute(rng, text, params):
    def shuffled(toks):
        t = list(toks)
        rng.shuffle(t)
        return t

    return _per_line(text, shuffled)


def _reverse(rng, text, params):
    return _per_line(text, lambda toks: list(reversed(toks)))


def _whitespace(rng, text, params):
    # Re-emit each line with single-space separation (collapse runs of spaces).
    return "\n".join(" ".join(line.split()) for line in text.split("\n"))


register_relation(
    Relation(
        "permute-invariant",
        "shuffling each line's tokens leaves the output unchanged "
        "(order-independent problems: sum, max, count, set membership)",
        _permute,
    )
)
register_relation(
    Relation(
        "reverse-invariant",
        "reversing each line's tokens leaves the output unchanged",
        _reverse,
    )
)
register_relation(
    Relation(
        "whitespace-invariant",
        "reformatting whitespace leaves the output unchanged",
        _whitespace,
    )
)


def follow_input(relation: Relation, seed: int, text: str, params=None) -> str:
    """The transformed (follow-up) input for a base input, deterministic per seed."""
    return relation.transform(random.Random(seed), text, params or {})


def check(base_out: bytes, follow_out: bytes) -> RelationVerdict:
    """Do the two outputs satisfy the relation (currently: equal up to whitespace)?"""
    if _norm(base_out) == _norm(follow_out):
        return RelationVerdict(holds=True)
    return RelationVerdict(holds=False, detail="the output changed under the transform")


def _norm(data: bytes) -> bytes:
    return b" ".join(data.split())
