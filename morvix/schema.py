# Inferred input schema: a tokenizer plus a learned "what does this input look
# like" model (Section 13).
#
# This is the data side of format inference. It does three things and nothing
# more: it tokenizes input text into a per-line list of tokens; it folds several
# sample inputs into one Schema describing each line's tokens and their integer
# ranges; and it renders that Schema into a DRAFT generator the user edits.
#
# A Schema asserts the input's SHAPE, never its meaning, and it NEVER computes
# or stores an answer. The rendered generator is an unverified starting point -
# expected answers still come only from gen --expected running the solution.
#
# The tokenizer here is the single source of truth for "what a token is"; mutate
# and the oracle-free drivers all reuse tokenize_lines so they agree.

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

# An integer (optionally signed). Anything that is not a pure integer token is
# classified by kind below, never split further.
_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_WORD_RE = re.compile(r"^[A-Za-z_]\w*$")


# --- tokenizer ---------------------------------------------------------------


def tokenize_lines(text: str) -> List[List[str]]:
    """Split input text into a list of per-line token lists.

    Lines are split on '\n'; tokens within a line are split on runs of
    whitespace. A trailing newline does not produce a spurious empty line, but
    interior blank lines are preserved as empty token lists so structure (e.g. a
    blank separator line) is not silently dropped.
    """
    if text == "":
        return []
    body = text[:-1] if text.endswith("\n") else text
    lines = body.split("\n")
    return [ln.split() for ln in lines]


def classify_token(tok: str) -> str:
    """The kind of one token: 'int', 'float', 'word' or 'other'."""
    if _INT_RE.match(tok):
        return "int"
    if _FLOAT_RE.match(tok):
        return "float"
    if _WORD_RE.match(tok):
        return "word"
    return "other"


# --- the schema model --------------------------------------------------------


@dataclass
class TokenSpec:
    """One token position: its kind and (for ints) the observed value range."""

    kind: str  # int | float | word | other
    lo: Optional[int] = None  # min observed integer value (kind == int)
    hi: Optional[int] = None  # max observed integer value (kind == int)
    extrapolated: bool = False  # True when lo/hi were widened past what we saw

    def to_dict(self) -> dict:
        d: dict = {"kind": self.kind}
        for key in ("lo", "hi"):
            v = getattr(self, key)
            if v is not None:
                d[key] = v
        if self.extrapolated:
            d["extrapolated"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TokenSpec":
        return cls(
            kind=d["kind"],
            lo=d.get("lo"),
            hi=d.get("hi"),
            extrapolated=d.get("extrapolated", False),
        )


@dataclass
class LineSpec:
    """One line of the input: its token specs, and whether the token COUNT was
    constant across samples or driven by an earlier value."""

    tokens: List[TokenSpec] = field(default_factory=list)
    count_fixed: bool = True  # the number of tokens was the same in every sample
    # When the token count varied AND it equals a single integer read earlier,
    # we record (line, col) of that integer - the classic "n then n numbers".
    count_ref: Optional[List[int]] = None  # [line_index, col_index] or None

    def to_dict(self) -> dict:
        d = {"tokens": [t.to_dict() for t in self.tokens], "count_fixed": self.count_fixed}
        if self.count_ref is not None:
            d["count_ref"] = list(self.count_ref)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LineSpec":
        return cls(
            tokens=[TokenSpec.from_dict(t) for t in d.get("tokens", [])],
            count_fixed=d.get("count_fixed", True),
            count_ref=d.get("count_ref"),
        )


@dataclass
class Schema:
    """A folded model of several sample inputs.

    'lines' describes the leading fixed-structure lines. When the inputs had a
    variable number of trailing lines all of the same shape, that shape lives in
    'repeat_line' and 'repeat_ref' points at the integer that drives the count.
    'notes' carries honest caveats (extrapolation, low sample size) for display.
    """

    lines: List[LineSpec] = field(default_factory=list)
    repeat_line: Optional[LineSpec] = None  # shape of a variable run of trailing lines
    repeat_ref: Optional[List[int]] = None  # [line, col] integer driving the line count
    samples: int = 0  # how many inputs were folded in
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "lines": [ln.to_dict() for ln in self.lines],
            "samples": self.samples,
            "notes": list(self.notes),
        }
        if self.repeat_line is not None:
            d["repeat_line"] = self.repeat_line.to_dict()
        if self.repeat_ref is not None:
            d["repeat_ref"] = list(self.repeat_ref)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Schema":
        return cls(
            lines=[LineSpec.from_dict(x) for x in d.get("lines", [])],
            repeat_line=(
                LineSpec.from_dict(d["repeat_line"]) if d.get("repeat_line") is not None else None
            ),
            repeat_ref=d.get("repeat_ref"),
            samples=d.get("samples", 0),
            notes=d.get("notes", []),
        )


# --- classification: one sample -> a (lines, token grid) view ----------------


def classify(text: str) -> List[List[TokenSpec]]:
    """Turn one sample into a per-line grid of TokenSpecs (no merging yet).

    Each integer token gets lo == hi == its value so a later merge can widen the
    range; non-integers carry no range.
    """
    grid: List[List[TokenSpec]] = []
    for line in tokenize_lines(text):
        row: List[TokenSpec] = []
        for tok in line:
            kind = classify_token(tok)
            if kind == "int":
                v = int(tok)
                row.append(TokenSpec(kind="int", lo=v, hi=v))
            else:
                row.append(TokenSpec(kind=kind))
        grid.append(row)
    return grid


def _min_opt(x, y):
    return x if y is None else (y if x is None else min(x, y))


def _max_opt(x, y):
    return x if y is None else (y if x is None else max(x, y))


def _merge_token(a: TokenSpec, b: TokenSpec) -> TokenSpec:
    """Fold two token observations at the same position into one spec."""
    if a.kind == b.kind == "int":
        return TokenSpec(
            kind="int",
            lo=_min_opt(a.lo, b.lo),
            hi=_max_opt(a.hi, b.hi),
            extrapolated=a.extrapolated or b.extrapolated,
        )
    # Mixed kinds collapse to the looser one: int+float -> float; anything else
    # that disagrees becomes 'other' (we make no claim about its shape).
    if {a.kind, b.kind} == {"int", "float"}:
        return TokenSpec(kind="float")
    if a.kind == b.kind:
        return TokenSpec(kind=a.kind)
    return TokenSpec(kind="other")


def _merge_line(specs: List[List[TokenSpec]]) -> LineSpec:
    """Fold several observations of ONE line position into a LineSpec."""
    counts = {len(row) for row in specs}
    count_fixed = len(counts) == 1
    width = max(counts) if counts else 0
    tokens: List[TokenSpec] = []
    for col in range(width):
        present = [row[col] for row in specs if col < len(row)]
        if not present:
            continue
        acc = present[0]
        for nxt in present[1:]:
            acc = _merge_token(acc, nxt)
        tokens.append(acc)
    return LineSpec(tokens=tokens, count_fixed=count_fixed)


def merge(grids: List[List[List[TokenSpec]]]) -> Schema:
    """Fold several classified samples into one Schema.

    Strategy, deliberately simple and explainable:
      - Line counts that match across all samples -> fold line-by-line.
      - If samples differ only in their NUMBER of trailing single-shape lines,
        treat the common prefix as fixed and the tail as a repeat block, then
        try to bind the repeat count to an integer read earlier (n-then-n).
    """
    if not grids:
        return Schema(samples=0)
    line_counts = {len(g) for g in grids}

    if len(line_counts) == 1:
        # Same number of lines everywhere: fold each line position directly. The
        # count-driven relationship lives in the variable-line path; a fixed-line
        # corpus has no varying body to bind a count to, so we leave it unbound.
        n_lines = line_counts.pop()
        lines = [_merge_line([g[i] for g in grids]) for i in range(n_lines)]
        return Schema(lines=lines, samples=len(grids))

    # Variable line count: a leading fixed prefix, then a repeated body. We pick
    # the prefix length that lets a prefix integer EXPLAIN the number of trailing
    # lines (the 'n then n lines' relationship). Searching short-to-long means we
    # prefer the smallest prefix that yields a clean count binding; if none does,
    # we fall back to the longest shape-stable prefix.
    min_lines = min(line_counts)
    chosen_len = None
    chosen_ref = None
    for plen in range(min_lines):
        ref = _find_count_ref(grids, plen)
        if ref is not None:
            chosen_len, chosen_ref = plen, ref
            break
    if chosen_len is None:
        # No count explained the body; use the shape-stable leading prefix.
        chosen_len = 0
        for i in range(min_lines):
            if all(_same_shape(g[i], grids[0][i]) for g in grids):
                chosen_len += 1
            else:
                break

    prefix = [_merge_line([g[i] for g in grids]) for i in range(chosen_len)]
    tail_rows = [row for g in grids for row in g[chosen_len:]]
    repeat_line = _merge_line(tail_rows) if tail_rows else None
    schema = Schema(lines=prefix, repeat_line=repeat_line, samples=len(grids))
    if chosen_ref is not None:
        schema.repeat_ref = list(chosen_ref)
    return schema


def _find_count_ref(grids, prefix_len: int):
    """A (line, col) within the first prefix_len lines whose integer value equals
    the number of trailing lines in EVERY sample, or None. This is what detects
    'read n, then n lines'."""
    tail_counts = [len(g) - prefix_len for g in grids]
    if any(t < 0 for t in tail_counts):
        return None
    # Candidate positions: integers present in the prefix of every sample.
    for li in range(prefix_len):
        width = len(grids[0][li]) if li < len(grids[0]) else 0
        for ci in range(width):
            ok = True
            for g, tail in zip(grids, tail_counts):
                if li >= len(g) or ci >= len(g[li]):
                    ok = False
                    break
                tok = g[li][ci]
                if tok.kind != "int" or tok.lo != tail:
                    ok = False
                    break
            if ok:
                return (li, ci)
    return None


def _same_shape(a: List[TokenSpec], b: List[TokenSpec]) -> bool:
    """Two line observations have the same shape if they have the same length
    and the same per-token kinds (treating int and float as compatible)."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        kx = "num" if x.kind in ("int", "float") else x.kind
        ky = "num" if y.kind in ("int", "float") else y.kind
        if kx != ky:
            return False
    return True


# --- rendering a DRAFT generator ---------------------------------------------

# Header carried by every rendered generator: it is a draft of input SHAPE only.
_DRAFT_HEADER = """#!/usr/bin/env python3
# UNVERIFIED DRAFT generator (from gen --infer).
#
# Morvix inferred this input SHAPE from your sample files. It is a STARTING
# POINT, not a verified spec: ranges are guessed from a handful of samples and
# may be too narrow or too wide. Read it, fix the TODOs, then:
#
#   gen --generator generators/{name}.py --count 1000
#   gen --expected            # answers come from your solution, never from here
#
# This file produces INPUTS ONLY. It never computes or asserts an answer.

import random
import sys
"""


def _int_range(tok: TokenSpec) -> str:
    lo = tok.lo if tok.lo is not None else 0
    hi = tok.hi if tok.hi is not None else 1000000
    if lo == hi:
        # Only one value was ever seen; widen a little and flag it as a guess.
        return "rng.randint(%d, %d)  # TODO only one value seen; widen if needed" % (lo, hi)
    return "rng.randint(%d, %d)" % (lo, hi)


def _emit_token(tok: TokenSpec, bind: Optional[str] = None) -> str:
    """A Python expression (as a string) that produces one token's text."""
    if tok.kind == "int":
        expr = _int_range(tok)
    elif tok.kind == "float":
        expr = "round(rng.uniform(0, 1000000), 6)  # TODO float range is a guess"
    elif tok.kind == "word":
        expr = 'rng.choice(["foo", "bar"])  # TODO replace word vocabulary'
    else:
        expr = '"x"  # TODO unknown token kind; replace'
    if bind:
        return "%s = %s" % (bind, expr)
    return expr


def _emit_line(line: LineSpec, indent: str, idx: int) -> List[str]:
    """Render one fixed line into generator statements that append to 'out'."""
    body: List[str] = []
    if not line.tokens:
        body.append('%sout.append("")' % indent)
        return body
    parts = []
    for ci, tok in enumerate(line.tokens):
        var = "v%d_%d" % (idx, ci)
        body.append("%s%s" % (indent, _emit_token(tok, bind=var)))
        parts.append("str(%s)" % var)
    body.append('%sout.append(" ".join([%s]))' % (indent, ", ".join(parts)))
    return body


def render_generator(schema: Schema, name: str = "gen") -> str:
    """Render a Schema into a runnable DRAFT generator SOURCE STRING.

    The output is valid Python a newcomer can read and edit. It carries the
    UNVERIFIED header, prints inputs to stdout parameterized by a seed, and never
    touches an answer.
    """
    base = name[:-3] if name.endswith(".py") else name
    out: List[str] = [_DRAFT_HEADER.format(name=base), "", ""]
    out.append("def build_input(rng):")
    out.append("    out = []")

    # Track which (line, col) integers are bound so a repeat count can reference
    # them by the variable name we emitted.
    count_var = None
    for idx, line in enumerate(schema.lines):
        out.extend(_emit_line(line, "    ", idx))
        if (
            schema.repeat_ref is not None
            and schema.repeat_ref[0] == idx
            and schema.repeat_ref[1] < len(line.tokens)
        ):
            count_var = "v%d_%d" % (idx, schema.repeat_ref[1])

    if schema.repeat_line is not None:
        # A variable run of trailing lines, ideally driven by a read count.
        if count_var is not None:
            out.append("    n = %s  # the count read above drives the trailing lines" % count_var)
        else:
            out.append("    n = rng.randint(1, 100)  # TODO count of repeated lines is a guess")
        out.append("    for _ in range(n):")
        out.extend(_emit_line(schema.repeat_line, "        ", 9999))

    out.append('    return "\\n".join(out) + "\\n"')
    out.append("")
    out.append("")
    out.append("def main():")
    out.append("    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0")
    out.append("    rng = random.Random(seed)")
    out.append("    sys.stdout.write(build_input(rng))")
    out.append("")
    out.append("")
    out.append('if __name__ == "__main__":')
    out.append("    main()")
    out.append("")
    return "\n".join(out)


# --- sidecar (JSON) ----------------------------------------------------------


def save_schema(schema: Schema, path: str) -> None:
    """Write a Schema to a JSON sidecar (used by gen --infer / --mutate)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schema.to_dict(), f, indent=2)
        f.write("\n")


def load_schema(path: str) -> Schema:
    """Load a Schema from a JSON sidecar."""
    with open(path, "r", encoding="utf-8") as f:
        return Schema.from_dict(json.load(f))


# Kept for callers that want the raw dataclass dict without the to_dict trim.
def schema_asdict(schema: Schema) -> Dict:
    return asdict(schema)
