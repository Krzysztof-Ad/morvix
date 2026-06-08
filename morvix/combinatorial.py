# Greedy IPOG-style covering array (Section 13.5).
#
# A "t-wise covering array" is a small set of rows that, between them, exercise
# every combination of every t factors' levels at least once. With many factors
# the full cartesian product explodes (k factors of v levels => v**k rows), but
# you rarely need every COMBINATION of every factor at once — most bugs show up
# from the interaction of just a few factors. Pairwise (t=2) catches every pair;
# t=3 every triple; and so on. The array is far smaller than the product yet
# still covers all t-way interactions.
#
# This is an input-shaping helper: it returns assignments (dicts of
# factor -> level), never an answer. Callers turn each row into a generated
# input; the solution is run later, separately, by gen --expected.
#
# Algorithm: IPOG ("in-parameter-order"). Build a covering array for the first t
# factors as the full product of their levels, then add one factor at a time:
#   - horizontal growth: extend each existing row with the value of the new
#     factor that covers the most still-uncovered t-tuples;
#   - vertical growth: add fresh rows to cover whatever t-tuples remain.
# Greedy choices are made deterministically (ties broken by level order) and any
# remaining "don't care" slots are filled from a seeded random.Random, so the
# result is reproducible for a given rng.

import itertools
import random
from typing import Dict, List, Optional


def covering_array(
    factors: Dict[str, list],
    strength: int = 2,
    rng: Optional[random.Random] = None,
) -> List[dict]:
    """Return rows (factor -> level dicts) covering every t-way combination.

    factors maps each factor name to its list of levels. strength (t) is the
    interaction size to cover (2 = pairwise). Every combination of every t
    factors' levels is guaranteed to appear in at least one returned row.
    """
    if rng is None:
        rng = random.Random(0)
    if strength < 1:
        raise ValueError("strength must be at least 1")

    names = list(factors)
    # - drop factors with no levels; an empty factor has nothing to cover
    names = [n for n in names if factors[n]]
    if not names:
        return []

    # - t cannot exceed the number of factors we have
    t = min(strength, len(names))

    # Seed: the full product of the first t factors' levels. This block already
    # covers every t-tuple among those factors.
    base = names[:t]
    rows: List[dict] = []
    for combo in itertools.product(*(factors[n] for n in base)):
        rows.append(dict(zip(base, combo)))

    covered: set = set()
    for row in rows:
        _mark_covered(covered, row, t)

    # Add the remaining factors one at a time (in-parameter-order).
    for idx in range(t, len(names)):
        name = names[idx]
        prefix = names[:idx]  # factors already assigned in every row
        levels = factors[name]

        # Horizontal growth: give each existing row the level of `name` that
        # newly covers the most t-tuples with the already-placed factors.
        for row in rows:
            best_level = _best_level(row, name, levels, prefix, covered, t)
            row[name] = best_level
            _mark_covered(covered, row, t)

        # Vertical growth: any t-tuple involving `name` that is still uncovered
        # needs a row. Try to fold each into an existing partial row; otherwise
        # start a new row.
        missing = _uncovered_tuples(prefix + [name], factors, covered, t, name)
        for tup in missing:
            assignment = dict(tup)
            if _is_covered(covered, assignment):
                continue
            placed = _place_in_existing(rows, assignment, covered, t)
            if not placed:
                row = dict(assignment)
                rows.append(row)
                _mark_covered(covered, row, t)

    # Fill any unset slots (the seed rows never assigned later factors via a
    # forced choice; vertical-growth rows leave most factors as "don't care").
    for row in rows:
        for name in names:
            if name not in row:
                row[name] = rng.choice(factors[name])

    return rows


def _combos_with(name, others, t):
    """Yield the sets of t factor-names that include `name`, drawn from others+name."""
    # - pick t-1 partners from the already-placed factors
    if t == 1:
        yield (name,)
        return
    for partners in itertools.combinations(others, t - 1):
        yield partners + (name,)


def _mark_covered(covered, row, t):
    """Record every fully-assigned t-tuple present in `row` as covered."""
    keys = [k for k in row if row[k] is not None]
    if len(keys) < t:
        return
    for group in itertools.combinations(sorted(keys), t):
        covered.add(tuple((k, row[k]) for k in group))


def _is_covered(covered, assignment):
    """True when this exact small assignment (a t-tuple) is already covered."""
    keys = sorted(k for k in assignment if assignment[k] is not None)
    tup = tuple((k, assignment[k]) for k in keys)
    return tup in covered


def _best_level(row, name, levels, prefix, covered, t):
    """The level of `name` that covers the most new t-tuples with row's prefix."""
    placed = [k for k in prefix if row.get(k) is not None]
    best_level = levels[0]
    best_gain = -1
    for level in levels:
        gain = 0
        for partners in _combos_with(name, placed, t):
            others = [k for k in partners if k != name]
            tup = tuple(sorted([(k, row[k]) for k in others] + [(name, level)]))
            if tup not in covered:
                gain += 1
        if gain > best_gain:
            best_gain = gain
            best_level = level
    return best_level


def _uncovered_tuples(scope, factors, covered, t, must_include):
    """All still-uncovered t-tuples over `scope` that include `must_include`."""
    out = []
    others = [n for n in scope if n != must_include]
    for partners in itertools.combinations(others, t - 1):
        group = sorted(partners + (must_include,))
        for combo in itertools.product(*(factors[n] for n in group)):
            tup = tuple(zip(group, combo))
            if tup not in covered:
                out.append(tup)
    return out


def _place_in_existing(rows, assignment, covered, t):
    """Try to merge `assignment` into a compatible row that has free slots.

    A row is compatible when it does not already disagree on any assigned
    factor. Filling its "don't care" slots is free, so we reuse a row rather
    than add a new one whenever possible.
    """
    for row in rows:
        ok = True
        for k, v in assignment.items():
            if k in row and row[k] is not None and row[k] != v:
                ok = False
                break
        if ok:
            for k, v in assignment.items():
                row[k] = v
            _mark_covered(covered, row, t)
            return True
    return False
