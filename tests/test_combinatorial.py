# Tests for the greedy IPOG covering array (combinatorial.py).

import itertools
import random

from morvix.combinatorial import covering_array


def _all_tuples_covered(rows, factors, t):
    """Assert every combination of every t factors' levels appears in some row."""
    names = list(factors)
    for group in itertools.combinations(names, t):
        wanted = set(itertools.product(*(factors[n] for n in group)))
        seen = set()
        for row in rows:
            seen.add(tuple(row[n] for n in group))
        missing = wanted - seen
        assert not missing, f"uncovered {t}-tuples for {group}: {missing}"


def test_covering_array_covers_all_pairs():
    factors = {
        "a": [0, 1, 2],
        "b": ["x", "y", "z"],
        "c": [True, False],
        "d": [10, 20, 30],
    }
    rows = covering_array(factors, strength=2, rng=random.Random(1))
    # every row is a complete assignment
    for row in rows:
        assert set(row) == set(factors)
        for name, levels in factors.items():
            assert row[name] in levels
    _all_tuples_covered(rows, factors, 2)


def test_covering_array_smaller_than_full():
    # four factors of three levels: full product is 3**4 = 81 rows.
    factors = {name: [0, 1, 2] for name in ("a", "b", "c", "d")}
    rows = covering_array(factors, strength=2, rng=random.Random(7))
    full = 3**4
    assert len(rows) < full
    # pairwise of v levels needs at least v*v rows; comfortably under the product
    assert len(rows) <= full // 2
    _all_tuples_covered(rows, factors, 2)


def test_strength_three_covers_triples():
    factors = {
        "a": [0, 1, 2],
        "b": [0, 1, 2],
        "c": [0, 1, 2],
        "d": [0, 1, 2],
        "e": [0, 1],
    }
    rows = covering_array(factors, strength=3, rng=random.Random(3))
    _all_tuples_covered(rows, factors, 3)
    # triples need >= 3**3 rows but still far fewer than the full 3*3*3*3*2 = 162
    assert len(rows) < 3 * 3 * 3 * 3 * 2


def test_single_factor_trivial():
    factors = {"only": [1, 2, 3]}
    rows = covering_array(factors, strength=2, rng=random.Random(0))
    # with one factor, "pairwise" degrades to covering each level once
    assert {row["only"] for row in rows} == {1, 2, 3}
    _all_tuples_covered(rows, factors, 1)


def test_deterministic_same_seed():
    factors = {"a": [0, 1, 2], "b": [0, 1, 2], "c": [0, 1], "d": [0, 1, 2]}
    one = covering_array(factors, strength=2, rng=random.Random(42))
    two = covering_array(factors, strength=2, rng=random.Random(42))
    assert one == two


def test_empty_factors_returns_empty():
    assert covering_array({}, strength=2, rng=random.Random(0)) == []
    # a factor with no levels is dropped
    assert covering_array({"a": []}, strength=2, rng=random.Random(0)) == []


def test_strength_exceeding_factor_count_is_clamped():
    # asking for triples with only two factors still covers all pairs.
    factors = {"a": [0, 1], "b": ["x", "y"]}
    rows = covering_array(factors, strength=3, rng=random.Random(0))
    _all_tuples_covered(rows, factors, 2)


def test_default_rng_is_reproducible():
    factors = {"a": [0, 1, 2], "b": [0, 1, 2], "c": [0, 1, 2]}
    one = covering_array(factors, strength=2)
    two = covering_array(factors, strength=2)
    assert one == two
    _all_tuples_covered(one, factors, 2)
