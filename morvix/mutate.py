# The one mutation engine: turn existing inputs into new candidate inputs
# (Section 13).
#
# Both the --mutate corpus driver and the diversity-guided fuzzer derive new
# inputs from old ones, so there is exactly ONE library of mutation operators -
# here. An operator takes (rng, text, schema) and returns a mutated text; it
# tokenizes via schema.tokenize_lines so it agrees with everyone else on "what a
# token is". When a Schema is known, operators are structure-aware: after editing
# they REPAIR a leading count so 'n then n numbers' stays consistent.
#
# Mutation produces INPUTS ONLY. No operator reads, writes, or asserts an answer.

import random
from typing import Callable, Dict, List, Optional

from morvix.schema import Schema, classify_token, tokenize_lines

# How a count-driven input is held together: the first integer token in the
# whole input is treated as the element count when a schema marks one. We repair
# THAT token after structural edits so the harness stays well-formed.


# --- low-level helpers -------------------------------------------------------


def _render(lines: List[List[str]]) -> str:
    """Re-join a token grid back into input text (one line per row)."""
    return "\n".join(" ".join(row) for row in lines)


def _all_int_positions(lines: List[List[str]]):
    """Yield (row, col) of every integer token in the grid."""
    for r, row in enumerate(lines):
        for c, tok in enumerate(row):
            if classify_token(tok) == "int":
                yield r, c


def _count_ref(schema: Optional[Schema]):
    """The (row, col) of the count token this schema threads, or None.

    A fixed-line schema with a variable data line, or a repeat schema, both name
    the integer that drives the body size; we surface it as a grid coordinate.
    """
    if schema is None:
        return None
    if schema.repeat_ref is not None:
        return tuple(schema.repeat_ref)
    return None


# --- operators ---------------------------------------------------------------
# Each is (rng, text, schema) -> text. They never touch answers.


def op_tweak_int(rng: random.Random, text: str, schema: Optional[Schema] = None) -> str:
    """Nudge one random integer token up or down by a small delta."""
    lines = tokenize_lines(text)
    ints = list(_all_int_positions(lines))
    if not ints:
        return text
    r, c = rng.choice(ints)
    delta = rng.choice([-10, -2, -1, 1, 2, 10])
    lines[r][c] = str(int(lines[r][c]) + delta)
    return _repair_count(_render(lines), schema)


def op_extreme_int(rng: random.Random, text: str, schema: Optional[Schema] = None) -> str:
    """Replace one integer token with an edge value (0, 1, -1, or a big number)."""
    lines = tokenize_lines(text)
    ints = list(_all_int_positions(lines))
    if not ints:
        return text
    r, c = rng.choice(ints)
    lines[r][c] = str(rng.choice([0, 1, -1, 2**31 - 1, -(2**31)]))
    return _repair_count(_render(lines), schema)


def op_dup_token(rng: random.Random, text: str, schema: Optional[Schema] = None) -> str:
    """Duplicate one token in place, lengthening a line (count is repaired)."""
    lines = tokenize_lines(text)
    nonempty = [r for r, row in enumerate(lines) if row]
    if not nonempty:
        return text
    r = rng.choice(nonempty)
    c = rng.randrange(len(lines[r]))
    lines[r].insert(c, lines[r][c])
    return _repair_count(_render(lines), schema)


def op_drop_token(rng: random.Random, text: str, schema: Optional[Schema] = None) -> str:
    """Drop one token, shortening a line (count is repaired)."""
    lines = tokenize_lines(text)
    nonempty = [r for r, row in enumerate(lines) if row]
    if not nonempty:
        return text
    r = rng.choice(nonempty)
    if len(lines[r]) <= 1 and len(nonempty) == 1:
        return text
    c = rng.randrange(len(lines[r]))
    del lines[r][c]
    return _repair_count(_render(lines), schema)


def op_dup_line(rng: random.Random, text: str, schema: Optional[Schema] = None) -> str:
    """Duplicate a whole line (a repeated body element); repair any count."""
    lines = tokenize_lines(text)
    if not lines:
        return text
    r = rng.randrange(len(lines))
    lines.insert(r, list(lines[r]))
    return _repair_count(_render(lines), schema)


def op_swap_tokens(rng: random.Random, text: str, schema: Optional[Schema] = None) -> str:
    """Swap two tokens on one line - reorders without changing the count."""
    lines = tokenize_lines(text)
    candidates = [r for r, row in enumerate(lines) if len(row) >= 2]
    if not candidates:
        return text
    r = rng.choice(candidates)
    i, j = rng.sample(range(len(lines[r])), 2)
    lines[r][i], lines[r][j] = lines[r][j], lines[r][i]
    return _render(lines)


def op_negate_int(rng: random.Random, text: str, schema: Optional[Schema] = None) -> str:
    """Flip the sign of one integer token."""
    lines = tokenize_lines(text)
    ints = list(_all_int_positions(lines))
    if not ints:
        return text
    r, c = rng.choice(ints)
    lines[r][c] = str(-int(lines[r][c]))
    return _repair_count(_render(lines), schema)


OPERATORS: Dict[str, Callable] = {
    "tweak_int": op_tweak_int,
    "extreme_int": op_extreme_int,
    "dup_token": op_dup_token,
    "drop_token": op_drop_token,
    "dup_line": op_dup_line,
    "swap_tokens": op_swap_tokens,
    "negate_int": op_negate_int,
}

# A sensible default mix when the user does not name operators.
DEFAULT_OPS: List[str] = [
    "tweak_int",
    "extreme_int",
    "dup_token",
    "drop_token",
    "swap_tokens",
    "negate_int",
]


def list_operators() -> List[str]:
    """The names of every available mutation operator, sorted."""
    return sorted(OPERATORS)


# --- count repair: keep 'n then n ...' inputs consistent ---------------------


def _repair_count(text: str, schema: Optional[Schema]) -> str:
    """If the schema threads a count token, rewrite it to match the real body.

    Without a schema this is a no-op, so structure-blind mutation just returns
    edited text. With a schema, the leading count is fixed so the harness reads
    a well-formed input. This never inspects or touches an answer.
    """
    ref = _count_ref(schema)
    if ref is None or schema is None:
        return text
    lines = tokenize_lines(text)
    r, c = ref
    if r >= len(lines) or c >= len(lines[r]):
        return text
    real = _body_size(lines, schema)
    if real is None:
        return text
    lines[r][c] = str(real)
    return _render(lines)


def _body_size(lines: List[List[str]], schema: Schema):
    """How many body elements the count should report, given the schema.

    - A repeat-line schema with a fixed prefix: the number of trailing lines.
    - Otherwise: the token count of the single data line after the count.
    """
    if schema is None:
        return None
    if schema.repeat_line is not None and schema.repeat_ref is not None:
        prefix_len = len(schema.lines)
        return max(0, len(lines) - prefix_len)
    return None


def count_consistent(text: str, schema: Optional[Schema]) -> bool:
    """Does the input's declared count match its real body size?

    True when there is no count to check (no schema or no count ref). False on a
    classic off-by-one. This only looks at INPUT structure, never an answer.
    """
    ref = _count_ref(schema)
    if ref is None or schema is None:
        return True
    lines = tokenize_lines(text)
    r, c = ref
    if r >= len(lines) or c >= len(lines[r]):
        return False
    declared_tok = lines[r][c]
    if classify_token(declared_tok) != "int":
        return False
    declared = int(declared_tok)
    real = _body_size(lines, schema)
    if real is None:
        return True
    return declared == real


# --- the public mutation entry points ----------------------------------------


def mutate_once(
    rng: random.Random,
    text: str,
    ops: Optional[List[str]] = None,
    schema: Optional[Schema] = None,
) -> str:
    """Apply one randomly chosen operator from 'ops' to 'text'.

    Structure-aware when a schema is given (a leading count is repaired after the
    edit). Unknown operator names are ignored. Returns the mutated text.
    """
    names = ops if ops else DEFAULT_OPS
    usable = [n for n in names if n in OPERATORS]
    if not usable:
        return text
    name = rng.choice(usable)
    return OPERATORS[name](rng, text, schema)


def crossover(rng: random.Random, a: str, b: str) -> str:
    """Splice two inputs: take a line prefix from 'a' and the suffix from 'b'.

    A cheap structural recombination for the fuzzer's corpus. It only moves
    INPUT bytes around; it never produces or copies an answer.
    """
    la = tokenize_lines(a)
    lb = tokenize_lines(b)
    if not la:
        return b
    if not lb:
        return a
    cut_a = rng.randint(0, len(la))
    cut_b = rng.randint(0, len(lb))
    combined = la[:cut_a] + lb[cut_b:]
    return _render(combined)
