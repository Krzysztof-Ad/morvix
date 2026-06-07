# Tests for value distributions + the difficulty dial (distributions.py).

import random

import pytest

from morvix.distributions import (
    difficulty_params,
    list_dists,
    parse_difficulty,
    sample,
    sample_many,
)


def test_list_dists_has_all_six():
    assert list_dists() == [
        "uniform",
        "loguniform",
        "zipf",
        "gaussian",
        "bimodal",
        "clustered",
    ]


def test_sample_in_range_all_dists():
    # Every distribution must keep its draws within [lo, hi] over many draws,
    # including a range that spans zero/negatives.
    for dist in list_dists():
        rng = random.Random(7)
        for lo, hi in [(0, 100), (-50, 50), (5, 5), (-1000000, 1000000)]:
            vals = sample_many(rng, 200, lo, hi, dist)
            assert len(vals) == 200
            for v in vals:
                assert lo <= v <= hi, f"{dist} produced {v} outside [{lo}, {hi}]"


def test_integer_bounds_yield_ints():
    rng = random.Random(1)
    for dist in list_dists():
        v = sample(rng, 0, 1000, dist)
        assert isinstance(v, int)


def test_float_bounds_yield_floats():
    rng = random.Random(1)
    v = sample(rng, 0.0, 1.0, "uniform")
    assert isinstance(v, float)


def test_sample_is_deterministic_with_seed():
    a = sample_many(random.Random(42), 50, 0, 1000, "zipf")
    b = sample_many(random.Random(42), 50, 0, 1000, "zipf")
    assert a == b


def test_zipf_is_skewed():
    # Zipf should concentrate mass on the low end far more than uniform does.
    lo, hi = 0, 1000
    n = 4000
    zipf_vals = sample_many(random.Random(3), n, lo, hi, "zipf")
    uni_vals = sample_many(random.Random(3), n, lo, hi, "uniform")
    cutoff = (hi - lo) // 10  # bottom 10% of the range
    zipf_low = sum(1 for v in zipf_vals if v <= cutoff)
    uni_low = sum(1 for v in uni_vals if v <= cutoff)
    assert zipf_low > uni_low
    # And the mean of a zipf draw sits well below the range midpoint.
    assert sum(zipf_vals) / n < (lo + hi) / 2.0


def test_clustered_has_few_distinct_values():
    # Clustered snaps to a handful of hot-spots, so distinct count stays low.
    vals = sample_many(random.Random(5), 500, 0, 1000000, "clustered", {"clusters": 4})
    assert len(set(vals)) < 200


def test_unknown_dist_raises():
    with pytest.raises(ValueError):
        sample(random.Random(0), 0, 10, "no_such_dist")


def test_parse_difficulty_levels():
    assert parse_difficulty("easy") < parse_difficulty("medium")
    assert parse_difficulty("medium") < parse_difficulty("hard")
    assert parse_difficulty("hard") < parse_difficulty("adversarial")
    assert parse_difficulty("adversarial") == 1.0
    for level in ("easy", "medium", "hard", "adversarial"):
        d = parse_difficulty(level)
        assert 0.0 <= d <= 1.0


def test_parse_difficulty_numeric_and_clamped():
    assert parse_difficulty("0.7") == 0.7
    assert parse_difficulty(0.3) == 0.3
    assert parse_difficulty("2.5") == 1.0  # clamped to 1
    assert parse_difficulty("-1") == 0.0  # clamped to 0
    assert parse_difficulty("EASY") == parse_difficulty("easy")  # case-insensitive


def test_parse_difficulty_rejects_garbage():
    with pytest.raises(ValueError):
        parse_difficulty("banana")


def test_difficulty_adversarial_retargets():
    # At the top of the dial a base shape with a known worst case is retargeted
    # onto the adversarial shape name; lower difficulties leave the shape alone.
    p_hard = difficulty_params("ints", "adversarial")
    assert p_hard.get("shape") == "anti_quicksort"

    p_med = difficulty_params("ints", "medium")
    assert "shape" not in p_med

    # A shape with no registered worst case is not retargeted (no bogus name).
    p_unknown = difficulty_params("grid", "adversarial")
    assert "shape" not in p_unknown


def test_difficulty_scales_size_upward():
    small = difficulty_params("ints", "easy")
    big = difficulty_params("ints", "hard")
    assert big["count"] > small["count"]
    assert big["n"] > small["n"]


def test_difficulty_params_are_inputs_only():
    # The override dict may only describe inputs: size, value range, distribution,
    # and (at the top) an input shape name. It must never carry an answer.
    allowed = {
        "count",
        "min_n",
        "max_n",
        "n",
        "length",
        "lo",
        "hi",
        "dist",
        "shape",
    }
    for level in ("easy", "medium", "hard", "adversarial"):
        for shape in ("ints", "array", "string", "tree", "graph", "grid"):
            params = difficulty_params(shape, level)
            assert set(params) <= allowed, f"unexpected keys: {set(params) - allowed}"
            for key in params:
                assert "expected" not in key
                assert "answer" not in key
                assert "output" not in key
