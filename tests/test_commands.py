# Integration tests for the command registry (Section 5.1).
#
# All tests run in-process via safe_dispatch; no subprocess spawning.
# Each test builds whatever it needs in tmp_path.

import os

import pytest

from morvix.registry import safe_dispatch

# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


def test_init_creates_project_json(tmp_path, make_ctx):
    """init --name t --language python creates config/project.json and sets ctx.project."""
    ctx = make_ctx(tmp_path)
    rc = safe_dispatch(ctx, ["init", "--name", "t", "--language", "python"])
    assert rc == 0
    assert (tmp_path / ".morvix" / "config" / "project.json").exists()
    assert ctx.project is not None
    assert ctx.project.name == "t"
    assert ctx.project.language == "python"


def test_init_idempotent(tmp_path, make_ctx):
    """Running init a second time warns and returns 0 without overwriting."""
    ctx = make_ctx(tmp_path)
    safe_dispatch(ctx, ["init", "--name", "t", "--language", "python"])
    rc = safe_dispatch(ctx, ["init", "--name", "t2", "--language", "python"])
    assert rc == 0
    # name should still be the original, not overwritten
    ctx.reload_project()
    assert ctx.project.name == "t"


# ---------------------------------------------------------------------------
# import command
# ---------------------------------------------------------------------------


def test_import_sets_solution(tmp_path, make_ctx):
    """After init + import, ctx.project.solution is set to the absolute path."""
    ctx = make_ctx(tmp_path)
    safe_dispatch(ctx, ["init", "--name", "t", "--language", "python"])

    sol = tmp_path / "sol.py"
    sol.write_text("import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n")

    rc = safe_dispatch(ctx, ["import", str(sol)])
    assert rc == 0
    ctx.reload_project()
    assert ctx.project.solution is not None
    assert "sol.py" in ctx.project.solution


# ---------------------------------------------------------------------------
# gen --random / gen --expected / run --all pipeline
# ---------------------------------------------------------------------------


def test_gen_random_and_run(tmp_path, make_ctx):
    """Full pipeline: init -> import -> gen --random -> gen --expected -> run --all."""
    ctx = make_ctx(tmp_path)

    safe_dispatch(ctx, ["init", "--name", "t", "--language", "python"])

    sol = tmp_path / "sol.py"
    sol.write_text("import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n")

    rc = safe_dispatch(ctx, ["import", str(sol)])
    assert rc == 0

    ctx.reload_project()

    rc = safe_dispatch(
        ctx,
        [
            "gen",
            "--random",
            "--shape",
            "array",
            "--count",
            "3",
            "--param",
            "count=2",
            "--param",
            "hi=20",
        ],
    )
    assert rc == 0
    ctx.reload_project()
    assert len(ctx.project.cases) == 3

    rc = safe_dispatch(ctx, ["gen", "--expected"])
    assert rc == 0

    rc = safe_dispatch(ctx, ["run", "--all"])
    assert rc == 0


# ---------------------------------------------------------------------------
# gen --manual case + gen --expected + run
# ---------------------------------------------------------------------------


def test_gen_manual_case_and_run(tmp_path, make_ctx):
    """Manual case: write input, gen --expected, run --all passes."""
    ctx = make_ctx(tmp_path)

    safe_dispatch(ctx, ["init", "--name", "t", "--language", "python"])

    sol = tmp_path / "sol.py"
    sol.write_text("import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n")
    safe_dispatch(ctx, ["import", str(sol)])
    ctx.reload_project()

    rc = safe_dispatch(ctx, ["gen", "--manual", "case1"])
    assert rc == 0
    ctx.reload_project()

    # The manual case has an input file; write content so expected output is meaningful.
    case = ctx.project.cases[0]
    stdin_path = os.path.join(tmp_path, case.inputs["stdin"])
    os.makedirs(os.path.dirname(stdin_path), exist_ok=True)
    with open(stdin_path, "w") as f:
        f.write("4 6\n")

    rc = safe_dispatch(ctx, ["gen", "--expected"])
    assert rc == 0

    rc = safe_dispatch(ctx, ["run", "--all"])
    assert rc == 0


# ---------------------------------------------------------------------------
# status command
# ---------------------------------------------------------------------------


def test_status_no_project(tmp_path, make_ctx):
    """status without a project returns 0 and does not crash."""
    ctx = make_ctx(tmp_path)
    rc = safe_dispatch(ctx, ["status"])
    assert rc == 0


def test_status_with_project(tmp_path, make_ctx):
    """status with a project returns 0."""
    ctx = make_ctx(tmp_path)
    safe_dispatch(ctx, ["init", "--name", "t", "--language", "python"])
    rc = safe_dispatch(ctx, ["status"])
    assert rc == 0


# ---------------------------------------------------------------------------
# help command
# ---------------------------------------------------------------------------


def test_help_returns_0(tmp_path, make_ctx):
    """help with no arguments returns 0."""
    ctx = make_ctx(tmp_path)
    rc = safe_dispatch(ctx, ["help"])
    assert rc == 0


def test_help_specific_command(tmp_path, make_ctx):
    """help gen returns 0."""
    ctx = make_ctx(tmp_path)
    rc = safe_dispatch(ctx, ["help", "gen"])
    assert rc == 0
