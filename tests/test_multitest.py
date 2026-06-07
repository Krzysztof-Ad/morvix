# Tests for the multi-test wrapper (multitest.py).

import pytest

from morvix.multitest import auto_t_sizes, wrap


def test_wrap_t_first_header_and_count():
    subs = ["3\n1 2 3", "2\n4 5"]
    out = wrap(subs, layout="t-first")
    lines = out.split("\n")
    # - first line is T (the count of sub-inputs)
    assert lines[0] == "2"
    # - each sub-input is preserved intact, newline-terminated
    assert out == "2\n3\n1 2 3\n2\n4 5\n"


def test_wrap_t_first_preserves_existing_trailing_newline():
    # a sub-input that already ends in a newline must not gain a second one
    subs = ["1 2 3\n", "4 5 6"]
    out = wrap(subs, layout="t-first")
    assert out == "2\n1 2 3\n4 5 6\n"


def test_wrap_per_line():
    subs = ["  5  ", "10\n", "  42"]
    out = wrap(subs, layout="per-line")
    # T header then one stripped sub-input per line
    assert out == "3\n5\n10\n42\n"


def test_wrap_empty():
    assert wrap([], layout="t-first") == "0\n"
    assert wrap([], layout="per-line") == "0\n"


def test_wrap_unknown_layout_raises():
    with pytest.raises(ValueError):
        wrap(["1"], layout="nonsense")


def test_auto_t_sizes_includes_one_and_max():
    sizes = auto_t_sizes(1000)
    assert sizes[0] == 1
    assert sizes[-1] == 1000
    assert sizes == sorted(sizes)
    assert len(sizes) == len(set(sizes))  # deduped


def test_auto_t_sizes_small_max_dedups_and_clamps():
    # max_t of 1 collapses to just [1]; everything stays >= 1
    assert auto_t_sizes(1) == [1]
    assert auto_t_sizes(0) == [1]
    assert auto_t_sizes(-5) == [1]
    # a tiny max where 1, small and max overlap is still deduped and sorted
    for sizes in (auto_t_sizes(2), auto_t_sizes(3)):
        assert sizes[0] == 1
        assert sizes == sorted(set(sizes))
        assert all(s >= 1 for s in sizes)
