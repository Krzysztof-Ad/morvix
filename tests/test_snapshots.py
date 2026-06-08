# Tests for morvix/snapshots.py
#
# Snapshots pin the current inputs+answers so later drift is visible. These
# tests cover: pinning writes a file; a diff notices an edited answer, an edited
# input, and an edited solution (fingerprint move); loading a missing pin
# raises. Throughout, snapshots only HASH things - they never set an
# expectation and never decide right/wrong.

import os

import pytest

from morvix import snapshots
from morvix.errors import UserError
from morvix.generators import gen_expected, gen_random


# A small generated suite with frozen answers, ready to pin.
def _suite_with_expected(ctx, project):
    gen_random(ctx, project, "array", 3, 1, "baseline", {"count": 2, "lo": 0, "hi": 50})
    gen_expected(ctx, project)
    project.save()


def test_pin_creates_snapshot_file(py_project):
    ctx, project = py_project
    _suite_with_expected(ctx, project)

    path = snapshots.pin(project, "before")

    assert os.path.isfile(path)
    assert "before" in snapshots.list_snapshots(project)
    snap = snapshots.load_snapshot(project, "before")
    # One record per case, each carrying an input hash.
    assert len(snap["cases"]) == len(project.cases)
    for rec in snap["cases"].values():
        assert rec["input_hash"]
    assert snap["solution_fingerprint"]


def test_diff_detects_expected_drift(py_project):
    ctx, project = py_project
    _suite_with_expected(ctx, project)
    snapshots.pin(project, "before")

    # Hand-edit one frozen answer file - the answer drifts, the input does not.
    target = next(c for c in project.cases if c.expected_output)
    with open(project.abspath(target.expected_output), "w", encoding="utf-8") as f:
        f.write("999999\n")

    d = snapshots.diff(project, "before")
    assert target.id in d.expected_changed
    assert target.id not in d.inputs_changed
    assert d.drifted


def test_diff_detects_input_change(py_project):
    ctx, project = py_project
    _suite_with_expected(ctx, project)
    snapshots.pin(project, "before")

    # Edit one input file's bytes; its input hash should now differ.
    target = project.cases[0]
    with open(project.abspath(target.primary_input()), "w", encoding="utf-8") as f:
        f.write("1 2 3 4 5\n")

    d = snapshots.diff(project, "before")
    assert target.id in d.inputs_changed


def test_diff_flags_solution_change(py_project, tmp_path):
    ctx, project = py_project
    _suite_with_expected(ctx, project)
    snapshots.pin(project, "before")

    # Edit the solution source: the fingerprint moves even if inputs/answers
    # are untouched, so any frozen answer is flagged as possibly stale.
    with open(project.solution, "w", encoding="utf-8") as f:
        f.write("import sys\nprint(len(sys.stdin.read().split()))\n")

    d = snapshots.diff(project, "before")
    assert d.solution_changed is True
    assert d.drifted


def test_diff_clean_when_nothing_changed(py_project):
    ctx, project = py_project
    _suite_with_expected(ctx, project)
    snapshots.pin(project, "before")

    d = snapshots.diff(project, "before")
    assert not d.inputs_changed
    assert not d.expected_changed
    assert not d.added
    assert not d.removed
    assert d.solution_changed is False
    assert not d.drifted


def test_diff_reports_added_and_removed_cases(py_project):
    ctx, project = py_project
    _suite_with_expected(ctx, project)
    snapshots.pin(project, "before")

    removed_id = project.cases[0].id
    project.remove_case(removed_id)
    new_cases = gen_random(ctx, project, "array", 1, 99, "baseline", {"count": 2})
    added_id = new_cases[0].id

    d = snapshots.diff(project, "before")
    assert added_id in d.added
    assert removed_id in d.removed


def test_load_snapshot_missing_raises(py_project):
    ctx, project = py_project
    _suite_with_expected(ctx, project)

    with pytest.raises(UserError):
        snapshots.load_snapshot(project, "nope")
    with pytest.raises(UserError):
        snapshots.diff(project, "nope")


def test_list_snapshots_empty_when_none(py_project):
    ctx, project = py_project
    assert snapshots.list_snapshots(project) == []


def test_pin_requires_name(py_project):
    ctx, project = py_project
    with pytest.raises(UserError):
        snapshots.pin(project, "")
