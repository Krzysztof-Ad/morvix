# Tests for the answer-integrity layer: --check-stable and --changed.

from morvix import generators

NONDET = "import sys\nimport random\nsys.stdin.read()\nprint(random.randint(0, 10**9))\n"


def test_check_stable_skips_nondeterministic(py_project, tmp_path):
    ctx, proj = py_project
    nd = tmp_path / "nd.py"
    nd.write_text(NONDET)
    proj.solution = str(nd)
    cases = generators.gen_random(ctx, proj, "ints", 3, 1, "baseline", {"count": 2})
    result = generators.gen_expected(ctx, proj, check_stable=True, repeat=4)
    # A varying answer is refused, not frozen.
    assert len(result["unstable"]) == len(cases)
    assert all(c.expected_output is None and c.expected_hash is None for c in cases)


def test_changed_skips_unchanged_then_recomputes(py_project):
    ctx, proj = py_project  # deterministic sum solution
    generators.gen_random(ctx, proj, "ints", 3, 1, "baseline", {"count": 2})
    first = generators.gen_expected(ctx, proj)
    assert first["computed"] == 3

    # Nothing changed -> everything reused, nothing recomputed.
    again = generators.gen_expected(ctx, proj, changed_only=True)
    assert again["reused"] == 3 and again["computed"] == 0

    # Edit one input -> only that case recomputes.
    target = proj.cases[0]
    with open(proj.abspath(target.primary_input()), "w") as f:
        f.write("3\n1 2 3\n")
    after = generators.gen_expected(ctx, proj, changed_only=True)
    assert after["computed"] == 1 and after["reused"] == 2


def test_changed_recomputes_after_solution_swap(py_project, tmp_path):
    ctx, proj = py_project
    generators.gen_random(ctx, proj, "ints", 2, 1, "baseline", {"count": 2})
    generators.gen_expected(ctx, proj)
    # Swap to a different solution: the fingerprint moves, so --changed recomputes.
    other = tmp_path / "plus.py"
    other.write_text("import sys\nprint(sum(int(x) for x in sys.stdin.read().split()) + 0)\n")
    proj.solution = str(other)
    after = generators.gen_expected(ctx, proj, changed_only=True)
    assert after["computed"] == 2 and after["reused"] == 0
