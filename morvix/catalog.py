# A catalog of vetted named generators (Section 13).
#
# The combinator library (genlib.py) is powerful but unstructured; the catalog
# is a curated shelf of ready-made generators built on it - "tree.binary",
# "graph.dag", "seq.parens" - each with named, documented parameters. An author
# picks one by name, passes a seed and a few params, and gets one valid input.
# Browse with gen --list-lib; produce with gen --lib NAME.
#
# Each entry's builder is a (Gen, params) -> str function; the catalog resolves
# params (coercing and defaulting) before calling it, so a builder sees clean,
# typed values. Entries are vetted to produce structurally-valid inputs.
#
# HONESTY: a catalog entry produces INPUT text only. No entry reads, computes,
# or writes an expected answer; answers come only from gen --expected.

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from morvix.genlib import Gen, GenError, header, lines, tokens


@dataclass(frozen=True)
class Param:
    """One declared parameter of a catalog entry: name, type, default, help."""

    name: str
    type: str = "int"  # "int" | "str" | "bool"
    default: object = None
    help: str = ""


@dataclass(frozen=True)
class CatalogEntry:
    """A named generator: how to describe it and how to build one input."""

    name: str
    summary: str
    params: List[Param]
    build: Callable[[Gen, dict], str] = field(repr=False)


CATALOG: Dict[str, CatalogEntry] = {}


# ---------------------------------------------------------------------------
# Registry API
# ---------------------------------------------------------------------------


def register(entry: CatalogEntry) -> CatalogEntry:
    """Add an entry to the catalog (later registration overrides an earlier name)."""
    CATALOG[entry.name] = entry
    return entry


def list_entries() -> List[CatalogEntry]:
    """Every catalog entry, sorted by name."""
    return [CATALOG[name] for name in sorted(CATALOG)]


def get(name: str) -> CatalogEntry:
    """The entry called name, or a GenError naming the close-by alternatives."""
    if name not in CATALOG:
        known = ", ".join(sorted(CATALOG))
        raise GenError(f"Unknown catalog generator '{name}'. Known: {known}.")
    return CATALOG[name]


def describe(name: str) -> str:
    """A one-paragraph description of an entry and its parameters."""
    entry = get(name)
    out = [f"{entry.name}: {entry.summary}"]
    for p in entry.params:
        default = "" if p.default is None else f" (default {p.default})"
        suffix = f" - {p.help}" if p.help else ""
        out.append(f"  {p.name}: {p.type}{default}{suffix}")
    return "\n".join(out)


def generate(name: str, seed: int, params: dict) -> str:
    """Build one input from the named generator. Returns INPUT text only."""
    entry = get(name)
    resolved = _resolve_params(entry, params or {})
    gen = Gen(rng=random.Random(seed))
    return entry.build(gen, resolved)


def _resolve_params(entry: CatalogEntry, params: dict) -> dict:
    """Coerce supplied params against the entry's declared types; fill defaults."""
    declared = {p.name: p for p in entry.params}
    resolved = {p.name: p.default for p in entry.params}
    for key, value in params.items():
        if key not in declared:
            known = ", ".join(declared) or "(none)"
            raise GenError(f"Generator '{entry.name}' has no param '{key}'. Params: {known}.")
        resolved[key] = _coerce(value, declared[key])
    return resolved


def _coerce(value, param: Param):
    """Turn a string/CLI value into the param's declared type."""
    if param.type == "int":
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            raise GenError(f"Param '{param.name}' must be an integer (got {value!r}).") from e
    if param.type == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    return str(value)


# ---------------------------------------------------------------------------
# Vetted entries
# ---------------------------------------------------------------------------
#
# Each builder emits one valid input. Trees/graphs print n (and m) then the
# edges; sequences print the sequence. Sizes are read from resolved params.


def _b_tree_binary(gen: Gen, p: dict) -> str:
    n = p["n"]
    edges = gen.tree(n, kind="binary")
    return lines([n] + [header(u, v) for u, v in edges])


def _b_tree_caterpillar(gen: Gen, p: dict) -> str:
    n = p["n"]
    edges = gen.tree(n, kind="caterpillar")
    return lines([n] + [header(u, v) for u, v in edges])


def _b_tree_random(gen: Gen, p: dict) -> str:
    n = p["n"]
    edges = gen.tree(n, kind="random")
    return lines([n] + [header(u, v) for u, v in edges])


def _b_tree_path(gen: Gen, p: dict) -> str:
    n = p["n"]
    edges = gen.tree(n, kind="path")
    return lines([n] + [header(u, v) for u, v in edges])


def _b_graph_dag(gen: Gen, p: dict) -> str:
    n = p["n"]
    edges = gen.graph(n, p["m"], directed=True, connected=p["connected"], dag=True)
    rendered = [header(n, len(edges))] + [header(u, v) for u, v in edges]
    return lines(rendered)


def _b_graph_connected(gen: Gen, p: dict) -> str:
    n = p["n"]
    edges = gen.graph(n, p["m"], connected=True)
    rendered = [header(n, len(edges))] + [header(u, v) for u, v in edges]
    return lines(rendered)


def _b_seq_parens(gen: Gen, p: dict) -> str:
    # A balanced parenthesis string of n pairs (length 2n), built so every
    # prefix has at least as many '(' as ')' - correct-by-construction balance.
    n = p["n"]
    out = []
    open_left = n  # '(' still to place
    open_now = 0  # currently unmatched '('
    for _ in range(2 * n):
        # we may open if any left; we may close if something is open. Choose
        # randomly among the legal moves so the string is non-trivial.
        can_open = open_left > 0
        can_close = open_now > 0
        if can_open and (not can_close or gen.int_(0, 1) == 0):
            out.append("(")
            open_left -= 1
            open_now += 1
        else:
            out.append(")")
            open_now -= 1
    return "".join(out)


def _b_seq_perm(gen: Gen, p: dict) -> str:
    n = p["n"]
    return lines([n, tokens(gen.perm(n))])


def _b_seq_ints(gen: Gen, p: dict) -> str:
    n = p["n"]
    return lines([n, tokens(gen.ints(n, p["lo"], p["hi"]))])


def _b_grid_random(gen: Gen, p: dict) -> str:
    rows, cols = p["rows"], p["cols"]
    rendered = [header(rows, cols)] + gen.grid(rows, cols, p["alphabet"])
    return lines(rendered)


# Register the curated shelf.
register(
    CatalogEntry(
        name="tree.binary",
        summary="a complete binary tree on n nodes (parent of i is i//2)",
        params=[Param("n", "int", 15, "number of nodes")],
        build=_b_tree_binary,
    )
)
register(
    CatalogEntry(
        name="tree.caterpillar",
        summary="a caterpillar tree: a spine with leaves hanging off it",
        params=[Param("n", "int", 20, "number of nodes")],
        build=_b_tree_caterpillar,
    )
)
register(
    CatalogEntry(
        name="tree.random",
        summary="a uniform-ish random tree on n nodes",
        params=[Param("n", "int", 20, "number of nodes")],
        build=_b_tree_random,
    )
)
register(
    CatalogEntry(
        name="tree.path",
        summary="a path (line) graph on n nodes - the deepest tree",
        params=[Param("n", "int", 20, "number of nodes")],
        build=_b_tree_path,
    )
)
register(
    CatalogEntry(
        name="graph.dag",
        summary="a connected directed acyclic graph (edges point low->high)",
        params=[
            Param("n", "int", 10, "number of nodes"),
            Param("m", "int", 20, "target number of edges"),
            Param("connected", "bool", True, "lay a spanning tree first"),
        ],
        build=_b_graph_dag,
    )
)
register(
    CatalogEntry(
        name="graph.connected",
        summary="a connected undirected simple graph on n nodes",
        params=[
            Param("n", "int", 10, "number of nodes"),
            Param("m", "int", 20, "target number of edges"),
        ],
        build=_b_graph_connected,
    )
)
register(
    CatalogEntry(
        name="seq.parens",
        summary="a balanced parenthesis string of n pairs (correct by construction)",
        params=[Param("n", "int", 8, "number of '()' pairs")],
        build=_b_seq_parens,
    )
)
register(
    CatalogEntry(
        name="seq.perm",
        summary="n on a line, then a random permutation of 1..n",
        params=[Param("n", "int", 10, "permutation size")],
        build=_b_seq_perm,
    )
)
register(
    CatalogEntry(
        name="seq.ints",
        summary="n on a line, then n integers in [lo, hi]",
        params=[
            Param("n", "int", 10, "how many integers"),
            Param("lo", "int", 0, "minimum value"),
            Param("hi", "int", 1000000, "maximum value"),
        ],
        build=_b_seq_ints,
    )
)
register(
    CatalogEntry(
        name="grid.random",
        summary="a rows x cols character grid over an alphabet (default '.#')",
        params=[
            Param("rows", "int", 5, "number of rows"),
            Param("cols", "int", 5, "number of columns"),
            Param("alphabet", "str", ".#", "characters to draw from"),
        ],
        build=_b_grid_random,
    )
)
