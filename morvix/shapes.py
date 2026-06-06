# Built-in random-data shape library (Section 13.2).
#
# Common input shapes so you do not write a generator from scratch for trivial
# cases. Everything is seeded for reproducibility. Shapes are composable
# building blocks; the list is meant to grow.
#
# API:
#   list_shapes() -> list[str]
#   generate(shape: str, seed: int, params: dict) -> str   # the input text
#   SHAPES: dict[str, callable]   # name -> fn(rng: random.Random, params: dict) -> str

import random
import string

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lo_hi(params):
    return params.get("lo", 0), params.get("hi", 1_000_000)


def _apply_layout(nums, layout, rng):
    """Sort or shuffle a list of ints according to the requested layout."""
    if layout == "sorted":
        return sorted(nums)
    if layout == "reverse":
        return sorted(nums, reverse=True)
    if layout == "nearly_sorted":
        nums = sorted(nums)
        # swap a small number of adjacent pairs
        swaps = max(1, len(nums) // 10)
        for _ in range(swaps):
            i = rng.randrange(len(nums) - 1)
            nums[i], nums[i + 1] = nums[i + 1], nums[i]
        return nums
    if layout == "all_equal":
        v = nums[0] if nums else 0
        return [v] * len(nums)
    # default: random (already random from generation)
    return nums


# ---------------------------------------------------------------------------
# Shape functions — each returns the full input text as a string
# ---------------------------------------------------------------------------


def _shape_int(rng, params):
    lo, hi = _lo_hi(params)
    return str(rng.randint(lo, hi))


def _shape_ints(rng, params):
    lo, hi = _lo_hi(params)
    if "count" in params:
        n = int(params["count"])
    else:
        min_n = params.get("min_n", 1)
        max_n = params.get("max_n", 100)
        n = rng.randint(int(min_n), int(max_n))
    layout = params.get("layout", "random")
    nums = [rng.randint(lo, hi) for _ in range(n)]
    nums = _apply_layout(nums, layout, rng)
    lines = [str(n)] + [str(x) for x in nums]
    return "\n".join(lines)


def _shape_array(rng, params):
    lo, hi = _lo_hi(params)
    count = int(params.get("count", rng.randint(1, 100)))
    nums = [rng.randint(lo, hi) for _ in range(count)]
    return " ".join(str(x) for x in nums)


def _shape_string(rng, params):
    length = int(params.get("length", rng.randint(1, 100)))
    alphabet = params.get("alphabet", string.ascii_lowercase)
    return "".join(rng.choice(alphabet) for _ in range(length))


def _shape_permutation(rng, params):
    lo, hi = _lo_hi(params)
    n = int(params.get("n", rng.randint(1, 100)))
    perm = list(range(1, n + 1))
    rng.shuffle(perm)
    lines = [str(n)] + [str(x) for x in perm]
    return "\n".join(lines)


def _shape_tree(rng, params):
    """n on first line, then n-1 edges. shape in {random,path,star,by_degree}."""
    lo, hi = _lo_hi(params)
    n = int(params.get("n", rng.randint(2, 100)))
    tree_shape = params.get("shape", "random")
    edges = []

    if tree_shape == "path":
        # - nodes 1..n connected in a chain
        for i in range(1, n):
            edges.append((i, i + 1))
    elif tree_shape == "star":
        # - node 1 is the centre
        for i in range(2, n + 1):
            edges.append((1, i))
    elif tree_shape == "by_degree":
        # - attach each new node to one already placed, biased toward high-degree nodes
        degree = [0] * (n + 1)
        for i in range(2, n + 1):
            pool = list(range(1, i))
            weights = [degree[v] + 1 for v in pool]
            total = sum(weights)
            r = rng.uniform(0, total)
            cumulative = 0
            parent = pool[-1]
            for v, w in zip(pool, weights):
                cumulative += w
                if r <= cumulative:
                    parent = v
                    break
            degree[parent] += 1
            degree[i] += 1
            edges.append((parent, i))
    else:
        # random Prüfer-style: attach each new node to a random existing one
        for i in range(2, n + 1):
            parent = rng.randint(1, i - 1)
            edges.append((parent, i))

    lines = [str(n)] + [f"{u} {v}" for u, v in edges]
    return "\n".join(lines)


def _shape_graph(rng, params):
    """n m on first line then m edges. Supports directed, weighted, connected, dag."""
    lo, hi = _lo_hi(params)
    n = int(params.get("n", rng.randint(2, 20)))
    directed = bool(params.get("directed", False))
    weighted = bool(params.get("weighted", False))
    connected = bool(params.get("connected", True))
    dag = bool(params.get("dag", False))
    w_lo = int(params.get("w_lo", 1))
    w_hi = int(params.get("w_hi", 100))

    edge_set = set()
    edge_list = []

    def add_edge(u, v):
        key = (u, v) if directed else (min(u, v), max(u, v))
        if key not in edge_set:
            edge_set.add(key)
            edge_list.append((u, v))

    # ensure connectivity via a random spanning tree
    if connected and n > 1:
        order = list(range(1, n + 1))
        rng.shuffle(order)
        for i in range(1, n):
            u, v = order[i - 1], order[i]
            if dag:
                add_edge(min(u, v), max(u, v))
            else:
                add_edge(u, v)

    # add extra random edges
    default_m = int(params.get("m", rng.randint(n - 1, min(n * (n - 1) // 2, n + 10))))
    attempts = 0
    while len(edge_list) < default_m and attempts < default_m * 10:
        attempts += 1
        u = rng.randint(1, n)
        v = rng.randint(1, n)
        if u == v:
            continue
        if dag:
            u, v = min(u, v), max(u, v)
        add_edge(u, v)

    m = len(edge_list)
    if weighted:
        lines = [f"{n} {m}"] + [f"{u} {v} {rng.randint(w_lo, w_hi)}" for u, v in edge_list]
    else:
        lines = [f"{n} {m}"] + [f"{u} {v}" for u, v in edge_list]
    return "\n".join(lines)


def _shape_grid(rng, params):
    rows = int(params.get("rows", rng.randint(1, 10)))
    cols = int(params.get("cols", rng.randint(1, 10)))
    alphabet = list(params.get("alphabet", ".#"))
    grid_lines = ["".join(rng.choice(alphabet) for _ in range(cols)) for _ in range(rows)]
    header = f"{rows} {cols}"
    return "\n".join([header] + grid_lines)


def _shape_edge(rng, params):
    """Named edge-case templates — emit a minimal or extreme input."""
    # - kind: empty, single, max, all_equal, boundary
    kind = params.get("kind", "single")
    lo, hi = _lo_hi(params)
    n = int(params.get("n", 10))

    if kind == "empty":
        return "0"
    if kind == "single":
        return f"1\n{lo}"
    if kind == "max":
        nums = [hi] * n
        return str(n) + "\n" + "\n".join(str(x) for x in nums)
    if kind == "all_equal":
        v = (lo + hi) // 2
        nums = [v] * n
        return str(n) + "\n" + "\n".join(str(x) for x in nums)
    if kind == "boundary":
        # alternating lo and hi
        nums = [lo if i % 2 == 0 else hi for i in range(n)]
        return str(n) + "\n" + "\n".join(str(x) for x in nums)
    raise ValueError(
        f"Unknown edge kind '{kind}'. Choose: empty, single, max, all_equal, boundary."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SHAPES = {
    "int": _shape_int,
    "ints": _shape_ints,
    "array": _shape_array,
    "string": _shape_string,
    "permutation": _shape_permutation,
    "tree": _shape_tree,
    "graph": _shape_graph,
    "grid": _shape_grid,
    "edge": _shape_edge,
}


def list_shapes():
    return sorted(SHAPES)


def generate(shape, seed, params):
    if shape not in SHAPES:
        known = ", ".join(sorted(SHAPES))
        raise ValueError(f"Unknown shape '{shape}'. Known shapes: {known}.")
    rng = random.Random(seed)
    return SHAPES[shape](rng, params)
