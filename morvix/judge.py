# The judging engine: build once, run each case, decide pass/fail (Sections 14-17).
#
# This is the heart of a run. It ties the three axes together: the adapter
# builds the solution, the execution model runs each case, the comparator judges
# the output, and the exit/signal/memory dimensions are checked alongside and
# combined (Section 14.7). The shipped runner core mirrors this same logic in
# pure stdlib so a Receiver gets identical verdicts without Morvix.

import os
import signal as signalmod
import tempfile
from typing import Callable, List, Optional

from morvix import process
from morvix.adapters import BuildResult, RunSpec, get_adapter
from morvix.cases import TestCase
from morvix.compare import CompareInput, compare
from morvix.models import ExecEnv, run_case
from morvix.project import Project, Runner, resolve_limits
from morvix.results import CaseResult, RunResult


def build_solution(project: Project, source: str, language: str, workdir: str) -> BuildResult:
    """Compile/assemble the solution, honouring a raw build command if set."""
    if project.raw_build:
        res = process.run(["/bin/sh", "-c", project.raw_build], cwd=project.root, wall_limit=180)
        diag = (res.stdout + res.stderr).decode("utf-8", "replace")
        if not res.ok:
            return BuildResult(
                ok=False,
                diagnostics=diag,
                error="raw build failed",
                build_command=project.raw_build,
            )
        run_cmd = project.raw_run or source
        return BuildResult(
            ok=True,
            artifact=source,
            run_argv=["/bin/sh", "-c", run_cmd],
            build_command=project.raw_build,
        )

    adapter = get_adapter(language)
    return adapter.build(source, project.lang_config(language), workdir)


def _runspec(project: Project, build: BuildResult, language: str) -> RunSpec:
    if project.raw_build or not language:
        return RunSpec(argv=build.run_argv, env=build.run_env)
    return get_adapter(language).run_spec(build, project.lang_config(language))


def _signal_name(num: Optional[int]) -> Optional[str]:
    if num is None:
        return None
    try:
        return signalmod.Signals(num).name
    except ValueError:
        return f"SIG{num}"


def _has_output_expectation(project: Project, case: TestCase, strategy: str) -> bool:
    if strategy == "checker":
        return True
    if case.expected_hash:
        return True
    path = case.expected_output_abspath(project.root)
    return bool(path and os.path.exists(path))


def judge_case(
    project: Project, build: BuildResult, case: TestCase, env: ExecEnv, runner: Optional[Runner]
) -> CaseResult:
    """Run one case and combine every enabled dimension into a verdict."""
    limits = resolve_limits(project, runner, case)
    obs = run_case(project.model, case, env, limits)
    res = obs.result

    result = CaseResult(
        case_id=case.id,
        group=case.group,
        status="pass",
        exit_code=res.exit_code,
        signal=_signal_name(res.term_signal),
        timed_out=res.timed_out,
        wall_time=res.wall_time,
        cpu_time=res.cpu_time,
        peak_mem_kb=res.peak_mem_kb,
    )

    def fail(reason: str, diff: Optional[str] = None):
        result.status = "fail"
        result.verdict = reason
        if diff and (runner is None or runner.diff):
            result.diff = diff

    # --- timeout dimension ---
    if res.timed_out:
        fail("timed out")
        return result

    # --- exit / signal dimension (Section 14.6) ---
    expects_exit = case.expected_exit is not None or case.expected_signal is not None
    if expects_exit:
        ok = True
        if case.expected_signal:
            ok = result.signal == case.expected_signal
        if case.expected_exit is not None:
            ok = ok and res.exit_code == case.expected_exit
        if not ok:
            want = case.expected_signal or f"exit {case.expected_exit}"
            fail(f"expected {want}, got {res.describe_exit()}")
            return result
        # A crash that was expected is a pass; record it plainly.
        result.verdict = f"expected {case.expected_signal or 'exit ' + str(case.expected_exit)}"
    elif res.signaled or (res.exit_code is not None and res.exit_code != 0):
        # No expectation was set, so a clean exit 0 is required. A crash OR any
        # non-zero exit is a failure - even if the output happens to match.
        fail(res.describe_exit())
        return result

    # --- output dimension ---
    strategy = case.compare or (
        runner.compare
        if runner and runner.compare
        else project.compare.get("strategy", "whitespace")
    )
    if case.expected_hash and strategy != "checker":
        strategy = "hash"
    if _has_output_expectation(project, case, strategy):
        expected = b""
        path = case.expected_output_abspath(project.root)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                expected = f.read()
        ci = CompareInput(
            observed=obs.output,
            expected=expected,
            case=case,
            project=project,
            params=project.compare,
        )
        verdict = compare(strategy, ci)
        if not verdict.passed:
            fail(verdict.detail or "output differs", diff=verdict.diff)
            return result
        if not result.verdict:
            result.verdict = "output matches"
    elif not expects_exit:
        result.status = "error"
        result.verdict = "no expected answer (run: gen --expected)"
        return result

    # --- memory-correctness dimension (Section 15.2) ---
    if runner and runner.memcheck:
        result.memcheck = _run_memcheck(project, build, case, env, limits)
        if result.memcheck is False:
            fail("memory error")

    return result


def _run_memcheck(project, build, case, env, limits) -> Optional[bool]:
    """Run the case under valgrind; True = clean, False = errors, None = skipped."""
    valgrind = process.find_tool("valgrind")
    if not valgrind or not build.artifact:
        return None
    argv = [valgrind, "--error-exitcode=99", "--leak-check=full", "-q"] + env.runspec.argv
    stdin = b""
    primary = case.primary_input()
    if primary:
        p = os.path.join(project.root, primary)
        if os.path.exists(p):
            with open(p, "rb") as f:
                stdin = f.read()
    res = process.run(
        argv,
        stdin=stdin,
        cwd=env.workdir,
        env=process.base_env(project.locale),
        wall_limit=(limits.get("wall") or 10) * 4,
    )
    if res.timed_out or res.signaled:
        return None  # valgrind itself was killed - no clean verdict to report
    return res.exit_code != 99


def select_cases(
    project: Project,
    runner: Optional[Runner] = None,
    groups: Optional[List[str]] = None,
    case_ids: Optional[List[str]] = None,
) -> List[TestCase]:
    """Pick which cases a run covers, applying runner scope then explicit filters."""
    cases = list(project.cases)
    if runner and runner.groups:
        cases = [c for c in cases if c.group in runner.groups]
    if runner and runner.cases:
        cases = [c for c in cases if c.id in runner.cases]
    if groups:
        cases = [c for c in cases if c.group in groups]
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c.id in wanted or c.name in wanted]
    return cases


def judge(
    project: Project,
    solution: str,
    language: str,
    cases: List[TestCase],
    runner: Optional[Runner] = None,
    on_case: Optional[Callable[[CaseResult], None]] = None,
) -> RunResult:
    """Build the solution, run every selected case, return the full result.

    on_case is called as each case finishes, so a live table can update.
    """
    run = RunResult(solution=os.path.basename(solution), runner=runner.name if runner else None)
    workdir = tempfile.mkdtemp(prefix="morvix-build-")
    try:
        build = build_solution(project, solution, language, workdir)
        if not build.ok:
            from morvix.errors import MorvixError

            raise MorvixError(build.error or "build failed", hint=build.diagnostics)
        runspec = _runspec(project, build, language)
        env = ExecEnv(project=project, build=build, runspec=runspec, workdir=workdir)
        for case in cases:
            result = judge_case(project, build, case, env, runner)
            run.cases.append(result)
            if on_case:
                on_case(result)
    finally:
        import shutil

        shutil.rmtree(workdir, ignore_errors=True)
    return run
