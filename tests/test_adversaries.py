# Tests for the worst-case input constructors (adversaries.py).
#
# These shapes produce inputs only, so the tests verify structure and the
# pathology each one is supposed to provoke — not any expected answer.

import random

from morvix import adversaries

# ---------------------------------------------------------------------------
# Small parsers for the textual outputs
# ---------------------------------------------------------------------------


def _parse_perm(text):
    lines = text.strip().split("\n")
    n = int(lines[0])
    return n, [int(x) for x in lines[1 : n + 1]]


def _parse_n_edges(text):
    lines = [ln for ln in text.strip().split("\n") if ln]
    n = int(lines[0])
    edges = [tuple(int(t) for t in ln.split()) for ln in lines[1:]]
    return n, edges


# A median-of-three quicksort that counts comparisons. Used to prove the
# adversary forces far more work than a random or sorted permutation.
def _qsort_comparisons(arr):
    a = list(arr)
    count = 0

    def cmp(x, y):
        nonlocal count
        count += 1
        return (x > y) - (x < y)

    def med3(lo, mid, hi):
        if cmp(a[lo], a[mid]) < 0:
            if cmp(a[mid], a[hi]) < 0:
                return mid
            return hi if cmp(a[lo], a[hi]) < 0 else lo
        if cmp(a[lo], a[hi]) > 0:
            return lo
        return hi if cmp(a[mid], a[hi]) > 0 else mid

    # iterative quicksort so big inputs cannot blow the Python recursion stack
    stack = [(0, len(a) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 1:
            continue
        p = med3(lo, (lo + hi) // 2, hi)
        a[lo], a[p] = a[p], a[lo]
        pivot = a[lo]
        store = lo + 1
        for i in range(lo + 1, hi + 1):
            if cmp(a[i], pivot) < 0:
                a[i], a[store] = a[store], a[i]
                store += 1
        a[lo], a[store - 1] = a[store - 1], a[lo]
        stack.append((lo, store - 2))
        stack.append((store, hi))
    return count


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def test_adversary_reproducible():
    # Same seed and params -> byte-identical output for every shape.
    for name in adversaries.SHAPES:
        a = adversaries.SHAPES[name](random.Random(42), {"n": 200})
        b = adversaries.SHAPES[name](random.Random(42), {"n": 200})
        assert a == b, name
        assert isinstance(a, str)


# ---------------------------------------------------------------------------
# anti_quicksort
# ---------------------------------------------------------------------------


def test_anti_quicksort_is_permutation():
    n, perm = _parse_perm(adversaries.SHAPES["anti_quicksort"](random.Random(1), {"n": 500}))
    assert n == 500
    assert sorted(perm) == list(range(1, n + 1))


def test_anti_quicksort_kills_median3():
    n = 1500
    adv_n, adv = _parse_perm(adversaries.SHAPES["anti_quicksort"](random.Random(1), {"n": n}))
    assert adv_n == n

    rand = list(range(1, n + 1))
    random.Random(7).shuffle(rand)
    srt = list(range(1, n + 1))

    c_adv = _qsort_comparisons(adv)
    c_rand = _qsort_comparisons(rand)
    c_sorted = _qsort_comparisons(srt)

    # The adversary should drag median-of-three quicksort toward O(n^2): far
    # more comparisons than a random or an already-sorted input of the same n.
    assert c_adv > 8 * c_rand
    assert c_adv > 8 * c_sorted
    # And it should be a sizeable fraction of n^2 (random/n log n is ~1.5e4).
    assert c_adv > n * n // 8


# ---------------------------------------------------------------------------
# anti_hash
# ---------------------------------------------------------------------------


def test_anti_hash_collisions():
    # Every produced integer shares the same low-k bits, so a power-of-two
    # table sized 2^k buckets them all into one bucket.
    bits = 18
    text = adversaries.SHAPES["anti_hash"](random.Random(5), {"n": 300, "bits": bits})
    lines = text.strip().split("\n")
    n = int(lines[0])
    nums = [int(x) for x in lines[1:]]
    assert n == 300 and len(nums) == 300

    mask = (1 << bits) - 1
    buckets = {x & mask for x in nums}
    assert len(buckets) == 1
    # the integers themselves are distinct (a real, non-trivial set)
    assert len(set(nums)) == n


def test_anti_hash_collisions_default_bits():
    # Even without an explicit bits param the keys collide on some 2^k.
    text = adversaries.SHAPES["anti_hash"](random.Random(9), {"n": 100})
    nums = [int(x) for x in text.strip().split("\n")[1:]]
    mask = (1 << 1) - 1  # they must at least agree on the lowest bit
    assert len({x & mask for x in nums}) == 1


# ---------------------------------------------------------------------------
# caterpillar
# ---------------------------------------------------------------------------


def test_caterpillar_is_tree():
    n, edges = _parse_n_edges(adversaries.SHAPES["caterpillar"](random.Random(3), {"n": 40}))
    assert n == 40
    # a tree on n nodes has exactly n-1 edges
    assert len(edges) == n - 1
    # all node ids are valid
    for u, v in edges:
        assert 1 <= u <= n and 1 <= v <= n and u != v
    # connected: union-find over the edges yields a single component
    parent = list(range(n + 1))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for u, v in edges:
        parent[find(u)] = find(v)
    roots = {find(i) for i in range(1, n + 1)}
    assert len(roots) == 1


def test_caterpillar_tiny_n():
    # n=1 is a lone node with no edges; n=2 a single edge.
    n1, e1 = _parse_n_edges(adversaries.SHAPES["caterpillar"](random.Random(1), {"n": 1}))
    assert n1 == 1 and e1 == []
    n2, e2 = _parse_n_edges(adversaries.SHAPES["caterpillar"](random.Random(1), {"n": 2}))
    assert n2 == 2 and len(e2) == 1


# ---------------------------------------------------------------------------
# anti_dijkstra
# ---------------------------------------------------------------------------


def test_anti_dijkstra_dense_and_weighted():
    text = adversaries.SHAPES["anti_dijkstra"](random.Random(2), {"n": 50})
    lines = [ln for ln in text.strip().split("\n") if ln]
    n = int(lines[0])
    m = int(lines[1])
    edge_lines = lines[2:]
    assert n == 50
    assert len(edge_lines) == m
    # dense: default targets the complete graph
    assert m == n * (n - 1) // 2
    seen = set()
    for ln in edge_lines:
        u, v, w = (int(t) for t in ln.split())
        assert 1 <= u <= n and 1 <= v <= n and u != v
        assert w >= 1
        key = (min(u, v), max(u, v))
        assert key not in seen  # no duplicate edges
        seen.add(key)


# ---------------------------------------------------------------------------
# kmp_worst
# ---------------------------------------------------------------------------


def test_kmp_worst_shape():
    text = adversaries.SHAPES["kmp_worst"](random.Random(1), {"n": 1000, "m": 100})
    lines = text.strip().split("\n")
    assert len(lines) == 2
    text_line, pattern = lines
    assert len(text_line) == 1000
    assert text_line == "a" * 999 + "b"
    assert pattern == "a" * 99 + "b"


# ---------------------------------------------------------------------------
# Size cap (no OOM on an absurd n)
# ---------------------------------------------------------------------------


def test_adversary_size_cap():
    # A huge n must be clamped to MAX_N, not allocated whole.
    huge = 10**12
    text = adversaries.SHAPES["anti_hash"](random.Random(1), {"n": huge})
    count = int(text.split("\n", 1)[0])
    assert count == adversaries.MAX_N

    n, _ = _parse_perm(
        # cap also applies to the quicksort permutation; use a modest cap-test n
        adversaries.SHAPES["anti_quicksort"](random.Random(1), {"n": huge})
    )
    # we cannot afford to materialise MAX_N here, so just assert the header was
    # clamped rather than echoing the absurd request back.
    assert n == adversaries.MAX_N
