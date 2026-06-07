# Tests for the oracle-free trio (metamorphic/property/fuzz), mutate, infer,
# import, and the model-assist honesty firewall. All must stay inputs-only.

from morvix import assist, generators, importers
from morvix.judge import judge, select_cases

ORDER_DEP = "import sys\nd = sys.stdin.read().split()\nprint(d[0] if d else 0)\n"
ECHO = "import sys\nsys.stdout.write(sys.stdin.read())\n"


def _ints_source(seed):
    from morvix import shapes

    return lambda i: shapes.generate("ints", seed + i, {"count": 6})


def _array_source(seed):
    # "array" puts all values on one line, so reordering them is meaningful.
    from morvix import shapes

    return lambda i: shapes.generate("array", seed + i, {"count": 6})


def test_metamorphic_catches_order_dependence(py_project, tmp_path):
    ctx, proj = py_project
    sol = tmp_path / "od.py"
    sol.write_text(ORDER_DEP)  # prints the first value -> order-dependent
    proj.solution = str(sol)
    cases = generators.gen_metamorphic(
        ctx, proj, "permute-invariant", _array_source(1), 30, 1, "metamorphic", keep=5
    )
    assert cases  # the permutation changed the output -> violations found
    assert all(c.expected_output is None for c in cases)  # inputs only
    assert cases[0].provenance["mode"] == "metamorphic"


def test_metamorphic_no_violation_for_sum(py_project):
    ctx, proj = py_project  # sum is order-independent
    cases = generators.gen_metamorphic(
        ctx, proj, "permute-invariant", _array_source(1), 20, 1, "metamorphic"
    )
    assert cases == []


def test_property_finds_violation(py_project):
    ctx, proj = py_project  # sum can exceed the count n
    cases = generators.gen_property(
        ctx, proj, "out_int <= n", _ints_source(1), 20, 1, "property", keep=5
    )
    assert cases and all(c.expected_output is None for c in cases)


def test_property_holds(py_project):
    ctx, proj = py_project  # a sum of non-negative ints is always >= 0
    cases = generators.gen_property(ctx, proj, "out_int >= 0", _ints_source(1), 20, 1, "property")
    assert cases == []


def test_fuzz_keeps_inputs_only(py_project, tmp_path):
    ctx, proj = py_project
    sol = tmp_path / "echo.py"
    sol.write_text(ECHO)  # output size tracks input size -> behaviour varies
    proj.solution = str(sol)
    seeds = ["3\n1 2 3\n", "1\n9\n"]
    cases = generators.gen_fuzz(ctx, proj, seeds, budget=40, seed=1, keep=5)
    assert all(c.expected_output is None for c in cases)
    assert all(c.provenance["mode"] == "fuzz" for c in cases)


def test_gen_mutate_then_expected(py_project):
    ctx, proj = py_project  # sum solution sums any ints
    generators.gen_random(ctx, proj, "ints", 4, 1, "baseline", {"count": 3})
    muts = generators.gen_mutate(ctx, proj, "baseline", 6, 1, "mutated")
    assert muts and all(c.expected_output is None for c in muts)
    generators.gen_expected(ctx, proj)
    assert judge(proj, proj.solution, proj.language, select_cases(proj)).all_passed


def test_infer_writes_a_runnable_draft(py_project, tmp_path):
    ctx, proj = py_project
    s1 = tmp_path / "s1.txt"
    s1.write_text("3\n1 2 3\n")
    s2 = tmp_path / "s2.txt"
    s2.write_text("2\n5 9\n")
    rel = generators.infer_and_draft(ctx, proj, [str(s1), str(s2)], name="drafted")
    src = open(proj.abspath(rel)).read()
    compile(src, rel, "exec")  # the draft is valid Python


def test_import_strips_bundled_answers(py_project, tmp_path):
    ctx, proj = py_project
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.in").write_text("3\n1 2 3\n")
    (corpus / "a.out").write_text("6\n")  # an answer that MUST be stripped
    summary = importers.import_corpus(ctx, proj, str(corpus), group="imported")
    assert summary.created  # the .in became a case
    assert summary.stripped_answers  # the .out was dropped
    assert all(c.expected_output is None for c in summary.created)  # never set as expected


def test_assist_sanitize_strips_injected_answer():
    # The honesty firewall: a hook (or prompt injection) that returns an answer
    # must have it discarded - only the generator/inputs survive.
    raw = {
        "generator": "print('hi')",
        "expected": "42",
        "answer": "42",
        "output": "42",
        "inputs": ["1 2 3"],
    }
    clean = assist.sanitize_response("scaffold", raw)
    assert clean == {"morvix_assist": assist.ASSIST_VERSION, "kind": "scaffold", "generator": "print('hi')"}
    assert "expected" not in clean and "answer" not in clean and "output" not in clean

    clean_in = assist.sanitize_response("inputs", raw)
    assert clean_in["inputs"] == ["1 2 3"]
    assert "expected" not in clean_in and "generator" not in clean_in


def test_suggested_inputs_are_inert(py_project):
    ctx, proj = py_project
    cases = generators.gen_suggested_inputs(proj, ["1 2 3", "4 5 6"], group="suggested", seed=1)
    assert len(cases) == 2
    assert all(c.expected_output is None and "suggested" in c.tags for c in cases)
