# Tests for the vetted-generator catalog (catalog.py).
#
# These verify the registry round-trips, that generate() is reproducible per
# name, and that the curated entries produce structurally-valid input text. They
# assert input SHAPE only (a tree parses, parens balance) - never any answer.

import pytest

from morvix import catalog
from morvix.genlib import GenError

# ---------------------------------------------------------------------------
# Structural helpers
# ---------------------------------------------------------------------------


def _is_connected_tree(n, edges):
    if len(edges) != n - 1:
        return False
    parent = list(range(n + 1))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for u, v in edges:
        if not (1 <= u <= n and 1 <= v <= n) or u == v:
            return False
        parent[find(u)] = find(v)
    return len({find(i) for i in range(1, n + 1)}) == 1


def _parse_n_edges(text):
    rows = [ln for ln in text.strip().split("\n") if ln]
    n = int(rows[0])
    edges = [tuple(int(t) for t in ln.split()) for ln in rows[1:]]
    return n, edges


def _is_balanced(s):
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


# ---------------------------------------------------------------------------
# Registry API
# ---------------------------------------------------------------------------


def test_catalog_has_expected_entries():
    names = {e.name for e in catalog.list_entries()}
    for required in ("tree.binary", "tree.caterpillar", "graph.dag", "seq.parens"):
        assert required in names


def test_list_entries_sorted():
    names = [e.name for e in catalog.list_entries()]
    assert names == sorted(names)


def test_get_unknown_raises():
    with pytest.raises(GenError):
        catalog.get("does.not.exist")


def test_describe_mentions_params():
    text = catalog.describe("graph.dag")
    assert "graph.dag" in text
    assert "n" in text and "m" in text


def test_register_and_get_roundtrip():
    entry = catalog.CatalogEntry(
        name="test.tmp_entry",
        summary="temporary",
        params=[catalog.Param("n", "int", 3)],
        build=lambda gen, p: str(p["n"]),
    )
    try:
        catalog.register(entry)
        assert catalog.get("test.tmp_entry") is entry
        assert catalog.generate("test.tmp_entry", 0, {}) == "3"
    finally:
        catalog.CATALOG.pop("test.tmp_entry", None)


# ---------------------------------------------------------------------------
# Reproducibility per name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(catalog.CATALOG))
def test_generate_reproducible(name):
    a = catalog.generate(name, 123, {})
    b = catalog.generate(name, 123, {})
    assert a == b
    assert isinstance(a, str)


def test_generate_unknown_name_raises():
    with pytest.raises(GenError):
        catalog.generate("nope.nope", 1, {})


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


def test_generate_unknown_param_raises():
    with pytest.raises(GenError):
        catalog.generate("tree.binary", 1, {"bogus": 5})


def test_param_coercion_from_string():
    # CLI passes strings; the catalog coerces to the declared type.
    text = catalog.generate("tree.binary", 1, {"n": "12"})
    n, edges = _parse_n_edges(text)
    assert n == 12 and _is_connected_tree(n, edges)


def test_bad_int_param_raises():
    with pytest.raises(GenError):
        catalog.generate("tree.binary", 1, {"n": "abc"})


# ---------------------------------------------------------------------------
# Vetted entries produce valid structures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["tree.binary", "tree.caterpillar", "tree.random", "tree.path"])
def test_tree_entries_are_trees(name):
    n, edges = _parse_n_edges(catalog.generate(name, 7, {"n": 50}))
    assert n == 50
    assert _is_connected_tree(n, edges)


def test_seq_parens_balanced():
    for seed in range(20):
        s = catalog.generate("seq.parens", seed, {"n": 30})
        assert len(s) == 60
        assert _is_balanced(s)


def test_seq_parens_default_size():
    s = catalog.generate("seq.parens", 0, {})
    assert _is_balanced(s)


def test_graph_dag_parses_and_acyclic():
    text = catalog.generate("graph.dag", 3, {"n": 12, "m": 25})
    rows = [ln for ln in text.strip().split("\n") if ln]
    n, m = (int(t) for t in rows[0].split())
    assert n == 12
    edges = [tuple(int(t) for t in ln.split()) for ln in rows[1:]]
    assert len(edges) == m
    # DAG: every edge points from a lower id to a higher one -> acyclic.
    assert all(u < v for u, v in edges)


def test_graph_connected_parses():
    text = catalog.generate("graph.connected", 4, {"n": 15, "m": 20})
    rows = [ln for ln in text.strip().split("\n") if ln]
    n, m = (int(t) for t in rows[0].split())
    assert n == 15
    edges = [tuple(int(t) for t in ln.split()) for ln in rows[1:]]
    assert len(edges) == m
    for u, v in edges:
        assert 1 <= u <= n and 1 <= v <= n and u != v


def test_seq_perm_is_permutation():
    text = catalog.generate("seq.perm", 2, {"n": 40})
    rows = text.strip().split("\n")
    n = int(rows[0])
    perm = [int(x) for x in rows[1].split()]
    assert n == 40
    assert sorted(perm) == list(range(1, 41))


def test_seq_ints_count_and_bounds():
    text = catalog.generate("seq.ints", 1, {"n": 25, "lo": 5, "hi": 9})
    rows = text.strip().split("\n")
    n = int(rows[0])
    nums = [int(x) for x in rows[1].split()]
    assert n == 25 and len(nums) == 25
    assert all(5 <= x <= 9 for x in nums)


def test_grid_dimensions():
    text = catalog.generate("grid.random", 1, {"rows": 4, "cols": 6})
    rows = text.strip().split("\n")
    r, c = (int(t) for t in rows[0].split())
    assert r == 4 and c == 6
    body = rows[1:]
    assert len(body) == 4
    assert all(len(line) == 6 for line in body)


# ---------------------------------------------------------------------------
# Honesty: catalog.generate produces input text, never an expectation
# ---------------------------------------------------------------------------


def test_generate_returns_text_only():
    # The contract is simply: a string of input. There is no answer channel.
    out = catalog.generate("seq.parens", 5, {"n": 4})
    assert isinstance(out, str)
