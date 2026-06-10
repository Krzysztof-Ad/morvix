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


# ---------------------------------------------------------------------------
# interactive model
# ---------------------------------------------------------------------------

# The interactor sends "ping", expects "pong" back, and its exit code is the
# verdict (0 = pass), per Section 10.5.
INTERACTOR_PY = (
    "import sys\n"
    "sys.stdout.write('ping\\n')\n"
    "sys.stdout.flush()\n"
    "reply = sys.stdin.readline().strip()\n"
    "sys.exit(0 if reply == 'pong' else 1)\n"
)

PONG_SOL = "import sys\nline = input()\nprint('pong', flush=True)\n"
WRONG_SOL = "import sys\nline = input()\nprint('nope', flush=True)\n"
MUTE_SOL = "import sys, time\nline = input()\ntime.sleep(30)\n"


def _interactive_project(tmp_path, make_ctx, solution_src):
    ctx, proj = _project(tmp_path, make_ctx, "interactive", solution_src)
    interactor = tmp_path / "interactor.py"
    interactor.write_text(INTERACTOR_PY)
    proj.interactor = str(interactor)
    case = _add_case(proj, tmp_path, "conv", inputs={"stdin": ""})
    case.expected_exit = 0  # the interactor's exit code is the verdict
    proj.save()
    return ctx, proj, case


def test_interactive_model_interactor_accepts(tmp_path, make_ctx):
    ctx, proj, case = _interactive_project(tmp_path, make_ctx, PONG_SOL)
    result = judge(proj, proj.solution, proj.language, [case])
    assert result.cases[0].status == "pass", result.cases[0].verdict


def test_interactive_model_interactor_rejects(tmp_path, make_ctx):
    ctx, proj, case = _interactive_project(tmp_path, make_ctx, WRONG_SOL)
    result = judge(proj, proj.solution, proj.language, [case])
    assert result.cases[0].status == "fail"


def test_interactive_model_times_out_unresponsive_solution(tmp_path, make_ctx):
    ctx, proj, case = _interactive_project(tmp_path, make_ctx, MUTE_SOL)
    case.limits = {"wall": 0.4}
    proj.save()
    result = judge(proj, proj.solution, proj.language, [case])
    assert result.cases[0].status == "fail"
    assert result.cases[0].timed_out


def test_interactive_model_without_interactor_fails_clearly(tmp_path, make_ctx):
    ctx, proj, case = _interactive_project(tmp_path, make_ctx, PONG_SOL)
    proj.interactor = None
    result = judge(proj, proj.solution, proj.language, [case])
    assert result.cases[0].status == "fail"
    assert "no interactor" in (result.cases[0].verdict or "")


def test_legacy_languages_interactor_key_still_loads(tmp_path, make_ctx):
    """Pre-0.9 projects stored the interactor under languages['interactor']."""
    ctx, proj, case = _interactive_project(tmp_path, make_ctx, PONG_SOL)
    path = proj.interactor
    proj.interactor = None
    proj.languages["interactor"] = path
    proj.save()

    reloaded = Project.load(str(tmp_path))
    assert reloaded.interactor == path


# ---------------------------------------------------------------------------
# library model (needs a C compiler for the per-case harness)
# ---------------------------------------------------------------------------

# The solution still builds through the C adapter (so it needs a main); the
# library model then compiles and runs each case's harness on its own. That
# exercises the harness-verdict path without needing a real shared library.
LIB_SOL_C = "int main(void) { return 0; }\n"
HARNESS_OK = "int main(void) { return 0; }\n"
HARNESS_BAD = "int main(void) { return 1; }\n"
HARNESS_BROKEN = "int main(void) { this does not compile\n"


@pytest.fixture
def lib_project(tmp_path, make_ctx):
    if not __import__("shutil").which("cc"):
        pytest.skip("cc not installed")
    sol = tmp_path / "lib.c"
    sol.write_text(LIB_SOL_C)
    proj = Project.create(str(tmp_path), "t")
    proj.language = "c"
    proj.model = "library"
    proj.solution = str(sol)
    proj.save()
    ctx = make_ctx(tmp_path)
    ctx.project = proj
    return ctx, proj


def _harness_case(proj, tmp_path, name, source):
    rel = os.path.join(TESTS_DIR, "baseline", f"{name}.c")
    _write(tmp_path / rel, source)
    case = TestCase(
        name=name, group="baseline", manual=True, inputs={"harness": rel}, expected_exit=0
    )
    proj.add_case(case)
    return case


def test_library_model_harness_verdicts(lib_project, tmp_path):
    ctx, proj = lib_project
    ok = _harness_case(proj, tmp_path, "ok", HARNESS_OK)
    bad = _harness_case(proj, tmp_path, "bad", HARNESS_BAD)
    broken = _harness_case(proj, tmp_path, "broken", HARNESS_BROKEN)
    proj.save()

    result = judge(proj, proj.solution, proj.language, [ok, bad, broken])

    assert result.cases[0].status == "pass", result.cases[0].verdict
    assert result.cases[1].status == "fail"
    assert result.cases[2].status == "fail"  # harness failed to compile
