# Worst-case input constructors (Section 13.x — adversarial shapes).
#
# A "normal" random input rarely hits the pathological corner of an algorithm.
# These shapes deliberately engineer the corner: a permutation that makes a
# median-of-three quicksort go quadratic, integers that all collide in a
# power-of-two hash table, a degenerate caterpillar tree, a dense graph that
# stresses Dijkstra, and the classic kmp_worst string for naive substring
# search. They are plain shapes — `fn(rng, params) -> str` returning the INPUT
# text — registered into `shapes.SHAPES`. They produce inputs only and never
# read, compute, or write an expected answer; if such an input crashes a
# solution the signal is recorded later by `gen --expected` from the solution's
# own observed run, never here.
#
# Everything is deterministic given the random.Random and caps large n so a
# careless --param n=1e12 cannot exhaust memory.

import random

# A sane upper bound on emitted structure size. Big enough to provoke quadratic
# blow-ups on real solutions, small enough to never OOM the generator.
MAX_N = 2_000_000


def _capped_n(params, default, low=1):
    """Read n from params, coerce to int, and clamp to [low, MAX_N]."""
    n = int(params.get("n", default))
    if n < low:
        n = low
    if n > MAX_N:
        n = MAX_N
    return n


# ---------------------------------------------------------------------------
# anti_quicksort — the median-of-three / Bentley-McIlroy killer
# ---------------------------------------------------------------------------
#
# Builds a permutation of 1..n so that a quicksort choosing its pivot by the
# median of (first, middle, last) is forced into maximally unbalanced splits,
# i.e. about O(n^2) comparisons. This is M.D. McIlroy's "antiqsort" construction
# turned inside out: we decide the final array positions so that whenever the
# sorter looks at a median-of-three pivot it picks (nearly) the smallest
# remaining element. We assign values by simulating that adversarial choice.


def _anti_quicksort(rng, params):
    n = _capped_n(params, 100000)
    # a[i] is the value finally sitting at index i; -1 means "not yet decided".
    # We hand out the largest values to the pivot positions the sorter probes,
    # which keeps every partition lopsided.
    a = [-1] * n
    candidate = 0  # next "gas" value to assign to a probed pivot
    nsolid = 0  # how many real values we have committed so far

    def compare(x, y):
        # Called by the simulated sort when it compares a[x] vs a[y]. If either
        # is still undecided, decide it now: give it the next pivot value. This
        # is the trick — the comparator itself materialises the worst order.
        nonlocal candidate, nsolid
        if a[x] == -1 and a[y] == -1:
            if x == y:
                a[x] = candidate
                candidate += 1
            else:
                a[x] = candidate
                candidate += 1
                a[y] = candidate
                candidate += 1
            nsolid += 2 if x != y else 1
        elif a[x] == -1:
            a[x] = candidate
            candidate += 1
            nsolid += 1
        elif a[y] == -1:
            a[y] = candidate
            candidate += 1
            nsolid += 1
        return a[x] - a[y]

    def med3(lo, mid, hi):
        # Median of three by index, using the live comparator.
        if compare(lo, mid) < 0:
            if compare(mid, hi) < 0:
                return mid
            return hi if compare(lo, hi) < 0 else lo
        if compare(lo, hi) > 0:
            return lo
        return hi if compare(mid, hi) > 0 else mid

    # iterative driver so deep recursion on big n cannot blow the Python stack
    stack = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo <= 0:
            if lo == hi and a[lo] == -1:
                a[lo] = candidate
                candidate += 1
            continue
        p = med3(lo, (lo + hi) // 2, hi)
        for i in range(lo, hi + 1):
            if i != p and a[i] == -1:
                compare(i, p)
        stack.append(((lo + hi) // 2 + 1, hi))
        stack.append((lo, (lo + hi) // 2 - 1))

    # any cell still undecided gets the next value in order
    for i in range(n):
        if a[i] == -1:
            a[i] = candidate
            candidate += 1

    # values were handed out as 0..n-1; remap to a clean permutation of 1..n
    # by rank so the output is exactly 1..n in the adversarial order.
    order = sorted(range(n), key=lambda i: a[i])
    perm = [0] * n
    for rank, idx in enumerate(order, start=1):
        perm[idx] = rank

    lines = [str(n)] + [str(x) for x in perm]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# anti_hash — integers that all land in one bucket of a power-of-two table
# ---------------------------------------------------------------------------
#
# A simple open-addressing or chaining hash table sized to a power of two often
# buckets a key by `key & (size - 1)` (the low k bits). If every key shares the
# same low k bits they all collide, degrading lookups to O(n). We emit n such
# integers: pick a random residue and stride, then space the keys by multiples
# of 2^bits so the low `bits` bits never change.


def _anti_hash(rng, params):
    n = _capped_n(params, 100000)
    bits = int(params.get("bits", 20))  # collide on this many low bits
    bits = max(1, min(bits, 40))
    base = int(params.get("base", rng.randrange(1 << bits)))
    base &= (1 << bits) - 1  # the shared low-bit residue
    step = 1 << bits
    nums = [base + i * step for i in range(n)]
    lines = [str(n)] + [str(x) for x in nums]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# caterpillar — a degenerate tree: a long spine with leaves hanging off it
# ---------------------------------------------------------------------------
#
# A caterpillar is a tree that becomes a path once its leaves are removed. It is
# a nasty depth/diameter case for naive recursion and a poor case for many tree
# DP / LCA preprocessors. Emit n on the first line, then n-1 edges 'u v'. Half
# the nodes form the spine; the rest hang as leaves off random spine nodes.


def _caterpillar(rng, params):
    n = _capped_n(params, 100000, low=1)
    edges = []
    if n >= 2:
        spine_len = max(2, n // 2)
        spine_len = min(spine_len, n)
        # spine: nodes 1..spine_len chained
        for i in range(1, spine_len):
            edges.append((i, i + 1))
        # leaves: every remaining node attaches to a random spine node
        for leaf in range(spine_len + 1, n + 1):
            spine_node = rng.randint(1, spine_len)
            edges.append((spine_node, leaf))
    lines = [str(n)] + [f"{u} {v}" for u, v in edges]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# anti_dijkstra — a dense graph to stress shortest-path implementations
# ---------------------------------------------------------------------------
#
# A dense weighted graph: many edges relative to nodes, so an array-scan
# Dijkstra goes O(n^2) and a binary-heap Dijkstra does O(m log n) work with a
# large m. Emit 'n', then 'm', then m weighted edges 'u v w'. We first lay a
# random spanning tree (so the graph is connected) then pack in extra edges up
# to a dense target.


def _anti_dijkstra(rng, params):
    n = _capped_n(params, 2000, low=1)
    w_lo = int(params.get("w_lo", 1))
    w_hi = int(params.get("w_hi", 1_000_000_000))
    if w_hi < w_lo:
        w_lo, w_hi = w_hi, w_lo

    # target edge count: dense by default (~half of the complete graph), capped
    max_edges = n * (n - 1) // 2
    target = int(params.get("m", max_edges))
    if target > max_edges:
        target = max_edges
    if target < max(0, n - 1):
        target = max(0, n - 1)

    seen = set()
    edges = []

    def add(u, v):
        key = (min(u, v), max(u, v))
        if u != v and key not in seen:
            seen.add(key)
            edges.append((u, v))
            return True
        return False

    # spanning tree for connectivity
    if n > 1:
        order = list(range(1, n + 1))
        rng.shuffle(order)
        for i in range(1, n):
            add(order[i - 1], order[i])

    # pack remaining edges toward the dense target. When the target is the whole
    # complete graph, enumerate it directly rather than rejection-sampling.
    if target >= max_edges:
        for u in range(1, n + 1):
            for v in range(u + 1, n + 1):
                add(u, v)
    else:
        attempts = 0
        budget = (target - len(edges)) * 20 + 100
        while len(edges) < target and attempts < budget:
            attempts += 1
            add(rng.randint(1, n), rng.randint(1, n))

    m = len(edges)
    lines = [str(n), str(m)]
    lines += [f"{u} {v} {rng.randint(w_lo, w_hi)}" for u, v in edges]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# kmp_worst — worst case for naive (non-KMP) substring search
# ---------------------------------------------------------------------------
#
# Naive search of pattern in text backtracks the most when the two share long
# repeated prefixes. The classic worst case is a text of repeated 'a' with a
# single trailing 'b' searched for a pattern 'aa..ab': every alignment matches
# the run of 'a's and only fails at the last char. Emit the text then the
# pattern, one per line.


def _kmp_worst(rng, params):
    n = _capped_n(params, 100000)  # text length
    m = int(params.get("m", max(2, n // 2)))  # pattern length
    if m < 1:
        m = 1
    if m > n:
        m = n
    text = "a" * (n - 1) + "b"
    pattern = "a" * (m - 1) + "b"
    return text + "\n" + pattern


# ---------------------------------------------------------------------------
# Public registry — name -> fn(rng, params) -> str
# ---------------------------------------------------------------------------

SHAPES = {
    "anti_quicksort": _anti_quicksort,
    "anti_hash": _anti_hash,
    "caterpillar": _caterpillar,
    "anti_dijkstra": _anti_dijkstra,
    "kmp_worst": _kmp_worst,
}


def generate(shape, seed, params):
    """Convenience: build one adversarial input from a seed (mirrors shapes.generate)."""
    if shape not in SHAPES:
        known = ", ".join(sorted(SHAPES))
        raise ValueError(f"Unknown adversary '{shape}'. Known: {known}.")
    return SHAPES[shape](random.Random(seed), params)
