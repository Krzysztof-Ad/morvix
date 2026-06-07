# Value distributions + a difficulty dial for random generation (Section 13).
#
# The built-in shapes draw their numbers uniformly by default, which is fine for
# a smoke test but rarely the input that breaks a solution. Two orthogonal knobs
# change *how* a shape's values are drawn and *how hard* the overall input is:
#
#   --dist NAME        the shape of the value cloud (uniform, zipf, gaussian, ...)
#   --difficulty LEVEL easy|medium|hard|adversarial, or a number in 0..1
#
# This module is the home of both. It produces VALUES and INPUT-SHAPING params
# only: it never runs the solution and never reads or writes an expected answer.
# `difficulty_params` returns a dict of overrides for a shape's params (a bigger
# n, a tighter/duplicate-heavy value range, and at the top end the name of an
# adversarial shape to retarget to) - all of which describe the input, not the
# answer.

import math
import random
from typing import List

# Adversarial shapes a high difficulty can retarget a base shape onto. These are
# referenced by NAME only (the adversaries module registers them into
# shapes.SHAPES); we keep the mapping here so difficulty can shape the input
# without importing - and breaking - if adversaries is not present yet.
_ADVERSARIAL_FOR = {
    "ints": "anti_quicksort",
    "array": "anti_quicksort",
    "permutation": "anti_quicksort",
    "string": "kmp_worst",
    "tree": "caterpillar",
    "graph": "anti_dijkstra",
}


# ---------------------------------------------------------------------------
# Distributions - each maps a uniform draw into a value within [lo, hi]
# ---------------------------------------------------------------------------


def _clamp(v, lo, hi):
    """Keep a value inside the inclusive [lo, hi] window (also fixes lo > hi)."""
    if lo > hi:
        lo, hi = hi, lo
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _round_like(v, lo, hi):
    """Return an int when the bounds are integral, else the float as-is."""
    if isinstance(lo, int) and isinstance(hi, int):
        return int(round(v))
    return v


def _uniform(rng, lo, hi, params):
    return rng.uniform(lo, hi)


def _loguniform(rng, lo, hi, params):
    # Draw uniformly in log space so small magnitudes are favoured. Work on the
    # positive offset from lo so a range spanning zero/negatives still behaves.
    span = hi - lo
    if span <= 0:
        return lo
    # +1 keeps log defined at the low end and gives lo a real chance.
    u = rng.uniform(0.0, math.log(span + 1.0))
    return lo + math.exp(u) - 1.0


def _zipf(rng, lo, hi, params):
    # Zipf-like: rank 1 is the most likely, probability ~ 1/rank^s. We map the
    # chosen rank back onto [lo, hi] so low values dominate.
    s = float(params.get("zipf_s", 1.5))
    span = int(hi) - int(lo)
    if span <= 0:
        return lo
    n = span + 1
    # Inverse-CDF style sampling over a truncated harmonic distribution.
    weights = [1.0 / (k**s) for k in range(1, n + 1)]
    total = sum(weights)
    target = rng.uniform(0.0, total)
    acc = 0.0
    rank = n
    for k, w in enumerate(weights, start=1):
        acc += w
        if target <= acc:
            rank = k
            break
    return lo + (rank - 1)


def _gaussian(rng, lo, hi, params):
    # Centre on the midpoint; spread covers the range in ~6 sigma. Out-of-range
    # tails clamp to the edges (so the edges get a little extra mass, on purpose).
    mid = (lo + hi) / 2.0
    sigma = float(params.get("sigma", (hi - lo) / 6.0)) or 1.0
    return rng.gauss(mid, sigma)


def _bimodal(rng, lo, hi, params):
    # Two clusters near the two extremes - the classic "small and large, nothing
    # in the middle" case. Each mode is a tight gaussian by one edge.
    spread = float(params.get("spread", (hi - lo) / 20.0)) or 1.0
    centre = lo if rng.random() < 0.5 else hi
    return rng.gauss(centre, spread)


def _clustered(rng, lo, hi, params):
    # A handful of random hot-spots; most draws land exactly on a centre, a few
    # jitter nearby. Values pile up into few distinct ones - rough on hashing/
    # counting code. "jitter" is the chance a draw strays from its centre.
    k = int(params.get("clusters", 4))
    spread = float(params.get("spread", (hi - lo) / 1000.0))
    jitter = float(params.get("jitter", 0.2))
    # Derive stable cluster centres from this rng's own stream so a given seed is
    # reproducible across draws within one sample_many call.
    if "_centres" in params:
        centres = params["_centres"]
    else:
        centres = [_round_like(rng.uniform(lo, hi), lo, hi) for _ in range(max(1, k))]
        params["_centres"] = centres
    centre = rng.choice(centres)
    if spread <= 0 or rng.random() >= jitter:
        return centre
    return rng.gauss(centre, spread)


_DISTS = {
    "uniform": _uniform,
    "loguniform": _loguniform,
    "zipf": _zipf,
    "gaussian": _gaussian,
    "bimodal": _bimodal,
    "clustered": _clustered,
}


# ---------------------------------------------------------------------------
# Public API - sampling
# ---------------------------------------------------------------------------


def list_dists() -> List[str]:
    """The distribution names, in the order they are documented."""
    return ["uniform", "loguniform", "zipf", "gaussian", "bimodal", "clustered"]


def sample(rng: random.Random, lo, hi, dist: str = "uniform", params=None):
    """Draw one value within [lo, hi] from the named distribution.

    Every distribution clamps into [lo, hi]; integer bounds yield an int.
    """
    if params is None:
        params = {}
    if dist not in _DISTS:
        known = ", ".join(list_dists())
        raise ValueError(f"Unknown distribution '{dist}'. Known: {known}.")
    raw = _DISTS[dist](rng, lo, hi, params)
    return _round_like(_clamp(raw, lo, hi), lo, hi)


def sample_many(rng: random.Random, n: int, lo, hi, dist: str = "uniform", params=None):
    """Draw n values within [lo, hi] from the named distribution."""
    if params is None:
        params = {}
    # Copy so per-call caches (e.g. clustered centres) do not leak back to the
    # caller's dict, while staying reproducible within this call.
    local = dict(params)
    return [sample(rng, lo, hi, dist, local) for _ in range(int(n))]


# ---------------------------------------------------------------------------
# Public API - difficulty
# ---------------------------------------------------------------------------

_LEVELS = {
    "easy": 0.15,
    "medium": 0.5,
    "hard": 0.85,
    "adversarial": 1.0,
}


def parse_difficulty(level) -> float:
    """Map a difficulty level to a float in [0, 1].

    Accepts the named rungs easy|medium|hard|adversarial, or a numeric string
    like "0.7". Anything out of range is clamped; adversarial is exactly 1.0.
    """
    if isinstance(level, (int, float)):
        return _clamp01(float(level))
    if level is None:
        return 0.0
    key = str(level).strip().lower()
    if key in _LEVELS:
        return _LEVELS[key]
    try:
        return _clamp01(float(key))
    except ValueError as e:
        names = ", ".join(_LEVELS)
        raise ValueError(f"Bad difficulty '{level}'. Use one of {names}, or a number 0..1.") from e


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def difficulty_params(shape: str, d) -> dict:
    """Input-shaping overrides for a shape at difficulty d (a float or a level).

    Higher d means: a larger structure (bigger n / longer arrays), a tighter and
    more duplicate-heavy value range (to stress hashing/sorting), a heavier-tailed
    distribution, and - at the very top - retargeting onto a named adversarial
    shape via the "shape" key. Returns INPUT params only; it never touches answers.
    """
    d = parse_difficulty(d)
    out: dict = {}

    # Size scales geometrically from a small floor to a large ceiling.
    lo_n, hi_n = 10, 100_000
    n = int(round(lo_n * (hi_n / lo_n) ** d))
    out["count"] = n
    out["min_n"] = n
    out["max_n"] = n
    out["n"] = n
    out["length"] = n

    # Harder inputs lean on heavier-tailed value clouds.
    if d >= 0.85:
        out["dist"] = "zipf"
    elif d >= 0.5:
        out["dist"] = "loguniform"

    # Tighten the value range as difficulty rises so values collide more: at
    # d=0 the full default range, shrinking toward a small window at d=1.
    span = max(1, int(round(1_000_000 * (1.0 - 0.999 * d))))
    out["lo"] = 0
    out["hi"] = span

    # At the very top, retarget onto a worst-case shape if one exists for this
    # base shape. This sets a *shape name* (an input source), never an answer.
    if d >= 1.0:
        adversary = _ADVERSARIAL_FOR.get(shape)
        if adversary is not None:
            out["shape"] = adversary

    return out
