# Tests for the seeded combinator library (genlib.py).
#
# These verify the combinators produce valid, reproducible structures and that
# the renderers turn them into clean input text. They assert input SHAPE only -
# a tree has n-1 edges and is connected, a graph parses - never any answer.

import random

import pytest

from morvix import genlib
from morvix.genlib import Gen, GenError

# ---------------------------------------------------------------------------
# Small structural helpers
# ---------------------------------------------------------------------------


def _is_connected_tree(n, edges):
    # n-1 edges and a single component over union-find.
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
    roots = {find(i) for i in range(1, n + 1)}
    return len(roots) == 1


# ---------------------------------------------------------------------------
# Determinism / seeding
# ---------------------------------------------------------------------------


def test_same_seed_same_output():
    a = Gen(7)
    b = Gen(7)
    assert a.ints(20, 0, 1000) == b.ints(20, 0, 1000)
    assert Gen(3).perm(50) == Gen(3).perm(50)
    assert Gen(9).tree(40) == Gen(9).tree(40)
    assert Gen(9).graph(30, 60) == Gen(9).graph(30, 60)


def test_wrap_existing_rng():
    rng = random.Random(11)
    g = Gen(rng=rng)
    first = g.ints(5, 0, 100)
    g2 = Gen(rng=random.Random(11))
    assert first == g2.ints(5, 0, 100)


# ---------------------------------------------------------------------------
# Scalars and collections
# ---------------------------------------------------------------------------


def test_int_in_range():
    g = Gen(1)
    for _ in range(200):
        v = g.int_(-5, 5)
        assert -5 <= v <= 5


def test_int_empty_range_raises():
    with pytest.raises(GenError):
        Gen(1).int_(10, 1)


def test_array_and_ints_length_and_bounds():
    g = Gen(2)
    arr = g.array(15, 3, 9)
    assert len(arr) == 15
    assert all(3 <= x <= 9 for x in arr)


def test_string_length_and_alphabet():
    s = Gen(2).string(40, alphabet="ab")
    assert len(s) == 40
    assert set(s) <= set("ab")


def test_string_empty_alphabet_raises():
    with pytest.raises(GenError):
        Gen(1).string(5, alphabet="")


def test_perm_is_a_permutation():
    p = Gen(4).perm(100)
    assert sorted(p) == list(range(1, 101))


def test_matrix_dimensions():
    m = Gen(5).matrix(4, 6, 0, 9)
    assert len(m) == 4
    assert all(len(row) == 6 for row in m)
    assert all(0 <= x <= 9 for row in m for x in row)


def test_grid_dimensions_and_alphabet():
    g = Gen(6).grid(3, 7, alphabet=".#")
    assert len(g) == 3
    assert all(len(row) == 7 for row in g)
    assert all(set(row) <= set(".#") for row in g)


def test_negative_count_raises():
    with pytest.raises(GenError):
        Gen(1).ints(-1, 0, 9)


# ---------------------------------------------------------------------------
# Trees: n-1 edges and connected for every kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["random", "path", "star", "binary", "caterpillar", "by_degree"])
def test_tree_has_n_minus_1_edges_and_connected(kind):
    n = 60
    edges = Gen(13).tree(n, kind=kind)
    assert _is_connected_tree(n, edges)


def test_tree_tiny_n():
    assert Gen(1).tree(1) == []
    assert len(Gen(1).tree(2)) == 1


def test_tree_unknown_kind_raises():
    with pytest.raises(GenError):
        Gen(1).tree(5, kind="nope")


# ---------------------------------------------------------------------------
# Graphs: parse, no self-loops, no duplicate edges, connectivity, dag order
# ---------------------------------------------------------------------------


def test_graph_simple_and_within_bounds():
    n, m = 30, 50
    edges = Gen(8).graph(n, m)
    seen = set()
    for u, v in edges:
        assert 1 <= u <= n and 1 <= v <= n and u != v
        key = (min(u, v), max(u, v))
        assert key not in seen
        seen.add(key)
    assert len(edges) <= m


def test_graph_connected_spanning_tree():
    n = 25
    edges = Gen(2).graph(n, n - 1, connected=True)
    # connected with exactly a spanning tree's worth of edges -> it is a tree.
    assert _is_connected_tree(n, edges)


def test_graph_dag_edges_point_forward():
    edges = Gen(3).graph(20, 40, directed=True, dag=True)
    assert all(u < v for u, v in edges)


def test_graph_caps_at_complete():
    # asking for far more edges than exist returns at most the complete graph.
    n = 5
    edges = Gen(1).graph(n, 1000)
    assert len(edges) <= n * (n - 1) // 2


def test_graph_negative_m_raises():
    with pytest.raises(GenError):
        Gen(1).graph(5, -3)


# ---------------------------------------------------------------------------
# Combinators
# ---------------------------------------------------------------------------


def test_oneof_picks_a_member():
    choices = ["a", "b", "c"]
    for _ in range(50):
        assert Gen(random.randint(0, 9999)).oneof(choices) in choices


def test_oneof_empty_raises():
    with pytest.raises(GenError):
        Gen(1).oneof([])


def test_weighted_respects_zero_weight():
    g = Gen(1)
    # 'b' has zero weight, so it should never be picked.
    picks = {g.weighted(["a", "b"], [1, 0]) for _ in range(100)}
    assert picks == {"a"}


def test_weighted_length_mismatch_raises():
    with pytest.raises(GenError):
        Gen(1).weighted(["a", "b"], [1])


def test_repeat_collects_results():
    g = Gen(1)
    vals = g.repeat(5, lambda: g.int_(0, 0))
    assert vals == [0, 0, 0, 0, 0]


def test_constrain_resamples_until_ok():
    g = Gen(1)
    # keep drawing until we get an even number; must succeed and be even.
    v = g.constrain(lambda: g.int_(0, 100), lambda x: x % 2 == 0)
    assert v % 2 == 0


def test_constrain_exhausts_raises():
    g = Gen(1)
    with pytest.raises(GenError):
        g.constrain(lambda: g.int_(0, 0), lambda x: x == 999, tries=10)


def test_seq_renders_parts():
    g = Gen(1)
    text = g.seq("3", [1, 2, 3])
    assert text == "3\n1 2 3"


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def test_tokens_and_lines_and_header():
    assert genlib.tokens([1, 2, 3]) == "1 2 3"
    assert genlib.lines([1, 2, 3]) == "1\n2\n3"
    assert genlib.header(4, 5) == "4 5"


def test_render_nested_rows():
    assert genlib.render([[1, 2], [3, 4]]) == "1 2\n3 4"
    assert genlib.render([1, 2, 3]) == "1 2 3"
    assert genlib.render("hi") == "hi"
    assert genlib.render(7) == "7"


def test_render_unrenderable_raises():
    with pytest.raises(GenError):
        genlib.render({1: 2})


def test_render_integral_float_is_clean():
    assert genlib.tokens([1.0, 2.0]) == "1 2"


def test_write_adds_trailing_newline(tmp_path):
    path = tmp_path / "in.txt"
    genlib.write(str(path), "1 2 3")
    assert path.read_text() == "1 2 3\n"
