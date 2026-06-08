# Suite hygiene: drop duplicate cases, and recognise the same graph in disguise.
#
# Two jobs, both about not keeping redundant inputs:
#   - dedup_pool removes byte-identical GENERATED cases (random shapes often
#     collide on small inputs), keeping the first and never touching a manual
#     case. It content-addresses each input so the comparison is cheap and exact.
#   - canonical_graph_key answers "are these two graphs the same up to renaming
#     the vertices?" with a Weisfeiler-Lehman colour refinement. It powers the
#     structural '--diversity graph-iso' knob, where exact byte-dedup is too weak
#     (a path written 1-2-3 and 3-2-1 are the same shape but different bytes).
#
# Honesty: this module only reads INPUT bytes and graph structure. It never
# reads, writes, or reasons about an expected answer.

import os
from collections import Counter
from typing import List, Set

from morvix import provenance


def content_hash(data) -> str:
    """The sha256 hex digest of some bytes (str is encoded utf-8 first)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return provenance.hash_bytes(data)


def existing_input_hashes(project) -> Set[str]:
    """The set of input hashes already present in the project's cases.

    Uses each case's stored input_hash when set, else computes it from the
    primary input file. Cases with no input contribute nothing.
    """
    hashes: Set[str] = set()
    for case in project.cases:
        h = case.input_hash or provenance.compute_input_hash(case, project.root)
        if h:
            hashes.add(h)
    return hashes


def dedup_pool(project, group=None) -> int:
    """Remove byte-identical GENERATED cases, keeping the first of each input.

    Manual cases are never removed (they are permanent and may legitimately
    duplicate a generated input). Optionally restricted to a single group. The
    removed cases' input files are deleted from disk. Returns how many cases
    were removed. The caller is responsible for saving the project.
    """
    seen: Set[str] = set()
    kept: List = []
    removed = 0
    for case in project.cases:
        # Manual cases and cases outside the target group are always kept, and a
        # manual case still seeds 'seen' so a later generated twin is pruned.
        in_scope = (group is None or case.group == group) and not case.manual
        h = case.input_hash or provenance.compute_input_hash(case, project.root)
        if not in_scope or h is None:
            if h is not None:
                seen.add(h)
            kept.append(case)
            continue
        if h in seen:
            _delete_inputs(project, case)
            removed += 1
            continue
        seen.add(h)
        kept.append(case)
    project.cases = kept
    return removed


def _delete_inputs(project, case) -> None:
    """Delete a case's input files from disk (best-effort)."""
    for rel in case.inputs.values():
        path = os.path.join(project.root, rel)
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Weisfeiler-Lehman canonical graph key
# ---------------------------------------------------------------------------
#
# The 1-WL colour refinement: start every vertex at the same colour, then
# repeatedly recolour each vertex by hashing (its colour, the sorted multiset of
# its neighbours' colours). After n rounds the colours stabilise; the sorted
# multiset of final colours is a relabelling-invariant signature. It is a strong
# (not perfect) graph invariant - more than enough to tell a path from a star and
# to fold away vertex renamings, which is all '--diversity graph-iso' needs.


def canonical_graph_key(text: str, is_tree: bool) -> str:
    """A relabelling-invariant key for a graph/tree given as 'n' then 'u v' lines.

    Same key => almost certainly isomorphic (WL is a strong heuristic, not a
    proof). Distinguishes a path from a star; identical for any renaming of the
    vertices. 'is_tree' is accepted for caller symmetry (trees are just graphs
    here) and does not change the computed key.
    """
    n, adj = _parse_graph(text)
    if n <= 0:
        return f"wl:n={n}:m=0:[]"

    # Start all vertices at the same colour, then refine for n rounds.
    colours = [1] * n
    for _ in range(n):
        new = []
        for v in range(n):
            sig = (colours[v], tuple(sorted(colours[u] for u in adj[v])))
            new.append(sig)
        # Compress the round's signatures to small dense integers so the next
        # round's hashing stays cheap and order-independent.
        ranking = {sig: i for i, sig in enumerate(sorted(set(new)))}
        colours = [ranking[sig] for sig in new]

    edges = sum(len(a) for a in adj) // 2
    histogram = sorted(Counter(colours).items())
    return f"wl:n={n}:m={edges}:{histogram}"


def _parse_graph(text: str):
    """Parse 'n' then edge lines 'u v' into (n, adjacency-lists).

    Vertices are taken as 1..n and stored 0-indexed. Self-loops and lines that
    are not two integers are ignored; an edge is undirected and de-duplicated.
    """
    tokens_per_line = [line.split() for line in text.splitlines() if line.split()]
    if not tokens_per_line:
        return 0, []
    try:
        n = int(tokens_per_line[0][0])
    except (ValueError, IndexError):
        return 0, []
    if n <= 0:
        return n, []
    adj: list = [set() for _ in range(n)]
    for parts in tokens_per_line[1:]:
        if len(parts) < 2:
            continue
        try:
            u, v = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if not (1 <= u <= n and 1 <= v <= n) or u == v:
            continue
        adj[u - 1].add(v - 1)
        adj[v - 1].add(u - 1)
    return n, [sorted(a) for a in adj]
