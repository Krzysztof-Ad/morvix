# Tests for morvix/validators.py
#
# A validator gates input shape before answers are frozen. It sees inputs only,
# so these tests never touch expected output - they prove well-formed inputs pass
# and malformed ones fail, that flagging works per-case, and that a missing
# toolchain degrades honestly rather than crashing.

import os

from morvix import layout
from morvix.cases import TestCase
from morvix.validators import (
    VALIDATOR_TEMPLATE,
    is_valid,
    new_validator,
    resolve_validator,
    validate_cases,
)

# A tiny validator: first line is an int equal to the count of the following
# numbers. Well-formed -> exit 0; anything else -> exit 1. Inputs only.
COUNT_VALIDATOR = """import sys
toks = sys.stdin.read().split()
if not toks:
    sys.exit(1)
try:
    n = int(toks[0])
except ValueError:
    sys.exit(1)
rest = toks[1:]
if len(rest) != n:
    sys.exit(1)
for t in rest:
    try:
        int(t)
    except ValueError:
        sys.exit(1)
sys.exit(0)
"""


def _write_validator(project, text, name="validate.py"):
    rel = os.path.join(layout.GENERATORS_DIR, name)
    path = project.abspath(rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# ---------------------------------------------------------------------------
# new_validator
# ---------------------------------------------------------------------------


def test_new_validator_writes_template(py_project):
    ctx, project = py_project
    rel = new_validator(ctx, project, "validate")

    assert rel == os.path.join(layout.GENERATORS_DIR, "validate.py")
    path = project.abspath(rel)
    assert os.path.isfile(path)
    with open(path, "r", encoding="utf-8") as f:
        written = f.read()
    assert written == VALIDATOR_TEMPLATE
    # The template never reads or sets an expected-answer field (inputs only).
    assert "expected_" not in written


def test_new_validator_appends_extension(py_project):
    ctx, project = py_project
    rel = new_validator(ctx, project, "myval")
    assert rel.endswith("myval.py")


def test_new_validator_rejects_duplicate(py_project):
    import pytest

    from morvix.errors import UserError

    ctx, project = py_project
    new_validator(ctx, project, "validate")
    with pytest.raises(UserError):
        new_validator(ctx, project, "validate")


# ---------------------------------------------------------------------------
# resolve_validator
# ---------------------------------------------------------------------------


def test_resolve_validator_prefers_explicit(py_project):
    ctx, project = py_project
    explicit = project.abspath(os.path.join(layout.GENERATORS_DIR, "x.py"))
    assert resolve_validator(project, explicit=explicit) == explicit


def test_resolve_validator_defaults_to_scaffold(py_project):
    ctx, project = py_project
    got = resolve_validator(project)
    assert got == project.abspath(os.path.join(layout.GENERATORS_DIR, "validate.py"))


# ---------------------------------------------------------------------------
# is_valid
# ---------------------------------------------------------------------------


def test_is_valid_accepts_well_formed(py_project):
    ctx, project = py_project
    path = _write_validator(project, COUNT_VALIDATOR)
    assert is_valid(project, "3\n1 2 3\n", path) is True


def test_is_valid_rejects_malformed(py_project):
    ctx, project = py_project
    path = _write_validator(project, COUNT_VALIDATOR)
    # count says 3 but only two numbers follow
    assert is_valid(project, "3\n1 2\n", path) is False


def test_is_valid_accepts_bytes(py_project):
    ctx, project = py_project
    path = _write_validator(project, COUNT_VALIDATOR)
    assert is_valid(project, b"2\n7 8\n", path) is True


# ---------------------------------------------------------------------------
# validate_cases
# ---------------------------------------------------------------------------


def _make_case(project, name, content):
    rel = os.path.join(layout.TESTS_DIR, "baseline", f"{name}.in")
    path = project.abspath(rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return TestCase(name=name, group="baseline", inputs={"stdin": rel})


def test_validate_cases_flags_malformed(py_project):
    ctx, project = py_project
    path = _write_validator(project, COUNT_VALIDATOR)
    good = _make_case(project, "good", "2\n4 5\n")
    bad = _make_case(project, "bad", "5\n4 5\n")

    results = validate_cases(project, [good, bad], path)

    assert len(results) == 2
    assert results[0].case_id == "baseline/good"
    assert results[0].valid is True
    assert results[0].degraded is False
    assert results[1].case_id == "baseline/bad"
    assert results[1].valid is False
    assert results[1].degraded is False


def test_validate_cases_empty_returns_empty(py_project):
    ctx, project = py_project
    path = _write_validator(project, COUNT_VALIDATOR)
    assert validate_cases(project, [], path) == []


def test_validate_cases_missing_input_degrades(py_project):
    ctx, project = py_project
    path = _write_validator(project, COUNT_VALIDATOR)
    # A case whose input file was never written: cannot be validated.
    ghost = TestCase(
        name="ghost",
        group="baseline",
        inputs={"stdin": os.path.join(layout.TESTS_DIR, "baseline", "ghost.in")},
    )
    results = validate_cases(project, [ghost], path)
    assert len(results) == 1
    assert results[0].degraded is True
    assert results[0].valid is False


# ---------------------------------------------------------------------------
# honest degradation when the toolchain is missing
# ---------------------------------------------------------------------------


def test_validate_missing_toolchain_degrades(py_project):
    # A validator with an unknown extension has no language adapter, so it cannot
    # be built. validate_cases must degrade every case rather than crash.
    ctx, project = py_project
    path = _write_validator(project, "garbage", name="validate.zzz")
    case = _make_case(project, "c1", "2\n1 2\n")

    results = validate_cases(project, [case], path)

    assert len(results) == 1
    assert results[0].degraded is True
    assert results[0].valid is False
    assert results[0].message  # an honest reason is present


def test_is_valid_missing_toolchain_does_not_block(py_project):
    # is_valid degrades to True so a --require-valid resample loop against a
    # missing validator does not spin forever.
    ctx, project = py_project
    path = _write_validator(project, "garbage", name="validate.zzz")
    assert is_valid(project, "anything", path) is True
