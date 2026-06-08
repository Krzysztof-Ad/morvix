# Behavior bucketing for diversity-guided fuzzing (Section 13).
#
# Fuzzing keeps an input only when it makes the solution behave in an observably
# NEW way. To decide "new", we map each run's observation to a coarse bucket key:
# same behavior -> same key, meaningfully different behavior -> different key.
# Bucketing is deliberately COARSE - it groups by regime (crash vs clean, short
# vs long output, fast vs slow) rather than raw numbers, so trivial jitter in
# timing or a one-byte output change does not look like a fresh behavior.
#
# This module is INPUTS-ONLY. A behavior key is a steering heuristic that picks
# which inputs look interesting; it never reads, computes, or asserts an expected
# answer. The run-driver (gen_fuzz) is wired separately; this is the pure part.
#
# API:
#   behavior_key(obs: dict, limits: dict) -> tuple
#   is_novel(key, seen: set) -> bool
#
# obs is a small normalised dict produced by the run-driver:
#   {"output": bytes, "exit": int|None, "signal": str|None,
#    "timed_out": bool, "wall": float, "mem_kb": int|None}
# limits is {"wall": float|None, "mem_kb": int|None} (the per-case limits), used
# only to scale the timing/memory regimes relative to the budget.

from typing import Optional

# Output-length buckets: 0, then geometric decades. A change of output by orders
# of magnitude is "new behavior"; a few bytes either way is not.
_LEN_EDGES = (0, 1, 10, 100, 1_000, 10_000, 100_000, 1_000_000)

# Distinct-token-count buckets: how varied the output is, coarsely.
_TOK_EDGES = (0, 1, 2, 5, 10, 50, 200, 1_000)


# ---------------------------------------------------------------------------
# Coarse bucketing helpers
# ---------------------------------------------------------------------------


def _bucket(value: int, edges) -> int:
    """Index of the highest edge <= value; a monotone, coarse bucket id."""
    idx = 0
    for i, edge in enumerate(edges):
        if value >= edge:
            idx = i
        else:
            break
    return idx


def _status_class(obs: dict) -> tuple:
    """The exit/signal/timeout regime - the dominant axis of behavior.

    Ordered most-specific-first so a crash never collapses into a clean run.
    """
    if obs.get("timed_out"):
        return ("timeout",)
    signal = obs.get("signal")
    if signal:
        return ("signal", str(signal))
    exit_code = obs.get("exit")
    if exit_code is None:
        # killed without a signal we captured - treat as its own regime
        return ("killed",)
    if exit_code == 0:
        return ("ok",)
    return ("exit", int(exit_code))


def _output_buckets(output) -> tuple:
    """(length-bucket, distinct-token-bucket) for the observable output."""
    data = output if isinstance(output, (bytes, bytearray)) else b""
    length = len(data)
    distinct = len(set(data.split())) if data else 0
    return (_bucket(length, _LEN_EDGES), _bucket(distinct, _TOK_EDGES))


def _ratio_regime(value: Optional[float], limit: Optional[float], edges) -> int:
    """Bucket a value as a FRACTION of its limit (so regimes scale to budget).

    Returns -1 when there is nothing measurable (no value, or no/zero limit) so
    timing/memory simply does not contribute - it never invents a distinction.
    """
    if value is None or not limit or limit <= 0:
        return -1
    return _bucket(int((value / limit) * 1000), edges)


# Fraction-of-limit edges in parts-per-thousand: idle, low, mid, high, near-limit.
_RATIO_EDGES = (0, 100, 250, 500, 750, 900, 1_000)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def behavior_key(obs: dict, limits: dict) -> tuple:
    """A coarse, hashable bucket for one observation of the solution.

    Same observable behavior -> same key; a meaningfully different behavior ->
    a different key. Buckets, never raw values, so timing/memory jitter and tiny
    output edits do not register as novelty. Carries no expected answer.
    """
    limits = limits or {}
    status = _status_class(obs)
    out_len, out_tok = _output_buckets(obs.get("output"))
    wall_regime = _ratio_regime(obs.get("wall"), limits.get("wall"), _RATIO_EDGES)
    mem_regime = _ratio_regime(obs.get("mem_kb"), limits.get("mem_kb"), _RATIO_EDGES)
    return (status, out_len, out_tok, wall_regime, mem_regime)


def is_novel(key, seen: set) -> bool:
    """True if KEY is a behavior not yet in SEEN; records it as a side effect.

    The caller keeps an input exactly when this returns True, so the seen-set is
    updated here to make the keep-or-skip decision atomic.
    """
    if key in seen:
        return False
    seen.add(key)
    return True
