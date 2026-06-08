# Seeded combinator library for generators (Section 13).
#
# When a built-in shape is too rigid but a full generator program is overkill,
# an author reaches for these combinators. They are small, composable building
# blocks - draw an int, an array, a permutation, a tree, a graph, a grid, a
# matrix - plus a handful of combinators (seq/oneof/repeat/constrain/weighted)
# and renderers (render/lines/tokens/header/write) that turn structure into the
# exact input text a program reads.
#
# Everything is seeded and deterministic: a Gen wraps one random.Random, so the
# same seed always reproduces the same input. This is the lower layer the
# catalog (catalog.py) is built on, and the layer shapes.py delegates to.
#
# HONESTY: this module produces INPUTS only. Nothing here reads, computes, or
# writes an expected answer; expected answers come only from gen --expected
# running the solution.

import random
import string
from typing import Callable, List, Optional, Sequence, Union


class GenError(ValueError):
    """Misuse of a combinator: a bad bound, an empty choice, a negative count."""


# A value rendered into input text: a string, a number, or a nested list of them.
Value = Union[str, int, float, list, tuple]


# ---------------------------------------------------------------------------
# Rendering helpers (free functions, usable without a Gen)
# ---------------------------------------------------------------------------


def tokens(items: Sequence, sep: str = " ") -> str:
    """Join items into a single whitespace-separated line, e.g. an array row."""
    return sep.join(_render_token(x) for x in items)


def lines(items: Sequence) -> str:
    """Join items into separate lines (each item rendered as one token)."""
    return "\n".join(_render_token(x) for x in items)


def header(*parts) -> str:
    """A header line, e.g. header(n, m) -> 'n m'. Numbers and strings allowed."""
    return " ".join(_render_token(p) for p in parts)


def render(value: Value, sep: str = " ") -> str:
    """Render any value to input text.

    - a str is returned as-is,
    - a scalar (int/float) becomes its string,
    - a flat list/tuple of scalars becomes a space-joined line,
    - a list of lists becomes one line per row (each row space-joined).
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return _render_token(value)
    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], (list, tuple)):
            return "\n".join(tokens(row, sep) for row in value)
        return tokens(value, sep)
    raise GenError(f"Cannot render value of type {type(value).__name__}.")


def write(path: str, text: str) -> str:
    """Write rendered input text to a file (utf-8); return the path.

    A trailing newline is ensured so concatenated inputs stay line-clean.
    """
    if not text.endswith("\n"):
        text = text + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _render_token(x) -> str:
    if isinstance(x, bool):  # guard: bool is an int subclass, render as 0/1
        return "1" if x else "0"
    if isinstance(x, float):
        # keep integral floats clean (3.0 -> "3"); otherwise plain repr-ish
        return str(int(x)) if x.is_integer() else repr(x)
    return str(x)


# ---------------------------------------------------------------------------
# Gen: a seeded source of structures
# ---------------------------------------------------------------------------


class Gen:
    """A seeded random source with combinators for building inputs.

    Construct from a seed (Gen(7)) or wrap an existing random.Random
    (Gen(rng=my_rng)). Every method draws from the one underlying generator, so
    a fixed seed reproduces the whole input byte-for-byte.
    """

    def __init__(self, seed: Optional[int] = None, rng: Optional[random.Random] = None):
        if rng is not None:
            self.rng = rng
        else:
            self.rng = random.Random(seed if seed is not None else 0)

    # --- scalars -----------------------------------------------------------

    def int_(self, lo: int, hi: int) -> int:
        """A random integer in [lo, hi] (inclusive)."""
        lo, hi = int(lo), int(hi)
        if hi < lo:
            raise GenError(f"int_: empty range [{lo}, {hi}].")
        return self.rng.randint(lo, hi)

    def float_(self, lo: float, hi: float, ndigits: int = 6) -> float:
        """A random float in [lo, hi], rounded to ndigits decimals."""
        if hi < lo:
            raise GenError(f"float_: empty range [{lo}, {hi}].")
        return round(self.rng.uniform(lo, hi), int(ndigits))

    def char(self, alphabet: str = string.ascii_lowercase) -> str:
        """One random character from alphabet."""
        if not alphabet:
            raise GenError("char: empty alphabet.")
        return self.rng.choice(alphabet)

    # --- collections -------------------------------------------------------

    def ints(self, n: int, lo: int, hi: int) -> List[int]:
        """A list of n random integers, each in [lo, hi]."""
        n = _check_count(n, "ints")
        return [self.int_(lo, hi) for _ in range(n)]

    def array(self, n: int, lo: int = 0, hi: int = 1_000_000) -> List[int]:
        """An array of n integers in [lo, hi] (a friendlier alias for ints)."""
        return self.ints(n, lo, hi)

    def string(self, length: int, alphabet: str = string.ascii_lowercase) -> str:
        """A random string of the given length over alphabet."""
        length = _check_count(length, "string")
        if not alphabet:
            raise GenError("string: empty alphabet.")
        return "".join(self.rng.choice(alphabet) for _ in range(length))

    def perm(self, n: int, start: int = 1) -> List[int]:
        """A random permutation of n consecutive integers starting at start."""
        n = _check_count(n, "perm")
        out = list(range(start, start + n))
        self.rng.shuffle(out)
        return out

    def matrix(self, rows: int, cols: int, lo: int = 0, hi: int = 1_000_000) -> List[List[int]]:
        """A rows x cols matrix of integers in [lo, hi]."""
        rows = _check_count(rows, "matrix(rows)")
        cols = _check_count(cols, "matrix(cols)")
        return [self.ints(cols, lo, hi) for _ in range(rows)]

    def grid(self, rows: int, cols: int, alphabet: str = ".#") -> List[str]:
        """A rows x cols character grid (one string per row) over alphabet."""
        rows = _check_count(rows, "grid(rows)")
        cols = _check_count(cols, "grid(cols)")
        if not alphabet:
            raise GenError("grid: empty alphabet.")
        return [self.string(cols, alphabet) for _ in range(rows)]

    # --- structures: trees and graphs --------------------------------------
    #
    # Edges are returned as a list of (u, v) pairs over nodes 1..n. The caller
    # renders them (the catalog typically prints n then the edges). A tree on n
    # nodes has exactly n-1 edges and is connected by construction.

    def tree(self, n: int, kind: str = "random") -> List[tuple]:
        """n-1 edges of a tree on nodes 1..n. kind in {random,path,star,binary,
        caterpillar,by_degree}."""
        n = _check_count(n, "tree")
        if n <= 1:
            return []
        if kind == "path":
            return [(i, i + 1) for i in range(1, n)]
        if kind == "star":
            return [(1, i) for i in range(2, n + 1)]
        if kind == "binary":
            # node i's parent is i // 2: a complete binary tree by index.
            return [(i // 2, i) for i in range(2, n + 1)]
        if kind == "caterpillar":
            return self._caterpillar(n)
        if kind == "by_degree":
            return self._tree_by_degree(n)
        if kind == "random":
            return [(self.int_(1, i - 1), i) for i in range(2, n + 1)]
        raise GenError(
            f"tree: unknown kind '{kind}'. "
            "Choose: random, path, star, binary, caterpillar, by_degree."
        )

    def graph(
        self,
        n: int,
        m: Optional[int] = None,
        *,
        directed: bool = False,
        connected: bool = True,
        dag: bool = False,
    ) -> List[tuple]:
        """Up to m edges of a simple graph on nodes 1..n.

        With connected=True a random spanning tree is laid first so the graph is
        connected; with dag=True every edge points low->high so the result is
        acyclic. Returns the edge list; the caller renders n/m and the edges.
        """
        n = _check_count(n, "graph")
        max_edges = n * (n - 1) // 2 if not directed else n * (n - 1)
        if m is None:
            m = min(max_edges, n + 10) if n > 1 else 0
        m = int(m)
        if m < 0:
            raise GenError("graph: negative edge count.")
        if m > max_edges:
            m = max_edges

        seen = set()
        edges: List[tuple] = []

        def add(u, v):
            if u == v:
                return False
            if dag:
                u, v = min(u, v), max(u, v)
            key = (u, v) if directed else (min(u, v), max(u, v))
            if key in seen:
                return False
            seen.add(key)
            edges.append((u, v))
            return True

        if connected and n > 1:
            order = list(range(1, n + 1))
            self.rng.shuffle(order)
            for i in range(1, n):
                add(order[i - 1], order[i])

        attempts = 0
        budget = max(100, (m - len(edges)) * 20)
        while len(edges) < m and attempts < budget:
            attempts += 1
            add(self.int_(1, n), self.int_(1, n))
        return edges

    # --- combinators -------------------------------------------------------

    def oneof(self, choices: Sequence):
        """Pick one element of choices uniformly at random."""
        choices = list(choices)
        if not choices:
            raise GenError("oneof: no choices.")
        return self.rng.choice(choices)

    def weighted(self, choices: Sequence, weights: Sequence[float]):
        """Pick one element of choices with the given relative weights."""
        choices = list(choices)
        weights = list(weights)
        if not choices:
            raise GenError("weighted: no choices.")
        if len(choices) != len(weights):
            raise GenError("weighted: choices and weights differ in length.")
        if any(w < 0 for w in weights) or sum(weights) <= 0:
            raise GenError("weighted: weights must be non-negative and sum to > 0.")
        return self.rng.choices(choices, weights=weights, k=1)[0]

    def repeat(self, n: int, fn: Callable[[], object]) -> list:
        """Call fn() n times, collecting the results (fn draws from this Gen)."""
        n = _check_count(n, "repeat")
        return [fn() for _ in range(n)]

    def seq(self, *parts) -> str:
        """Render a sequence of parts into newline-joined text.

        Each part may be a string (used as-is), a scalar, or a list; callables
        are invoked first so 'lazy' parts draw from this Gen at render time.
        """
        out = []
        for p in parts:
            if callable(p):
                p = p()
            out.append(render(p))
        return "\n".join(out)

    def constrain(self, fn: Callable[[], object], ok: Callable[[object], bool], tries: int = 1000):
        """Resample fn() until ok(result) holds; raise if tries is exhausted.

        Useful for "an array with no duplicates" or "a connected graph": express
        the constraint as a predicate rather than constructing it by hand.
        """
        for _ in range(int(tries)):
            value = fn()
            if ok(value):
                return value
        raise GenError(f"constrain: no value satisfied the predicate in {tries} tries.")

    # --- internal tree builders -------------------------------------------

    def _caterpillar(self, n: int) -> List[tuple]:
        edges: List[tuple] = []
        spine = max(2, n // 2)
        spine = min(spine, n)
        for i in range(1, spine):
            edges.append((i, i + 1))
        for leaf in range(spine + 1, n + 1):
            edges.append((self.int_(1, spine), leaf))
        return edges

    def _tree_by_degree(self, n: int) -> List[tuple]:
        # Attach each new node to an existing one, biased toward high degree, so
        # the tree grows lopsided (a stress shape for tree algorithms).
        degree = [0] * (n + 1)
        edges: List[tuple] = []
        for i in range(2, n + 1):
            pool = list(range(1, i))
            weights = [degree[v] + 1 for v in pool]
            parent = self.weighted(pool, weights)
            degree[parent] += 1
            degree[i] += 1
            edges.append((parent, i))
        return edges


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _check_count(n, where: str) -> int:
    n = int(n)
    if n < 0:
        raise GenError(f"{where}: count must be >= 0 (got {n}).")
    return n
