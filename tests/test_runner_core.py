# Tests for morvix/runner_core/morvix_runner.py - the shippable, stdlib-only runner.
#
# We build a minimal package layout in tmp_path (morvix.json + tests/ + expected/
# + a sol.py), copy the runner core next to morvix.json, and drive it via
# subprocess so we exercise it exactly as a Receiver would.

import json
import os
import shutil
import subprocess
import sys

import pytest

from morvix.manifest import write_manifest
from morvix.cases import TestCase
from morvix.layout import TESTS_DIR, EXPECTED_DIR

RUNNER_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "morvix", "runner_core", "morvix_runner.py",
)

SUM_SOL = "import sys\nd = sys.stdin.read().split()\nprint(sum(int(x) for x in d))\n"
WRONG_SOL = "import sys\nsys.stdin.read()\nprint(999999)\n"


def _write(path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def _add_case(proj, tmp_path, name, group, stdin_text, expected_text):
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


def _setup_package(py_project, tmp_path):
    """Add test cases, write the manifest, copy the runner core."""
    ctx, proj = py_project

    _add_case(proj, tmp_path, "c1", "baseline", "1 2 3\n", "6\n")
    _add_case(proj, tmp_path, "c2", "baseline", "10 20\n", "30\n")
    _add_case(proj, tmp_path, "c3", "baseline", "0\n", "0\n")
    proj.save()

    write_manifest(proj)

    runner_dst = tmp_path / "morvix_runner.py"
    shutil.copy2(RUNNER_SRC, str(runner_dst))

    return tmp_path


def _run_runner(pkg_dir, sol_path, extra_args=None):
    cmd = [sys.executable, "morvix_runner.py", sol_path, "--all"]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=str(pkg_dir),
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# The runner core must contain no "import morvix" anywhere.
# ---------------------------------------------------------------------------

def test_runner_core_no_morvix_import():
    content = open(RUNNER_SRC, "r", encoding="utf-8").read()
    assert "import morvix" not in content


# ---------------------------------------------------------------------------
# A correct solution: returncode 0, "passed" in stdout.
# ---------------------------------------------------------------------------

def test_runner_core_correct_solution(py_project, tmp_path):
    pkg = _setup_package(py_project, tmp_path)

    sol = tmp_path / "sol.py"
    sol.write_text(SUM_SOL)

    result = _run_runner(pkg, "sol.py")

    assert result.returncode == 0, (
        f"Expected returncode 0.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "passed" in result.stdout.lower(), (
        f"Expected 'passed' in stdout.\nstdout:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# A wrong solution: returncode 1.
# ---------------------------------------------------------------------------

def test_runner_core_wrong_solution(py_project, tmp_path):
    pkg = _setup_package(py_project, tmp_path)

    sol = tmp_path / "wrong_sol.py"
    sol.write_text(WRONG_SOL)

    result = _run_runner(pkg, "wrong_sol.py")

    assert result.returncode == 1, (
        f"Expected returncode 1 for wrong solution.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# A solution missing from disk produces returncode 2 (not a test failure).
# ---------------------------------------------------------------------------

def test_runner_core_missing_solution(py_project, tmp_path):
    pkg = _setup_package(py_project, tmp_path)

    result = _run_runner(pkg, "does_not_exist.py")

    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Output format: correct run mentions each case and a summary line.
# ---------------------------------------------------------------------------

def test_runner_core_output_mentions_cases(py_project, tmp_path):
    pkg = _setup_package(py_project, tmp_path)

    sol = tmp_path / "sol.py"
    sol.write_text(SUM_SOL)

    result = _run_runner(pkg, "sol.py")

    # Each of the three case ids should appear in the output.
    for cid in ("baseline/c1", "baseline/c2", "baseline/c3"):
        assert cid in result.stdout, f"Case {cid!r} not found in output:\n{result.stdout}"


# ---------------------------------------------------------------------------
# JSON results export: --results json writes a parseable file.
# ---------------------------------------------------------------------------

def test_runner_core_json_results(py_project, tmp_path):
    pkg = _setup_package(py_project, tmp_path)

    sol = tmp_path / "sol.py"
    sol.write_text(SUM_SOL)

    out_file = str(tmp_path / "results.json")
    result = _run_runner(pkg, "sol.py", extra_args=["--results", "json", "--out", out_file])

    assert result.returncode == 0
    assert os.path.exists(out_file), "results JSON file was not written"

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["summary"]["passed"] == 3
    assert data["summary"]["failed"] == 0
    assert data["summary"]["total"] == 3


# ---------------------------------------------------------------------------
# Wrong solution's JSON results reflect the failures.
# ---------------------------------------------------------------------------

def test_runner_core_json_results_wrong_solution(py_project, tmp_path):
    pkg = _setup_package(py_project, tmp_path)

    sol = tmp_path / "wrong_sol.py"
    sol.write_text(WRONG_SOL)

    out_file = str(tmp_path / "results_wrong.json")
    result = _run_runner(pkg, "wrong_sol.py", extra_args=["--results", "json", "--out", out_file])

    assert result.returncode == 1
    assert os.path.exists(out_file)

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["summary"]["failed"] > 0
    assert data["summary"]["passed"] < data["summary"]["total"]


# ---------------------------------------------------------------------------
# Hand-written manifest (no py_project): ensures the runner works without
# the morvix library being installed at all (pure stdlib path).
# ---------------------------------------------------------------------------

def test_runner_core_hand_written_manifest(tmp_path):
    """Build everything by hand, without using any morvix imports."""
    # Write input and expected output.
    (tmp_path / "tests" / "baseline").mkdir(parents=True)
    (tmp_path / "expected" / "baseline").mkdir(parents=True)
    (tmp_path / "tests" / "baseline" / "t1.in").write_text("4 5 6\n")
    (tmp_path / "expected" / "baseline" / "t1.out").write_text("15\n")

    manifest = {
        "morvix": "0.0.0",
        "name": "handmade",
        "model": "stdio",
        "locale": "C",
        "compare": {"strategy": "whitespace"},
        "limits": {"wall": 10.0},
        "languages": {},
        "raw_build": None,
        "raw_run": None,
        "groups": ["baseline"],
        "cases": [
            {
                "name": "t1",
                "group": "baseline",
                "manual": True,
                "inputs": {"stdin": "tests/baseline/t1.in"},
                "expected_output": "expected/baseline/t1.out",
            }
        ],
        "runners": {},
        "author_results": None,
    }
    (tmp_path / "morvix.json").write_text(json.dumps(manifest, indent=2))
    (tmp_path / "sol.py").write_text(SUM_SOL)
    shutil.copy2(RUNNER_SRC, str(tmp_path / "morvix_runner.py"))

    result = subprocess.run(
        [sys.executable, "morvix_runner.py", "sol.py", "--all"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "passed" in result.stdout.lower()
