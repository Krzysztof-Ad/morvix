# Infer an input format from sample files, honestly (Section 13).
#
# Given a few real inputs, learn their SHAPE and hand back a Schema plus a draft
# generator the user edits. This is the on-ramp for "I have some sample tests but
# no generator". It is deliberately conservative: it states what it saw, flags
# where it extrapolated, and NEVER claims correctness.
#
# Critically, inference NEVER runs a program and NEVER computes an answer. It
# only reads input text. The drafted generator carries an UNVERIFIED header and
# expected answers still come only from gen --expected.

from dataclasses import dataclass, field
from typing import List, Optional

from morvix.schema import Schema, classify, merge, render_generator

# Below this many samples, ranges are weak evidence; we say so out loud.
LOW_SAMPLE_THRESHOLD = 3


@dataclass
class InferenceResult:
    """The outcome of inferring a format: the merged Schema plus honest notes."""

    schema: Schema
    notes: List[str] = field(default_factory=list)  # caveats to show the user
    sample_count: int = 0


def infer_schema(samples: List[str]) -> InferenceResult:
    """Fold sample input strings into one Schema, recording honest caveats.

    Never runs anything; just classifies and merges text. The returned schema's
    integer ranges come straight from the samples - they may be too narrow.
    """
    grids = [classify(s) for s in samples if s != ""]
    schema = merge(grids)
    schema.samples = len(grids)
    notes = _build_notes(schema, len(grids))
    schema.notes = list(notes)
    return InferenceResult(schema=schema, notes=notes, sample_count=len(grids))


def _build_notes(schema: Schema, n: int) -> List[str]:
    """The plain-English caveats that ride with an inference result."""
    notes: List[str] = []
    notes.append("DRAFT of input shape, not a verified spec.")
    if n == 0:
        notes.append("No usable samples were given; the schema is empty.")
        return notes
    if n < LOW_SAMPLE_THRESHOLD:
        notes.append(
            "Only %d sample(s) seen - integer ranges are guesses and likely too narrow." % n
        )
    if schema.repeat_ref is not None:
        notes.append(
            "Detected a count-driven body: the integer at line %d "
            "appears to set how many trailing lines follow." % (schema.repeat_ref[0] + 1)
        )
    elif schema.repeat_line is not None:
        notes.append(
            "The number of trailing lines varied but no count integer matched it; "
            "the repeat count in the draft is a guess (see the TODO)."
        )
    # Flag single-value integer ranges as extrapolation candidates.
    if _has_degenerate_ranges(schema):
        notes.append(
            "Some integers were seen with a single value only; the draft widens them "
            "and marks each with a TODO - check the real bounds."
        )
    return notes


def _has_degenerate_ranges(schema: Schema) -> bool:
    """True if any int token had only one observed value (lo == hi)."""
    all_lines = list(schema.lines)
    if schema.repeat_line is not None:
        all_lines.append(schema.repeat_line)
    for line in all_lines:
        for tok in line.tokens:
            if tok.kind == "int" and tok.lo is not None and tok.lo == tok.hi:
                return True
    return False


def report_inference(ctx, result: InferenceResult) -> None:
    """Print the honest caveats for an inference result through the messenger.

    Always leads with the standing disclaimer. This never asserts an answer or
    even a correct format - only what the samples looked like.
    """
    msg = ctx.messenger
    if result.sample_count == 0:
        msg.warning(
            "Nothing to infer from.",
            hint="Pass one or more sample input files: gen --infer sample1.txt sample2.txt",
        )
        return
    msg.info(
        "Inferred an input shape from %d sample(s). This is a DRAFT of input "
        "shape, not a verified spec." % result.sample_count
    )
    for note in result.notes:
        if note.startswith("DRAFT of input shape"):
            continue  # already said in the headline
        msg.plain("  - " + note)
    msg.info("Answers still come only from gen --expected running your solution.")


def render_draft(result: InferenceResult, name: str = "gen") -> str:
    """The DRAFT generator source for an inference result (a thin pass-through)."""
    return render_generator(result.schema, name)


def try_write_grammar(result: InferenceResult, name: str = "gram") -> Optional[str]:
    """Best-effort: render the inferred schema as a starter GRAMMAR source string.

    Returns the grammar source, or None when the shape is too irregular to map
    cleanly (the caller falls back to the Python draft). Like everything here it
    asserts SHAPE only and never an answer.
    """
    schema = result.schema
    # We only attempt the clean, common case: a single leading count line whose
    # value drives a run of equally-shaped trailing lines (n then n ...).
    if schema.repeat_line is None or schema.repeat_ref is None:
        return None
    if schema.repeat_ref[0] != 0 or len(schema.lines) != 1:
        return None
    head = schema.lines[0]
    if len(head.tokens) != 1 or head.tokens[0].kind != "int":
        return None
    body = schema.repeat_line
    if not body.tokens or any(t.kind not in ("int", "float") for t in body.tokens):
        return None

    n_tok = head.tokens[0]
    nlo = n_tok.lo if n_tok.lo is not None else 1
    nhi = n_tok.hi if n_tok.hi is not None else 100
    if nlo == nhi:
        nhi = nlo + 1  # avoid a degenerate range in the draft

    body_terms = []
    for tok in body.tokens:
        lo = tok.lo if tok.lo is not None else 0
        hi = tok.hi if tok.hi is not None else 1000000
        if lo == hi:
            hi = lo + 1
        body_terms.append("int(%d..%d)" % (lo, hi))
    body_expr = " ".join(body_terms)

    lines = [
        "# UNVERIFIED DRAFT grammar (from gen --infer --as-grammar).",
        "# A draft of input SHAPE, not a verified spec. Fix the ranges, then run",
        "# gen --grammar generators/%s.gram --count 1000 and gen --expected." % name,
        "#",
        "# n, then n line(s) of the body shown below.",
        'start: int(%d..%d) as n "\\n" repeat(n) { %s "\\n" }' % (nlo, nhi, body_expr),
        "",
    ]
    return "\n".join(lines)
