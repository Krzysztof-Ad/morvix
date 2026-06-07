# Tests for bounded-exhaustive enumeration (enumerate_inputs.py).
#
# These are pure-logic tests: no project, no solution run. They check that the
# enumerator emits the whole finite space (size matches count_estimate), renders
# each point correctly, and respects the cap without erroring.

import itertools

import pytest

from morvix.enumerate_inputs import count_estimate, enumerate_for
from morvix.errors import UserError


def test_enumerate_array_counts():
    # For small bounds the enumeration size must equal count_estimate exactly.
    for shape in ("array", "ints"):
        for max_n in range(0, 4):
            for values in ([0, 1], [0, 1, 2]):
                got = enumerate_for(shape, max_n, values, cap=10_000)
                assert len(got) == count_estimate(shape, max_n, values)
                # every one is distinct (the product space has no repeats)
                assert len(set(got)) == len(got)


def test_enumerate_array_rendering():
    # Length line, then space-joined values; empty sequence renders just "0".
    got = enumerate_for("array", 2, [0, 1], cap=100)
    assert "0\n" in got  # the empty sequence
    assert "1\n0" in got and "1\n1" in got  # the singletons
    assert "2\n0 1" in got and "2\n1 0" in got  # a couple of length-2 ones


def test_enumerate_permutation_all_distinct():
    got = enumerate_for("permutation", 3, None, cap=10_000)
    assert len(got) == count_estimate("permutation", 3, None)
    assert len(set(got)) == len(got)
    # n=3 has 6 permutations; each renders as "3\n" then 3 lines of 1..3.
    perms3 = [t for t in got if t.startswith("3\n")]
    assert len(perms3) == 6
    for t in perms3:
        lines = t.split("\n")
        assert lines[0] == "3"
        assert sorted(int(x) for x in lines[1:]) == [1, 2, 3]


def test_enumerate_string_counts():
    got = enumerate_for("string", 3, ["a", "b"], cap=10_000)
    assert len(got) == count_estimate("string", 3, ["a", "b"])
    # 1 + 2 + 4 + 8 = 15 strings of length 0..3 over {a,b}
    assert len(got) == 15
    assert "" in got and "a" in got and "ab" in got and "bab" in got


def test_enumerate_respects_cap():
    # Capping truncates silently with no error and never exceeds the cap.
    full = count_estimate("array", 4, [0, 1, 2])
    assert full > 5
    capped = enumerate_for("array", 4, [0, 1, 2], cap=5)
    assert len(capped) == 5
    # The capped prefix is exactly the first 5 of the full enumeration.
    full_list = enumerate_for("array", 4, [0, 1, 2], cap=10_000)
    assert capped == full_list[:5]
    # A zero/negative cap yields an empty list, not an error.
    assert enumerate_for("array", 4, [0, 1, 2], cap=0) == []
    assert enumerate_for("array", 4, [0, 1, 2], cap=-3) == []


def test_count_estimate_tree():
    # Cayley's formula: n^(n-2) labelled trees; n<=2 gives 1 each.
    # n in 1..4: 1 + 1 + 3 + 16 = 21.
    assert count_estimate("tree", 1, None) == 1
    assert count_estimate("tree", 2, None) == 2
    assert count_estimate("tree", 3, None) == 1 + 1 + 3
    assert count_estimate("tree", 4, None) == 1 + 1 + 3 + 16
    # Enumeration agrees with the estimate and yields valid, distinct trees.
    got = enumerate_for("tree", 4, None, cap=10_000)
    assert len(got) == count_estimate("tree", 4, None)
    assert len(set(got)) == len(got)


def _tree_edges(text):
    lines = text.split("\n")
    n = int(lines[0])
    edges = [tuple(int(x) for x in ln.split()) for ln in lines[1:] if ln]
    return n, edges


def test_enumerate_tree_emits_valid_trees():
    # Each emitted tree on n nodes has n-1 edges and is connected & acyclic.
    for text in enumerate_for("tree", 4, None, cap=10_000):
        n, edges = _tree_edges(text)
        assert len(edges) == n - 1
        # union-find connectivity check
        parent = list(range(n + 1))

        def find(x, parent=parent):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for u, v in edges:
            assert 1 <= u <= n and 1 <= v <= n
            ru, rv = find(u), find(v)
            assert ru != rv, "edges form a cycle"  # acyclic: never already joined
            parent[ru] = rv
        roots = {find(i) for i in range(1, n + 1)}
        assert len(roots) == 1, "tree is disconnected"


def test_count_estimate_array_geometric():
    # sum of k**length for length 0..max_n
    assert count_estimate("array", 0, [0, 1]) == 1  # only the empty sequence
    assert count_estimate("array", 2, [0, 1]) == 1 + 2 + 4
    assert count_estimate("ints", 2, [0, 1, 2]) == 1 + 3 + 9


def test_default_values_used_when_none():
    # array with values=None falls back to the small {0,1} default.
    assert count_estimate("array", 2, None) == count_estimate("array", 2, [0, 1])
    got = enumerate_for("array", 2, None, cap=100)
    assert len(got) == count_estimate("array", 2, None)


def test_unknown_shape_raises():
    with pytest.raises(UserError):
        enumerate_for("graph", 3, None, cap=10)
    with pytest.raises(UserError):
        count_estimate("graph", 3, None)


def test_negative_max_n_raises():
    with pytest.raises(UserError):
        enumerate_for("array", -1, [0, 1], cap=10)
    with pytest.raises(UserError):
        count_estimate("array", -1, [0, 1])


def test_enumerate_matches_itertools_array():
    # Cross-check the array body against a direct itertools.product for one size.
    bodies = []
    for text in enumerate_for("array", 2, [0, 1], cap=100):
        lines = text.split("\n")
        body = lines[1] if len(lines) > 1 else ""
        bodies.append(body)
    expected = [""]
    for length in (1, 2):
        for seq in itertools.product([0, 1], repeat=length):
            expected.append(" ".join(str(v) for v in seq))
    assert bodies == expected
