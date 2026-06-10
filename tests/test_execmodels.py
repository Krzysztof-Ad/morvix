# Behavioral tests for the execution models (args, file, interactive, library).
#
# Each model is driven through judge() on a tiny python project in tmp_path so
# the full case pipeline (inputs on disk, expected files, verdicts) is what is
# being tested, not the model function in isolation.

import os

import pytest

from morvix.cases import TestCase
from morvix.judge import judge
from morvix.layout import EXPECTED_DIR, TESTS_DIR
from morvix.project import Project


def _write(path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def _project(tmp_path, make_ctx, model: str, solution_src: str):
    sol = tmp_path / "sol.py"
    sol.write_text(solution_src)
    proj = Project.create(str(tmp_path), "t")
    proj.language = "python"
    proj.model = model
    proj.solution = str(sol)
    proj.save()
    ctx = make_ctx(tmp_path)
    ctx.project = proj
    return ctx, proj


def _add_case(proj, tmp_path, name, *, inputs=None, args=None, expected=None, input_key="stdin"):
    """Write input/expected files and attach a TestCase to the project."""
    case_inputs = {}
    for key, text in (inputs or {}).items():
        rel = os.path.join(TESTS_DIR, "baseline", f"{name}.{key}")
        _write(tmp_path / rel, text)
        case_inputs[key] = rel
    expected_rel = None
    if expected is not None:
        expected_rel = os.path.join(EXPECTED_DIR, "baseline", f"{name}.out")
        _write(tmp_path / expected_rel, expected)
    case = TestCase(
        name=name,
        group="baseline",
        manual=True,
        inputs=case_inputs,
        args=list(args or []),
        expected_output=expected_rel,
    )
    proj.add_case(case)
    return case


# ---------------------------------------------------------------------------
# args model
# ---------------------------------------------------------------------------

# Print the sum of the integers given on argv.
SUM_ARGS_PY = "import sys\nprint(sum(int(x) for x in sys.argv[1:]))\n"


def test_memcheck_skips_non_stdio_models(tmp_path, make_ctx):
    """The valgrind rerun replays the stdio invocation, so non-stdio cases must
    report memcheck as skipped (None) - never a verdict for a run that never
    happened. (Trivially true where valgrind is absent; the gate matters on CI.)"""
    from morvix.project import Runner

    ctx, proj = _project(tmp_path, make_ctx, "args", SUM_ARGS_PY)
    case = _add_case(proj, tmp_path, "ok", args=["1", "2"], expected="3\n")
    proj.save()

    runner = Runner(name="mem", memcheck=True)
    result = judge(proj, proj.solution, proj.language, [case], runner=runner)

    assert result.cases[0].status == "pass", result.cases[0].verdict
    assert result.cases[0].memcheck is None


def test_args_model_passes_case_args(tmp_path, make_ctx):
    ctx, proj = _project(tmp_path, make_ctx, "args", SUM_ARGS_PY)
    ok = _add_case(proj, tmp_path, "ok", args=["1", "2", "3"], expected="6\n")
    bad = _add_case(proj, tmp_path, "bad", args=["1", "1"], expected="3\n")
    proj.save()

    result = judge(proj, proj.solution, proj.language, [ok, bad])

    assert result.cases[0].status == "pass", result.cases[0].verdict
    assert result.cases[1].status == "fail"


# ---------------------------------------------------------------------------
# file model
# ---------------------------------------------------------------------------

# Read input.txt; write its content to output.txt unless told not to write.
FILE_SOL_PY = (
    "data = open('input.txt').read().strip()\n"
    "if data != 'nowrite':\n"
    "    open('output.txt', 'w').write(data + '\\n')\n"
)


def test_file_model_reads_and_judges_output_file(tmp_path, make_ctx):
    ctx, proj = _project(tmp_path, make_ctx, "file", FILE_SOL_PY)
    ok = _add_case(proj, tmp_path, "ok", inputs={"input.txt": "hello"}, expected="hello\n")
    proj.save()

    result = judge(proj, proj.solution, proj.language, [ok])

    assert result.cases[0].status == "pass", result.cases[0].verdict


def test_file_model_does_not_judge_stale_output_from_previous_case(tmp_path, make_ctx):
    """Cases share one build workdir; a case whose program writes nothing must
    not inherit (and be judged on) the previous case's output.txt."""
    ctx, proj = _project(tmp_path, make_ctx, "file", FILE_SOL_PY)
    writes = _add_case(proj, tmp_path, "writes", inputs={"input.txt": "A"}, expected="A\n")
    # The program writes nothing here; with a stale output.txt from the case
    # above this would wrongly compare "A" against "A" and pass.
    silent = _add_case(proj, tmp_path, "silent", inputs={"input.txt": "nowrite"}, expected="A\n")
    proj.save()

    result = judge(proj, proj.solution, proj.language, [writes, silent])

    assert result.cases[0].status == "pass", result.cases[0].verdict
    assert result.cases[1].status == "fail", "stale output.txt was judged as this case's output"


def test_file_model_missing_input_is_absent_not_stale(tmp_path, make_ctx):
    """An input copied in by an earlier case must not satisfy a later case
    that declares the same logical name but whose file is gone from disk."""
    ctx, proj = _project(tmp_path, make_ctx, "file", FILE_SOL_PY)
    first = _add_case(proj, tmp_path, "first", inputs={"input.txt": "A"}, expected="A\n")
    ghost = _add_case(proj, tmp_path, "ghost", inputs={"input.txt": "B"}, expected="B\n")
    # Remove ghost's input from disk after creation: judge reports a missing
    # input as a setup error rather than running against first's stale copy.
    os.unlink(os.path.join(str(tmp_path), ghost.inputs["input.txt"]))
    proj.save()

    result = judge(proj, proj.solution, proj.language, [first, ghost])

    assert result.cases[0].status == "pass", result.cases[0].verdict
    assert result.cases[1].status == "error"
    assert "missing" in (result.cases[1].verdict or "")
