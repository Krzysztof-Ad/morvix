# End-to-end tests for the structural / distribution generation drivers.
# Each generates inputs only, then proves the honest pipeline still judges
# (gen_expected freezes answers from the solution, run --all passes).

from morvix import boundspec, generators
from morvix.judge import judge, select_cases


def _no_expected(cases):
    return all(
        c.expected_output is None
        and c.expected_hash is None
        and c.expected_exit is None
        and c.expected_signal is None
        for c in cases
    )


def test_gen_ladder_emits_geometric_rungs(py_project):
    ctx, proj = py_project
    cases = generators.gen_ladder(ctx, proj, "ints", 1, "ladder", {}, steps=4, lo_n=1, hi_n=100)
    assert 2 <= len(cases) <= 4
    assert _no_expected(cases)
    sizes = [c.provenance["params"]["count"] for c in cases]
    assert sizes == sorted(sizes) and sizes[0] >= 1 and sizes[-1] <= 100
    generators.gen_expected(ctx, proj)
    assert judge(proj, proj.solution, proj.language, select_cases(proj)).all_passed


def test_gen_boundary_then_expected(py_project):
    ctx, proj = py_project
    axes = boundspec.parse_specs(["count=1..5", "hi=0..10"])
    cases = generators.gen_boundary(ctx, proj, "ints", 1, "boundary", axes)
    assert cases and _no_expected(cases)
    generators.gen_expected(ctx, proj)
    assert judge(proj, proj.solution, proj.language, select_cases(proj)).all_passed


def test_gen_exhaustive_then_expected(py_project):
    ctx, proj = py_project
    cases = generators.gen_exhaustive(ctx, proj, "array", 1, "exhaustive", max_n=2, values=[0, 1], cap=50)
    assert cases and _no_expected(cases)
    generators.gen_expected(ctx, proj)
    assert judge(proj, proj.solution, proj.language, select_cases(proj)).all_passed


def test_gen_pairwise_then_expected(py_project):
    ctx, proj = py_project
    axes = boundspec.parse_specs(["count=1,5", "hi=10,100"])
    cases = generators.gen_pairwise(ctx, proj, "ints", 1, "pairwise", axes, strength=2)
    assert cases and _no_expected(cases)
    generators.gen_expected(ctx, proj)
    assert judge(proj, proj.solution, proj.language, select_cases(proj)).all_passed


def test_gen_multi_then_expected(py_project):
    ctx, proj = py_project
    cases = generators.gen_multi(ctx, proj, "ints", 3, 1, "baseline", {}, auto_t=True)
    assert cases and _no_expected(cases)
    # auto_t emits T=1, small and max variants (deduped).
    assert len(cases) >= 2
    generators.gen_expected(ctx, proj)
    assert judge(proj, proj.solution, proj.language, select_cases(proj)).all_passed


def test_gen_catalog_then_expected(py_project):
    ctx, proj = py_project
    cases = generators.gen_catalog(ctx, proj, "tree.binary", 4, 1, "baseline", {"n": 12})
    assert cases and _no_expected(cases)
    assert cases[0].provenance["mode"] == "lib"
    assert cases[0].provenance["lib"] == "tree.binary"
    generators.gen_expected(ctx, proj)
    assert judge(proj, proj.solution, proj.language, select_cases(proj)).all_passed


def test_gen_random_dist_and_adversary(py_project):
    ctx, proj = py_project
    # A non-uniform distribution still produces valid ints the solution can sum.
    cases = generators.gen_random(ctx, proj, "ints", 5, 1, "baseline", {"count": 8, "dist": "zipf"})
    assert _no_expected(cases)
    # An adversarial shape is reachable through the normal shape registry.
    adv = generators.gen_random(ctx, proj, "anti_quicksort", 1, 1, "adv", {"n": 200})
    assert adv and adv[0].provenance["mode"] == "random"
    generators.gen_expected(ctx, proj)
    assert judge(proj, proj.solution, proj.language, select_cases(proj)).all_passed
