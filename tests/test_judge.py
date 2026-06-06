# End-to-end tests for morvix/judge.py (python, no external toolchain).
#
# Covers: judge() passing all cases, a case with a wrong expected output
# failing, expected_exit matching a nonzero exit (Section 14.6), select_cases
# filtering, and on_case callback delivery.

import os

import pytest

from morvix.cases import TestCase, save_cases
from morvix.judge import judge, select_cases
from morvix.layout import EXPECTED_DIR, TESTS_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def _add_stdio_case(proj, tmp_path, name, group, stdin_text, expected_text):
    """Write input/expected files, create a TestCase, attach it to project."""
    stdin_rel = os.path.join(TESTS_DIR, group, f"{name}.in")
    expected_rel = os.path.join(EXPECTED_DIR, group, f"{name}.out")
    _write(tmp_path / stdin_rel, stdin_text)
    _write(tmp_path / expected_rel, expected_text)
    case = TestCase(
        name=name,
        group=group,
        manual=True,
        inputs={"stdin": stdin_rel},
        expected_output=expected_rel,
    )
    proj.add_case(case)
    return case


# ---------------------------------------------------------------------------
# Fixture: three baseline cases with correct expected files
# ---------------------------------------------------------------------------


@pytest.fixture
def judged_project(py_project, tmp_path):
    """py_project + 3 test cases, saved, ready for judge()."""
    ctx, proj = py_project

    _add_stdio_case(proj, tmp_path, "c1", "baseline", "1 2 3\n", "6\n")
    _add_stdio_case(proj, tmp_path, "c2", "baseline", "10 20\n", "30\n")
    _add_stdio_case(proj, tmp_path, "c3", "baseline", "0\n", "0\n")

    proj.save()
    return ctx, proj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_judge_all_pass(judged_project):
    """All three cases produce the correct sum -> all_passed, passed==3."""
    ctx, proj = judged_project
    cases = list(proj.cases)
    result = judge(proj, proj.solution, proj.language, cases)

    assert result.all_passed, [c.verdict for c in result.cases]
    assert result.passed == 3
    assert result.total == 3


def test_judge_wrong_expected_fails(py_project, tmp_path):
    """A case whose expected_output is deliberately wrong -> status 'fail'."""
    ctx, proj = py_project

    # Input sums to 5, but expected says 999.
    bad_case = _add_stdio_case(proj, tmp_path, "bad", "baseline", "2 3\n", "999\n")
    proj.save()

    result = judge(proj, proj.solution, proj.language, [bad_case])

    assert result.total == 1
    assert result.cases[0].status == "fail"


def test_judge_expected_exit_pass(tmp_path, make_ctx):
    """A program that exits 2, case.expected_exit=2 -> pass (Section 14.6)."""
    from morvix.project import Project

    exit2_py = tmp_path / "exit2.py"
    _write(exit2_py, "import sys\nsys.exit(2)\n")

    proj = Project.create(str(tmp_path), "exitprog")
    proj.language = "python"
    proj.model = "stdio"
    proj.solution = str(exit2_py)

    # Case needs an input file; content doesn't matter for a crash program.
    stdin_rel = os.path.join(TESTS_DIR, "baseline", "crash.in")
    _write(tmp_path / stdin_rel, "")
    crash_case = TestCase(
        name="crash",
        group="baseline",
        manual=True,
        inputs={"stdin": stdin_rel},
        expected_exit=2,
    )
    proj.add_case(crash_case)
    proj.save()

    result = judge(proj, proj.solution, proj.language, [crash_case])

    assert result.total == 1
    assert result.cases[0].status == "pass", result.cases[0].verdict


def test_judge_expected_exit_wrong_code_fails(tmp_path, make_ctx):
    """expected_exit=3 but program exits 2 -> status 'fail'."""
    from morvix.project import Project

    exit2_py = tmp_path / "exit2.py"
    _write(exit2_py, "import sys\nsys.exit(2)\n")

    proj = Project.create(str(tmp_path), "exitprog2")
    proj.language = "python"
    proj.model = "stdio"
    proj.solution = str(exit2_py)

    stdin_rel = os.path.join(TESTS_DIR, "baseline", "crash2.in")
    _write(tmp_path / stdin_rel, "")
    case = TestCase(
        name="crash2",
        group="baseline",
        manual=True,
        inputs={"stdin": stdin_rel},
        expected_exit=3,  # wrong expectation
    )
    proj.add_case(case)
    proj.save()

    result = judge(proj, proj.solution, proj.language, [case])

    assert result.cases[0].status == "fail"


def test_on_case_callback(judged_project):
    """on_case is called once per case in order."""
    ctx, proj = judged_project
    cases = list(proj.cases)
    seen = []

    def cb(cr):
        seen.append(cr.case_id)

    judge(proj, proj.solution, proj.language, cases, on_case=cb)

    assert len(seen) == 3
    assert seen == [c.id for c in cases]


def test_select_cases_no_filter(judged_project):
    """select_cases with no runner/groups/ids returns all cases."""
    ctx, proj = judged_project
    selected = select_cases(proj)
    assert len(selected) == 3


def test_select_cases_by_group(judged_project, tmp_path):
    """select_cases with groups= filters to that group only."""
    ctx, proj = judged_project

    # Add a case in a different group.
    _add_stdio_case(proj, tmp_path, "extra", "bonus", "5\n", "5\n")
    proj.save()

    selected = select_cases(proj, groups=["bonus"])
    assert len(selected) == 1
    assert selected[0].group == "bonus"


def test_select_cases_by_id(judged_project):
    """select_cases with case_ids= returns only the named case."""
    ctx, proj = judged_project
    selected = select_cases(proj, case_ids=["baseline/c2"])
    assert len(selected) == 1
    assert selected[0].name == "c2"


def test_judge_run_result_metadata(judged_project):
    """RunResult.solution is the basename of the solution file."""
    ctx, proj = judged_project
    cases = list(proj.cases)
    result = judge(proj, proj.solution, proj.language, cases)

    assert result.solution == os.path.basename(proj.solution)
    assert result.runner is None
