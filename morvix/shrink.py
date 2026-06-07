# Shrinking: turn a big failing input into a small reproducer (Section 13).
#
# A failure found by stress/crash/fuzz is often a huge random input. Shrinking
# (delta-debugging) repeatedly removes and reduces parts of the input, keeping
# any change that STILL triggers the same failure, until a minimal reproducer
# remains - far easier to read and debug.
#
# This module is pure mechanism: it takes a `predicate(input_bytes) -> bool`
# ("does this input still fail the same way?") supplied by the caller, who owns
# the actual program runs. Shrinking touches inputs only; the expectation is
# re-derived afterwards from the same authority (the oracle/solution).

from dataclasses import dataclass


class FailureKind:
    DISAGREE = "disagree"  # solution vs oracle differ
    CRASH = "crash"  # terminating signal
    HANG = "hang"  # timed out
    ERROR = "error"  # nonzero clean exit
    WRONG = "wrong"  # output != expected


@dataclass
class Failure:
    kind: str
    detail: str = ""


def shrink_failure(predicate, data: bytes, budget: int = 2000, on_progress=None) -> bytes:
    """Return a minimal input (<= data) for which predicate(...) is still True.

    `budget` caps how many predicate calls (program runs) we spend. Best-effort:
    we never return something the predicate rejects, and never grow the input.
    """
    text = data.decode("utf-8", "replace")
    calls = [0]

    def fails(candidate: str) -> bool:
        if calls[0] >= budget or candidate == "" or len(candidate) >= len(text) + 1:
            return False
        calls[0] += 1
        ok = bool(predicate(candidate.encode("utf-8")))
        if ok and on_progress:
            on_progress(candidate)
        return ok

    best = text
    changed = True
    while changed and calls[0] < budget:
        changed = False
        for step in (_drop_lines, _repair_counts, _drop_tokens, _reduce_numbers):
            cand = step(best, fails)
            if cand is not None and cand != best and len(cand) < len(best):
                best = cand
                changed = True
    return best.encode("utf-8")


# --- delta-debugging passes ---------------------------------------------------


def _ddmin(units, join, fails, best_join):
    """Classic ddmin over a list of units: find a minimal subset that still fails."""
    n = 2
    units = list(units)
    while len(units) >= 2:
        chunk = max(1, len(units) // n)
        removed_any = False
        i = 0
        while i < len(units):
            candidate = units[:i] + units[i + chunk :]
            if candidate and fails(join(candidate)):
                units = candidate
                n = max(n - 1, 2)
                removed_any = True
            else:
                i += chunk
        if not removed_any:
            if n >= len(units):
                break
            n = min(len(units), n * 2)
    return join(units)


def _drop_lines(text, fails):
    lines = text.split("\n")
    if len(lines) < 2:
        return None
    return _ddmin(lines, lambda u: "\n".join(u), fails, text)


def _drop_tokens(text, fails):
    # Per line, try ddmin over whitespace tokens (helps "a b c d" rows).
    lines = text.split("\n")
    out = []
    changed = False
    for line in lines:
        toks = line.split()
        if len(toks) >= 2:
            shrunk = _ddmin(toks, lambda u: " ".join(u), fails, line)
            if shrunk != line:
                changed = True
            out.append(shrunk)
        else:
            out.append(line)
    return "\n".join(out) if changed else None


def _repair_counts(text, fails):
    # The "N then N items" pattern: a bare integer line followed by a line of N
    # whitespace tokens. Greedily drop trailing items while fixing the count.
    lines = text.split("\n")
    changed = False
    for i in range(len(lines) - 1):
        head = lines[i].strip()
        if not _is_int(head):
            continue
        items = lines[i + 1].split()
        if int(head) != len(items) or len(items) < 1:
            continue
        while len(items) > 0:
            cand_items = items[:-1]
            cand_lines = list(lines)
            cand_lines[i] = str(len(cand_items))
            cand_lines[i + 1] = " ".join(cand_items)
            if fails("\n".join(cand_lines)):
                items = cand_items
                lines = cand_lines
                changed = True
            else:
                break
    return "\n".join(lines) if changed else None


def _reduce_numbers(text, fails):
    # Shrink each integer toward 0 (try 0, then halve repeatedly) while failing.
    import re

    tokens = list(re.finditer(r"-?\d+", text))
    if not tokens:
        return None
    result = text
    changed = False
    # Walk right-to-left so earlier match spans stay valid as we splice.
    for m in reversed(tokens):
        val = int(m.group())
        if val == 0:
            continue
        start, end = m.start(), m.end()
        for target in _reduction_targets(val):
            cand = result[:start] + str(target) + result[end:]
            if fails(cand):
                result = cand
                changed = True
                break
    return result if changed else None


def _reduction_targets(val):
    # Candidate smaller magnitudes to try, smallest first.
    seen = []
    for t in (0, 1, val // 2):
        if abs(t) < abs(val) and t not in seen:
            seen.append(t)
    return seen


def _is_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False
