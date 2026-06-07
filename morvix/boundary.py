# Boundary-value analysis: turn declared axes into concrete shape param-dicts.
#
# `gen --boundary` declares one or more axes (via the bound-spec mini-language in
# boundspec.py) and wants a set of inputs that probe the edges of that space. The
# classic technique is boundary-value analysis: for each variable, push it to its
# minimum, maximum and the neighbours of those, while holding the rest at a
# representative value. This module is the pure-logic layer that decides WHICH
# combinations of axis values to emit; the caller feeds each returned dict to a
# shape as its params, so we never touch a solution or an expected answer.
#
# Two outputs:
#   boundary_param_sets(axes, strategy, shape) -> list[dict]
#       The BVA matrix. Three strategies trade coverage for size:
#         one-at-a-time : a baseline, then one variant per (axis, boundary value)
#         corners       : the cartesian product of each axis's lo/hi extremes
#         full          : the cartesian product of all boundary values (capped)
#   structural_extremes(shape, axes) -> list[dict]
#       Shape-level extremes (empty / single / max-sized) derived from a size axis
#       such as n, so a structured shape is exercised at its smallest and largest.
#
# Every returned dict maps axis-name -> value and is ready to pass as shape params.

import itertools
from typing import Dict, List

from morvix.boundspec import Domain, RangeDomain, SetDomain, boundary_values, factor_levels

# Cap on the "full" cartesian product so a few wide axes cannot explode into
# millions of cases. The caller's --max-cases still trims further downstream.
DEFAULT_CAP = 500

# Axis names that a shape treats as "how big is the structure". structural_extremes
# looks for one of these to derive empty/single/max sized variants.
SIZE_NAMES = ("n", "count", "size", "len", "length", "m", "rows")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _baseline(axes: Dict[str, Domain]) -> Dict:
    """One representative value per axis, used as the hold-constant background."""
    # - a range's representative value is its middle factor level; a set's is its
    #   first member. factor_levels already orders levels min/mid/max[/0].
    base = {}
    for name, d in axes.items():
        levels = factor_levels(d)
        if isinstance(d, RangeDomain):
            mid = levels[len(levels) // 2] if levels else d.lo
            base[name] = mid
        else:
            base[name] = levels[0] if levels else None
    return base


def _extremes(d: Domain) -> list:
    """The lo/hi corner values of one axis (both ends of a set or a range)."""
    if isinstance(d, SetDomain):
        vals = list(d.values)
        if not vals:
            return []
        if len(vals) == 1:
            return [vals[0]]
        return [vals[0], vals[-1]]
    return [d.lo, d.hi]


def _dedup(dicts: List[Dict]) -> List[Dict]:
    """Drop repeated param-dicts while preserving first-seen order."""
    out: List[Dict] = []
    seen = set()
    for d in dicts:
        key = tuple(sorted(d.items()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def boundary_param_sets(
    axes: Dict[str, Domain],
    strategy: str = "one-at-a-time",
    shape: str = "ints",
    cap: int = DEFAULT_CAP,
) -> List[Dict]:
    """Expand declared axes into a list of shape param-dicts for the given strategy.

    `shape` is accepted so a future strategy can specialise per shape; today it is
    advisory and does not change the combinations. `cap` bounds the 'full' product.
    """
    if not axes:
        return []

    if strategy == "one-at-a-time":
        base = _baseline(axes)
        out = [dict(base)]
        for name, d in axes.items():
            for v in boundary_values(d):
                variant = dict(base)
                variant[name] = v
                out.append(variant)
        return _dedup(out)

    if strategy == "corners":
        names = list(axes)
        value_lists = [_extremes(axes[n]) for n in names]
        out = []
        for combo in itertools.product(*value_lists):
            out.append(dict(zip(names, combo)))
            if len(out) >= cap:
                break
        return _dedup(out)[:cap]

    if strategy == "full":
        names = list(axes)
        value_lists = [boundary_values(axes[n]) for n in names]
        out = []
        for combo in itertools.product(*value_lists):
            out.append(dict(zip(names, combo)))
            if len(out) >= cap:
                break
        return _dedup(out)[:cap]

    raise ValueError(
        f"Unknown boundary strategy '{strategy}'. Choose: one-at-a-time, corners, full."
    )


def structural_extremes(shape: str, axes: Dict[str, Domain]) -> List[Dict]:
    """Shape-level extremes (empty / single / max) derived from a size axis.

    Looks for the first axis whose name is a recognised size (n, count, ...). If
    none is declared there is nothing structural to vary, so the result is empty.
    The returned dicts pin that size axis to its smallest meaningful values and to
    its maximum, holding any other axes at their baseline.
    """
    size_name = None
    for cand in SIZE_NAMES:
        if cand in axes:
            size_name = cand
            break
    if size_name is None:
        return []

    d = axes[size_name]
    if isinstance(d, SetDomain):
        sizes = sorted(v for v in d.values if isinstance(v, (int, float)))
        if not sizes:
            return []
        lo, hi = sizes[0], sizes[-1]
    else:
        lo, hi = d.lo, d.hi

    # - candidate structural sizes: empty (lo, often 0/1), single element, and max.
    base = _baseline(axes)
    candidates = [lo, lo + 1, hi]
    out = []
    for s in candidates:
        if isinstance(d, RangeDomain) and not (d.lo <= s <= d.hi):
            continue
        if isinstance(d, SetDomain) and s not in d.values:
            continue
        variant = dict(base)
        variant[size_name] = s
        out.append(variant)
    return _dedup(out)
