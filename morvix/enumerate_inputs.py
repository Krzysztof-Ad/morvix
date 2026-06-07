# Bounded-exhaustive enumeration of a shape's whole small-input space.
#
# For tiny bounds the most thorough test is "try everything". This module walks
# the FULL finite space of a shape up to a size bound and renders each point as
# an input string, in the same on-the-wire format the random shapes use. It is
# input-only: it never runs the solution and never touches an expected answer.
#
# Two entry points:
#   enumerate_for(shape, max_n, values, cap) -> list[str]
#       Every input string for the shape up to max_n. Stops silently at `cap`
#       (the caller is responsible for logging the truncation); no error.
#   count_estimate(shape, max_n, values) -> int
#       The UNCAPPED total, so a caller can guard before enumerating millions.
#
# Supported shapes (matched to shapes.py rendering where one exists):
#   "array"/"ints"  all sequences of length 0..max_n over `values`,
#                   rendered as 'len' newline then the space-joined values.
#   "permutation"   all permutations of 1..n for every n in 0..max_n.
#   "string"        all strings of length 0..max_n over the alphabet `values`.
#   "tree"          all labelled trees on 1..max_n nodes (via Pruefer sequences),
#                   rendered as n then the edges, one per line.

import itertools
import math
from typing import List, Optional, Sequence

from morvix.errors import UserError

# The default value set for array/ints when the caller passes none. Small on
# purpose: exhaustive enumeration only makes sense for tiny alphabets.
DEFAULT_VALUES = [0, 1]
# The default alphabet for the string shape.
DEFAULT_ALPHABET = ["a", "b"]


# ---------------------------------------------------------------------------
# Value-set normalisation
# ---------------------------------------------------------------------------


def _values(values: Optional[Sequence]) -> list:
    """The value set for array/ints, falling back to the small default."""
    if values is None:
        return list(DEFAULT_VALUES)
    vals = list(values)
    return vals if vals else list(DEFAULT_VALUES)


def _alphabet(values: Optional[Sequence]) -> list:
    """The alphabet for the string shape: each value rendered as one char."""
    if values is None:
        return list(DEFAULT_ALPHABET)
    chars = [str(v) for v in values]
    return chars if chars else list(DEFAULT_ALPHABET)


# ---------------------------------------------------------------------------
# Per-shape enumerators — each yields input strings lazily
# ---------------------------------------------------------------------------


def _enum_array(max_n: int, values: Optional[Sequence]):
    """All sequences of length 0..max_n: 'len' line then space-joined values."""
    vals = _values(values)
    for length in range(max_n + 1):
        for seq in itertools.product(vals, repeat=length):
            body = " ".join(str(v) for v in seq)
            yield f"{length}\n{body}" if body else f"{length}\n"


def _enum_permutation(max_n: int):
    """All permutations of 1..n for n in 0..max_n: 'n' then one value per line."""
    for n in range(max_n + 1):
        for perm in itertools.permutations(range(1, n + 1)):
            lines = [str(n)] + [str(x) for x in perm]
            yield "\n".join(lines)


def _enum_string(max_n: int, values: Optional[Sequence]):
    """All strings of length 0..max_n over the alphabet."""
    alpha = _alphabet(values)
    for length in range(max_n + 1):
        for combo in itertools.product(alpha, repeat=length):
            yield "".join(combo)


def _pruefer_to_edges(seq: Sequence[int], n: int):
    """Decode a Pruefer sequence (over labels 1..n) into a tree's n-1 edges."""
    # - standard Pruefer decoding: repeatedly connect the smallest leaf to the
    #   next sequence entry, then connect the final two remaining labels.
    degree = [1] * (n + 1)  # 1-indexed; index 0 unused
    for label in seq:
        degree[label] += 1
    edges = []
    for label in seq:
        # smallest leaf (degree 1) not yet used
        for leaf in range(1, n + 1):
            if degree[leaf] == 1:
                edges.append((leaf, label))
                degree[leaf] -= 1
                degree[label] -= 1
                break
    # two labels of degree 1 remain
    remaining = [v for v in range(1, n + 1) if degree[v] == 1]
    edges.append((remaining[0], remaining[1]))
    return edges


def _enum_tree(max_n: int):
    """All labelled trees on 1..max_n nodes, rendered as n then the edges."""
    for n in range(1, max_n + 1):
        if n == 1:
            yield "1"
            continue
        if n == 2:
            yield "2\n1 2"
            continue
        # Cayley: n^(n-2) trees, one per Pruefer sequence of length n-2.
        for seq in itertools.product(range(1, n + 1), repeat=n - 2):
            edges = _pruefer_to_edges(seq, n)
            lines = [str(n)] + [f"{u} {v}" for u, v in edges]
            yield "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _iter_for(shape: str, max_n: int, values: Optional[Sequence]):
    """Pick the right enumerator generator for a shape (or raise)."""
    if max_n < 0:
        raise UserError("enumerate: max_n must be >= 0.")
    if shape in ("array", "ints"):
        return _enum_array(max_n, values)
    if shape == "permutation":
        return _enum_permutation(max_n)
    if shape == "string":
        return _enum_string(max_n, values)
    if shape == "tree":
        return _enum_tree(max_n)
    raise UserError(
        f"enumerate: shape '{shape}' is not exhaustively enumerable.",
        hint="Supported: array/ints, permutation, string, tree.",
    )


def enumerate_for(shape: str, max_n: int, values: Optional[Sequence], cap: int) -> List[str]:
    """Every input string for `shape` up to `max_n`, truncated silently at `cap`."""
    out: List[str] = []
    if cap <= 0:
        return out
    for text in _iter_for(shape, max_n, values):
        out.append(text)
        if len(out) >= cap:
            break
    return out


def count_estimate(shape: str, max_n: int, values: Optional[Sequence]) -> int:
    """The total (uncapped) number of inputs `enumerate_for` would produce."""
    if max_n < 0:
        raise UserError("enumerate: max_n must be >= 0.")
    if shape in ("array", "ints"):
        k = len(_values(values))
        # sum over length 0..max_n of k**length (geometric series)
        return sum(k**length for length in range(max_n + 1))
    if shape == "permutation":
        return sum(math.factorial(n) for n in range(max_n + 1))
    if shape == "string":
        k = len(_alphabet(values))
        return sum(k**length for length in range(max_n + 1))
    if shape == "tree":
        # Cayley: n**(n-2) labelled trees on n nodes (n=1 and n=2 give 1 each).
        total = 0
        for n in range(1, max_n + 1):
            total += 1 if n <= 2 else n ** (n - 2)
        return total
    raise UserError(
        f"enumerate: shape '{shape}' is not exhaustively enumerable.",
        hint="Supported: array/ints, permutation, string, tree.",
    )
