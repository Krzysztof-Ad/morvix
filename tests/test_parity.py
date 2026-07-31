# Engine <-> runner-core parity: the drift gate.
#
# CLAUDE.md declares the shipped runner core a manual mirror of the judging
# logic in judge.py/process.py/compare.py. This suite makes that rule
# enforceable: one project, one set of cases spanning every comparison
# strategy and judging dimension, judged twice - in-process by judge() and by
# morvix_runner.py exactly as a Receiver runs it - and the per-case verdicts
# must agree. If you change judging behavior on one side only, this fails.

import json
import os
import shutil
import signal
import stat
import subprocess
import sys

import pytest

from morvix.cases import TestCase
from morvix.judge import judge
from morvix.layout import EXPECTED_DIR, TESTS_DIR
from morvix.manifest import write_manifest
from morvix.project import Project

RUNNER_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "morvix",
    "runner_core",
    "morvix_runner.py",
)

# One solution that can produce every behavior a dimension needs, picked by
# the first token of stdin.
DISPATCH_SOL = """\
import sys
words = sys.stdin.read().split()
mode, rest = words[0], words[1:]
if mode == "sum":
    print(sum(int(x) for x in rest))
elif mode == "say":
    print(" ".join(rest) + "  ")  # trailing spaces: exact vs whitespace differ
elif mode == "floats":
    print("nan inf 1e400 0.5")
elif mode == "exit3":
    sys.exit(3)
elif mode == "sleep":
    import time
    time.sleep(10)
    print("done")
elif mode == "segv":
    import os, signal
    os.kill(os.getpid(), signal.SIGSEGV)
"""

# A checker that accepts iff the observed output's first token is "ok",
# and hangs on "hang" (to prove both sides bound the checker's runtime).
CHECKER = """\
#!/usr/bin/env python3
import sys, time
observed = open(sys.argv[2]).read().split()
if observed and observed[0] == "hang":
    time.sleep(30)
sys.exit(0 if observed and observed[0] == "ok" else 1)
"""


def _write(path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


def _case(proj, tmp_path, name, stdin_text, expected_text=None, **fields):
    stdin_rel = os.path.join(TESTS_DIR, "baseline", f"{name}.in")
    _write(tmp_path / stdin_rel, stdin_text)
    expected_rel = None
    if expected_text is not None:
        expected_rel = os.path.join(EXPECTED_DIR, "baseline", f"{name}.out")
        _write(tmp_path / expected_rel, expected_text)
    case = TestCase(
        name=name,
        group="baseline",
        manual=True,
        inputs={"stdin": stdin_rel},
        expected_output=expected_rel,
        **fields,
    )
    proj.add_case(case)
    return case


def _build_project(tmp_path, make_ctx):
    sol = tmp_path / "sol.py"
    sol.write_text(DISPATCH_SOL)
    proj = Project.create(str(tmp_path), "parity")
    proj.language = "python"
    proj.model = "stdio"
    proj.solution = str(sol)

    checker = tmp_path / "checker.py"
    checker.write_text(CHECKER)
    checker.chmod(checker.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    proj.compare["checker"] = str(checker)

    ctx = make_ctx(tmp_path)
    ctx.project = proj
    return ctx, proj


def _parity_cases(proj, tmp_path):
    """Every judging dimension once, with a pass and a fail where meaningful."""
    sha_ok = __import__("hashlib").sha256(b"6\n").hexdigest()

    _case(proj, tmp_path, "ws_pass", "sum 1 2 3\n", "6\n")
    _case(proj, tmp_path, "ws_fail", "sum 1 2 3\n", "7\n")
    _case(proj, tmp_path, "exact_fail", "say hi\n", "hi\n", compare="exact")
    _case(proj, tmp_path, "ws_trailing_pass", "say hi\n", "hi\n", compare="whitespace")
    # The historical drift case: nan/inf/overflow tokens must compare equal to
    # themselves under the float strategy on BOTH sides.
    _case(proj, tmp_path, "float_special", "floats\n", "nan inf 1e400 0.5\n", compare="float")
    _case(
        proj, tmp_path, "float_eps_pass", "floats\n", "nan inf 1e400 0.5000001\n", compare="float"
    )
    _case(proj, tmp_path, "float_fail", "floats\n", "nan inf 1e400 0.6\n", compare="float")
    _case(proj, tmp_path, "hash_pass", "sum 1 2 3\n", None, expected_hash=sha_ok)
    _case(proj, tmp_path, "hash_fail", "sum 1 2\n", None, expected_hash=sha_ok)
    _case(proj, tmp_path, "exit_pass", "exit3\n", None, expected_exit=3)
    _case(proj, tmp_path, "exit_fail", "sum 1\n", "1\n", expected_exit=3)
    _case(proj, tmp_path, "crash_fail", "exit3\n", "ignored\n")
    _case(proj, tmp_path, "timeout", "sleep\n", "done\n", limits={"wall": 0.4})
    _case(proj, tmp_path, "no_expectation", "sum 1\n", None)
    if os.name == "posix":
        # Signals and shebang-executed checker scripts are POSIX-only.
        _case(proj, tmp_path, "signal_pass", "segv\n", None, expected_signal="SIGSEGV")
        _case(proj, tmp_path, "signal_fail", "sum 1\n", "1\n", expected_signal="SIGSEGV")
        _case(proj, tmp_path, "checker_pass", "say ok\n", None, compare="checker")
        _case(proj, tmp_path, "checker_fail", "say nope\n", None, compare="checker")
        _case(
            proj,
            tmp_path,
            "checker_hang",
            "say hang\n",
            None,
            compare="checker",
            limits={"wall": 0.2},
        )
    proj.save()


def _engine_statuses(proj):
    run = judge(proj, proj.solution, proj.language, list(proj.cases))
    return {c.case_id: (c.status, bool(c.timed_out)) for c in run.cases}


def _runner_statuses(tmp_path):
    shutil.copy2(RUNNER_SRC, str(tmp_path / "morvix_runner.py"))
    out = str(tmp_path / "parity_results.json")
    proc = subprocess.run(
        [sys.executable, "morvix_runner.py", "sol.py", "--all", "--results", "json", "--out", out],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert os.path.exists(out), (
        f"runner produced no results file.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    with open(out, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["case"]: (c["status"], bool(c.get("timed_out", False))) for c in data["cases"]}


def test_engine_and_runner_agree_on_every_dimension(tmp_path, make_ctx):
    ctx, proj = _build_project(tmp_path, make_ctx)
    _parity_cases(proj, tmp_path)
    write_manifest(proj)

    engine = _engine_statuses(proj)
    runner = _runner_statuses(tmp_path)

    assert set(engine) == set(runner), "engine and runner judged different case sets"
    drifted = {k: (engine[k], runner[k]) for k in engine if engine[k] != runner[k]}
    assert not drifted, f"verdict drift between judge() and the runner core: {drifted}"

    # Sanity: the fixture really exercises pass, fail AND error outcomes, so a
    # both-sides-wrong regression cannot hide behind agreement alone.
    statuses = {s for s, _ in engine.values()}
    assert statuses == {"pass", "fail", "error"}, statuses
    assert engine["baseline/ws_pass"][0] == "pass"
    assert engine["baseline/exact_fail"][0] == "fail"
    assert engine["baseline/float_special"][0] == "pass"
    if os.name == "posix":
        assert engine["baseline/checker_hang"][0] == "fail"
    assert engine["baseline/no_expectation"][0] == "error"
    assert engine["baseline/timeout"] == ("fail", True)


def test_runner_exits_nonzero_when_cases_fail(tmp_path, make_ctx):
    # The shipped runner (and run.sh, which exec's it) must report failure with a
    # nonzero exit code so a Receiver can use it in scripts/CI. The fixture has
    # failing cases on purpose.
    ctx, proj = _build_project(tmp_path, make_ctx)
    _parity_cases(proj, tmp_path)
    write_manifest(proj)
    shutil.copy2(RUNNER_SRC, str(tmp_path / "morvix_runner.py"))
    proc = subprocess.run(
        [sys.executable, "morvix_runner.py", "sol.py", "--all"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0


def test_runner_quiet_suppresses_per_case_lines(tmp_path, make_ctx):
    ctx, proj = _build_project(tmp_path, make_ctx)
    _parity_cases(proj, tmp_path)
    write_manifest(proj)
    shutil.copy2(RUNNER_SRC, str(tmp_path / "morvix_runner.py"))
    proc = subprocess.run(
        [sys.executable, "morvix_runner.py", "sol.py", "--all", "--quiet"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    # The overall summary still prints, but no per-case PASS/FAIL stream.
    assert "passed (" in proc.stdout
    assert "[PASS]" not in proc.stdout and "[FAIL]" not in proc.stdout


@pytest.mark.skipif(os.name != "posix", reason="signals are POSIX-only")
def test_signal_dimension_agrees(tmp_path, make_ctx):
    ctx, proj = _build_project(tmp_path, make_ctx)
    _case(proj, tmp_path, "sig", "segv\n", None, expected_signal=signal.SIGSEGV.name)
    proj.save()
    write_manifest(proj)

    engine = _engine_statuses(proj)
    runner = _runner_statuses(tmp_path)
    assert engine == runner
    assert engine["baseline/sig"][0] == "pass"
