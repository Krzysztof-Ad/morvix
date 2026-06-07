# Tests for the bound-spec mini-language (boundspec.py).

import pytest

from morvix.boundspec import (
    RangeDomain,
    SetDomain,
    boundary_values,
    enum_values,
    factor_levels,
    num_token,
    parse_spec,
)
from morvix.errors import UserError


def test_num_token_scientific_integral_is_int():
    assert num_token("1e5") == (100000, True)
    assert num_token("-1e9") == (-1000000000, True)
    assert num_token("3") == (3, True)
    val, is_int = num_token("1.5")
    assert val == 1.5 and is_int is False


def test_parse_range_int():
    d = parse_spec("n=1..1e5")
    assert isinstance(d, RangeDomain)
    assert d.name == "n" and d.lo == 1 and d.hi == 100000 and d.is_int


def test_parse_set_numeric():
    d = parse_spec("v=0,1,2")
    assert isinstance(d, SetDomain)
    assert d.values == (0, 1, 2)


def test_parse_set_strings():
    d = parse_spec("layout=sorted,reverse,random")
    assert isinstance(d, SetDomain)
    assert d.values == ("sorted", "reverse", "random")


def test_parse_rejects_range_and_set():
    with pytest.raises(UserError):
        parse_spec("n=1..10,20")


def test_parse_rejects_missing_eq():
    with pytest.raises(UserError):
        parse_spec("nonsense")


def test_boundary_values_int_clamped():
    vals = boundary_values(RangeDomain("n", 1, 5, True))
    assert min(vals) >= 1 and max(vals) <= 5
    assert 1 in vals and 5 in vals  # the extremes are always present
    assert -1 not in vals  # out of range, dropped


def test_factor_levels_caps():
    levels = factor_levels(RangeDomain("v", -10, 10, True), max_levels=4)
    assert len(levels) <= 4
    assert -10 in levels and 10 in levels and 0 in levels  # min/max/zero


def test_enum_values_int_range():
    assert enum_values(RangeDomain("n", 0, 3, True)) == [0, 1, 2, 3]


def test_enum_values_rejects_float_range():
    with pytest.raises(UserError):
        enum_values(RangeDomain("x", 0.0, 1.0, False))
