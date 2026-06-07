# Tests for provenance.py: input hashing, the solution fingerprint, recipe rollup.

import hashlib

from morvix import provenance
from morvix.generators import gen_random


def test_compute_input_hash_matches_bytes(py_project):
    ctx, proj = py_project
    [case] = gen_random(ctx, proj, "ints", 1, 1, "baseline", {})
    data = open(proj.abspath(case.primary_input()), "rb").read()
    assert provenance.compute_input_hash(case, proj.root) == hashlib.sha256(data).hexdigest()
    assert case.input_hash == hashlib.sha256(data).hexdigest()  # stamped at generation


def test_solution_fingerprint_changes_with_source(py_project, tmp_path):
    ctx, proj = py_project
    before = provenance.solution_fingerprint(proj)
    assert before.startswith("sha256:")
    # Editing the answer-producing program changes the fingerprint.
    open(proj.solution, "a").write("\n# touched\n")
    assert provenance.solution_fingerprint(proj) != before


def test_solution_fingerprint_empty_without_solution(py_project):
    ctx, proj = py_project
    proj.solution = None
    assert provenance.solution_fingerprint(proj) == ""


def test_group_recipes_rollup(py_project):
    ctx, proj = py_project
    gen_random(ctx, proj, "ints", 3, 1, "baseline", {})
    recipes = provenance.group_recipes(proj.cases)
    assert recipes["baseline"]["count"] == 3
    assert recipes["baseline"]["mode"] == "random"
    assert recipes["baseline"]["shape"] == "ints"
    assert recipes["baseline"]["base_seed"] == 1


def test_group_recipes_skips_manual(py_project):
    from morvix.generators import gen_manual

    ctx, proj = py_project
    gen_manual(ctx, proj, "hand", group="baseline", content="1 2\n")
    assert provenance.group_recipes(proj.cases) == {}  # manual cases aren't rolled up
