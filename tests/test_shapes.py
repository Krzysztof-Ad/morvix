# Tests for morvix/shapes.py — list_shapes() and generate().

import pytest

from morvix.shapes import generate, list_shapes


def test_list_shapes_returns_sorted_nonempty():
    shapes = list_shapes()
    assert shapes
    assert shapes == sorted(shapes)


def test_list_shapes_contains_expected():
    shapes = set(list_shapes())
    for name in ("int", "ints", "array", "string", "permutation", "tree", "graph", "grid", "edge"):
        assert name in shapes


# ---------------------------------------------------------------------------
# Reproducibility and seed sensitivity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shape", list_shapes())
def test_generate_reproducible(shape):
    a = generate(shape, seed=42, params={})
    b = generate(shape, seed=42, params={})
    assert a == b


_DETERMINISTIC_SHAPES = {
    # "edge" with default params always returns "1\n0" (kind="single", lo=0) regardless of
    # seed — the rng is never consulted, so identical output for all seeds is correct.
    "edge",
}

@pytest.mark.parametrize("shape", [s for s in list_shapes() if s not in _DETERMINISTIC_SHAPES])
def test_generate_varies_with_seed(shape):
    # Different seeds should almost always produce different output.
    # We try several seeds to avoid accidental collisions on short shapes.
    results = {generate(shape, seed=s, params={}) for s in range(10)}
    assert len(results) > 1, f"shape '{shape}' produced identical output for all seeds 0-9"


def test_generate_unknown_shape_raises():
    with pytest.raises(ValueError, match="Unknown shape"):
        generate("nonexistent_shape", seed=0, params={})


# ---------------------------------------------------------------------------
# Every shape produces non-empty str for empty params
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("shape", list_shapes())
def test_generate_nonempty_str_empty_params(shape):
    result = generate(shape, seed=1, params={})
    assert isinstance(result, str)
    assert result.strip()


# ---------------------------------------------------------------------------
# Shape-specific checks
# ---------------------------------------------------------------------------

def test_permutation_valid():
    # With n=8 explicitly supplied, result must be a permutation of 1..8.
    result = generate("permutation", seed=7, params={"n": 8})
    lines = result.strip().splitlines()
    n = int(lines[0])
    assert n == 8
    assert len(lines) == n + 1
    values = [int(x) for x in lines[1:]]
    assert sorted(values) == list(range(1, n + 1))


def test_permutation_valid_default_params():
    result = generate("permutation", seed=99, params={})
    lines = result.strip().splitlines()
    n = int(lines[0])
    assert len(lines) == n + 1
    values = [int(x) for x in lines[1:]]
    assert sorted(values) == list(range(1, n + 1))


def test_array_count_param():
    for count in (1, 5, 20):
        result = generate("array", seed=3, params={"count": count})
        tokens = result.split()
        assert len(tokens) == count, f"expected {count} tokens, got {len(tokens)}"


def test_array_count_values_in_range():
    result = generate("array", seed=5, params={"count": 50, "lo": 10, "hi": 20})
    tokens = result.split()
    assert len(tokens) == 50
    for t in tokens:
        v = int(t)
        assert 10 <= v <= 20


def test_ints_count_param():
    result = generate("ints", seed=11, params={"count": 7})
    lines = result.strip().splitlines()
    n = int(lines[0])
    assert n == 7
    assert len(lines) == 8  # header + 7 values


def test_ints_sorted_layout():
    result = generate("ints", seed=13, params={"count": 20, "layout": "sorted"})
    lines = result.strip().splitlines()
    values = [int(x) for x in lines[1:]]
    assert values == sorted(values)


def test_ints_reverse_layout():
    result = generate("ints", seed=17, params={"count": 20, "layout": "reverse"})
    lines = result.strip().splitlines()
    values = [int(x) for x in lines[1:]]
    assert values == sorted(values, reverse=True)


def test_int_shape_single_value():
    result = generate("int", seed=0, params={})
    # Must be a single integer token.
    assert result.strip().lstrip("-").isdigit()


def test_int_shape_range():
    result = generate("int", seed=4, params={"lo": 5, "hi": 5})
    assert result.strip() == "5"


def test_string_length_param():
    result = generate("string", seed=2, params={"length": 13})
    assert len(result) == 13


def test_string_alphabet_param():
    result = generate("string", seed=8, params={"length": 30, "alphabet": "ab"})
    assert set(result) <= {"a", "b"}
    assert len(result) == 30


def test_tree_structure():
    result = generate("tree", seed=6, params={"n": 10})
    lines = result.strip().splitlines()
    n = int(lines[0])
    assert n == 10
    assert len(lines) == n  # 1 header + n-1 edges


def test_tree_path_shape():
    result = generate("tree", seed=0, params={"n": 5, "shape": "path"})
    lines = result.strip().splitlines()
    n = int(lines[0])
    edges = [tuple(map(int, l.split())) for l in lines[1:]]
    assert len(edges) == n - 1
    # path: consecutive pairs
    assert edges == [(i, i + 1) for i in range(1, n)]


def test_tree_star_shape():
    result = generate("tree", seed=0, params={"n": 6, "shape": "star"})
    lines = result.strip().splitlines()
    n = int(lines[0])
    edges = [tuple(map(int, l.split())) for l in lines[1:]]
    assert len(edges) == n - 1
    # every edge has node 1 as an endpoint
    for u, v in edges:
        assert u == 1 or v == 1


def test_graph_structure():
    result = generate("graph", seed=10, params={"n": 5})
    lines = result.strip().splitlines()
    first = lines[0].split()
    n, m = int(first[0]), int(first[1])
    assert n == 5
    assert len(lines) == m + 1


def test_grid_dimensions():
    result = generate("grid", seed=0, params={"rows": 4, "cols": 6})
    lines = result.strip().splitlines()
    r, c = map(int, lines[0].split())
    assert r == 4
    assert c == 6
    assert len(lines) == r + 1
    for row in lines[1:]:
        assert len(row) == c


def test_edge_empty_kind():
    result = generate("edge", seed=0, params={"kind": "empty"})
    assert result.strip() == "0"


def test_edge_single_kind():
    result = generate("edge", seed=0, params={"kind": "single", "lo": 7})
    lines = result.strip().splitlines()
    assert lines[0] == "1"
    assert lines[1] == "7"


def test_edge_unknown_kind_raises():
    with pytest.raises(ValueError, match="Unknown edge kind"):
        generate("edge", seed=0, params={"kind": "bogus"})
