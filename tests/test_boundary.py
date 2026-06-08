# Tests for boundary-value param-set expansion (boundary.py).

import itertools

import pytest

from morvix.boundary import boundary_param_sets, structural_extremes
from morvix.boundspec import RangeDomain, SetDomain, boundary_values, parse_specs


def test_one_at_a_time_covers_each_boundary():
    axes = parse_specs(["n=1..5", "v=-2..2"])
    sets = boundary_param_sets(axes, strategy="one-at-a-time")

    # every boundary value of every axis appears at that axis in some param-dict
    for name, d in axes.items():
        for bv in boundary_values(d):
            assert any(s.get(name) == bv for s in sets), (name, bv)

    # one-at-a-time holds the OTHER axes at the baseline: each variant differs
    # from the baseline in at most one axis.
    base = sets[0]
    for s in sets[1:]:
        differing = [k for k in axes if s.get(k) != base.get(k)]
        assert len(differing) <= 1


def test_corners_is_cartesian_of_extremes():
    axes = parse_specs(["n=1..100", "v=-9..9"])
    sets = boundary_param_sets(axes, strategy="corners")

    expected = {(n, v) for n, v in itertools.product([1, 100], [-9, 9])}
    got = {(s["n"], s["v"]) for s in sets}
    assert got == expected
    assert len(sets) == 4


def test_corners_set_axis_uses_first_and_last():
    axes = parse_specs(["layout=sorted,reverse,random", "n=1..10"])
    sets = boundary_param_sets(axes, strategy="corners")
    layouts = {s["layout"] for s in sets}
    assert layouts == {"sorted", "random"}  # first and last members only


def test_full_respects_cap():
    # two wide axes whose full product (>cap) must be truncated to the cap.
    axes = parse_specs(["a=0..1000", "b=0..1000"])
    full_uncapped = boundary_param_sets(axes, strategy="full", cap=1000)
    capped = boundary_param_sets(axes, strategy="full", cap=3)
    assert len(capped) == 3
    assert len(full_uncapped) <= 1000
    # the capped set is a prefix of the uncapped enumeration order
    assert capped == full_uncapped[:3]


def test_structural_extremes_for_ints():
    axes = parse_specs(["n=0..1000"])
    sets = structural_extremes("ints", axes)
    sizes = sorted(s["n"] for s in sets)
    # empty (0), single (1) and the maximum (1000) are all represented
    assert 0 in sizes
    assert 1 in sizes
    assert 1000 in sizes


def test_structural_extremes_no_size_axis_is_empty():
    axes = parse_specs(["v=-5..5"])  # no recognised size axis
    assert structural_extremes("ints", axes) == []


def test_structural_extremes_clamps_to_range():
    # lo+1 would only be added when it stays inside the range.
    axes = parse_specs(["n=5..5"])
    sets = structural_extremes("ints", axes)
    assert all(s["n"] == 5 for s in sets)
    assert len(sets) == 1


def test_one_at_a_time_includes_baseline_first():
    axes = parse_specs(["n=1..10"])
    sets = boundary_param_sets(axes)
    assert len(sets) >= 1
    # the baseline holds n at a representative (middle) value
    assert isinstance(sets[0]["n"], int)


def test_empty_axes_returns_empty():
    assert boundary_param_sets({}) == []
    assert structural_extremes("ints", {}) == []


def test_unknown_strategy_raises():
    axes = parse_specs(["n=1..5"])
    with pytest.raises(ValueError):
        boundary_param_sets(axes, strategy="diagonal")


def test_set_axis_boundary_one_at_a_time():
    axes = parse_specs(["layout=sorted,reverse,random"])
    sets = boundary_param_sets(axes)
    layouts = {s["layout"] for s in sets}
    assert {"sorted", "reverse", "random"} <= layouts


def test_results_are_dicts_with_all_axis_keys():
    axes = parse_specs(["n=1..5", "v=0..3"])
    for strategy in ("one-at-a-time", "corners", "full"):
        for s in boundary_param_sets(axes, strategy=strategy):
            assert set(s) == {"n", "v"}


def test_no_expected_fields_anywhere():
    # honesty: this module produces inputs/params only, never an answer.
    axes = parse_specs(["n=1..5"])
    produced = boundary_param_sets(axes, "full") + structural_extremes("ints", axes)
    for d in produced:
        assert not any("expected" in str(k) for k in d)
