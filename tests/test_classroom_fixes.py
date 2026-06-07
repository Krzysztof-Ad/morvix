# Regressions for the silent-failure footguns found while dogfooding morvix on a
# batch of student-style solutions. Each test pins one bug that let a suite look
# green while nothing real had happened.

import os

from morvix import registry
from morvix.generators import gen_expected, gen_manual, gen_random
from tests.conftest import SUM_ALL_PY, write

# ---------------------------------------------------------------------------
# A copied-in solution is stored as a project-relative path. Cases run with cwd
# set to a temp build dir, so that relative interpreter argument used to miss the
# file and gen_expected froze a "file not found" exit code as the answer - a suite
# that "passed" while the solution never ran. build_solution now resolves it.
# ---------------------------------------------------------------------------


def _copy_in(project, src_text):
    """Mimic `import --copy`: drop the solution in solutions/ and store a relpath."""
    solutions_dir = os.path.join(project.root, "solutions")
    os.makedirs(solutions_dir, exist_ok=True)
    dest = os.path.join(solutions_dir, "sol.py")
    with open(dest, "w") as f:
        f.write(src_text)
    project.solution = os.path.relpath(dest, project.root)
    project.solution_copied = True


def test_copied_relative_solution_computes_real_answers(py_project):
    ctx, project = py_project
    _copy_in(project, SUM_ALL_PY)
    assert not os.path.isabs(project.solution)  # the footgun precondition

    gen_random(ctx, project, "array", 4, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})
    result = gen_expected(ctx, project)

    assert result["computed"] == 4
    for case in project.cases:
        # Real output was frozen, not an exit code from a missing file.
        assert case.expected_output is not None
        assert case.expected_exit is None
        assert os.path.isfile(project.abspath(case.expected_output))


def test_copied_relative_solution_run_passes(py_project):
    from morvix.judge import judge, select_cases

    ctx, project = py_project
    _copy_in(project, SUM_ALL_PY)
    gen_random(ctx, project, "array", 4, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})
    gen_expected(ctx, project)

    run = judge(project, project.solution, project.language, select_cases(project))
    assert sum(1 for c in run.cases if c.status == "pass") == 4


# ---------------------------------------------------------------------------
# Trust guard: if every case errors with the same exit and nothing prints, the
# solution almost certainly never ran. gen_expected must warn instead of freezing
# a green-looking suite.
# ---------------------------------------------------------------------------


class _RecordingMessenger:
    def __init__(self):
        self.warnings = []

    def warning(self, message, hint=None):
        self.warnings.append(message)

    def info(self, message):
        pass

    def plain(self, message=""):
        pass

    def success(self, message):
        pass


def test_warns_when_solution_never_runs(py_project, tmp_path):
    ctx, project = py_project
    # A solution that always exits nonzero and prints nothing.
    project.solution = write(tmp_path / "dead.py", "import sys\nsys.exit(3)\n")
    gen_random(ctx, project, "array", 3, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})

    ctx.messenger = _RecordingMessenger()
    gen_expected(ctx, project)

    joined = " ".join(ctx.messenger.warnings)
    assert "may not be running" in joined


def test_no_false_alarm_when_solution_runs(py_project):
    ctx, project = py_project  # SUM_ALL_PY, prints real output
    gen_random(ctx, project, "array", 3, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})

    ctx.messenger = _RecordingMessenger()
    gen_expected(ctx, project)

    assert not any("may not be running" in w for w in ctx.messenger.warnings)


# ---------------------------------------------------------------------------
# gen --manual used to create an empty input with no way to set the content in
# one-shot mode. --content (and piped stdin) now fill it.
# ---------------------------------------------------------------------------


def test_gen_manual_content_writes_file(py_project):
    ctx, project = py_project
    case = gen_manual(ctx, project, "edge1", group="baseline", content="5 7\n")
    body = open(project.abspath(case.inputs["stdin"])).read()
    assert body == "5 7\n"


def test_gen_manual_empty_content_writes_empty_file(py_project):
    ctx, project = py_project
    case = gen_manual(ctx, project, "blank", group="baseline")
    assert open(project.abspath(case.inputs["stdin"])).read() == ""


def test_gen_command_content_flag(py_project):
    ctx, project = py_project
    registry.safe_dispatch(ctx, ["gen", "--manual", "edge2", "--content", "1 2 3\n"])
    case = next(c for c in project.cases if c.name == "edge2")
    assert open(project.abspath(case.inputs["stdin"])).read() == "1 2 3\n"
