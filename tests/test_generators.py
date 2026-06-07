# Tests for morvix/generators.py
import os

import pytest

from morvix.cases import TestCase
from morvix.generators import (
    clean_generated,
    gen_expected,
    gen_manual,
    gen_random,
    gen_stress,
)
from morvix.project import Rival
from tests.conftest import SUM_ALL_PY

# ---------------------------------------------------------------------------
# gen_random
# ---------------------------------------------------------------------------


def test_gen_random_creates_cases_and_files(py_project, tmp_path):
    ctx, project = py_project
    cases = gen_random(ctx, project, "array", 4, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})

    assert len(cases) == 4
    assert len(project.cases) == 4

    for case in cases:
        assert case.group == "baseline"
        assert not case.manual
        rel = case.inputs.get("stdin")
        assert rel is not None
        abspath = project.abspath(rel)
        assert os.path.isfile(abspath), f"input file missing: {abspath}"


# ---------------------------------------------------------------------------
# gen_expected
# ---------------------------------------------------------------------------


def test_gen_expected_writes_expected_files(py_project):
    ctx, project = py_project
    gen_random(ctx, project, "array", 4, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})

    result = gen_expected(ctx, project)

    assert result["computed"] == 4

    for case in project.cases:
        assert case.expected_output is not None
        abspath = project.abspath(case.expected_output)
        assert os.path.isfile(abspath), f"expected file missing: {abspath}"


def test_gen_expected_judge_passes(py_project):
    from morvix.judge import judge, select_cases

    ctx, project = py_project
    gen_random(ctx, project, "array", 4, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})
    gen_expected(ctx, project)

    cases = select_cases(project)
    run = judge(project, project.solution, project.language, cases)

    assert sum(1 for c in run.cases if c.status == "pass") == 4


# ---------------------------------------------------------------------------
# clean_generated
# ---------------------------------------------------------------------------


def test_clean_generated_removes_generated_cases(py_project):
    ctx, project = py_project
    gen_random(ctx, project, "array", 4, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})

    # Add a manual case that must survive.
    gen_manual(ctx, project, "hand1", group="baseline", content="3 4 5\n")

    assert len(project.cases) == 5

    removed = clean_generated(project)

    assert removed == 4
    assert len(project.cases) == 1
    assert project.cases[0].name == "hand1"
    assert project.cases[0].manual


def test_clean_generated_deletes_input_files(py_project):
    ctx, project = py_project
    cases = gen_random(ctx, project, "array", 4, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})
    paths = [project.abspath(c.inputs["stdin"]) for c in cases]

    clean_generated(project)

    for p in paths:
        assert not os.path.exists(p), f"input file should have been removed: {p}"


# ---------------------------------------------------------------------------
# gen_stress
# ---------------------------------------------------------------------------

BUGGY_SUM_PY = "import sys\nd = sys.stdin.read().split()\nprint(sum(int(x) for x in d) + 1)\n"


def test_gen_stress_finds_disagreement(py_project, tmp_path):
    ctx, project = py_project

    buggy = tmp_path / "buggy.py"
    buggy.write_text(BUGGY_SUM_PY)

    bf = tmp_path / "bf.py"
    bf.write_text(SUM_ALL_PY)

    project.solution = str(buggy)
    project.add_rival(Rival(name="bf", path=str(bf), stress=True))

    cases = gen_stress(ctx, project, 30, 7)

    assert cases  # at least one disagreement found and saved
    result = cases[0]
    assert isinstance(result, TestCase)
    assert result.manual is True

    # The regression case must be in project.cases.
    ids = [c.id for c in project.cases]
    assert result.id in ids

    # Both the input and expected files must exist.
    in_path = project.abspath(result.inputs["stdin"])
    assert os.path.isfile(in_path)

    exp_path = project.abspath(result.expected_output)
    assert os.path.isfile(exp_path)
