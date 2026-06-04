# "interactive" execution model (Section 10.5): the program does not just read
# input and print an answer - it holds a conversation with a judge process (the
# "interactor") supplied by the author. The interactor feeds the program data,
# reads its replies, and decides whether the program behaved correctly. Its
# exit code is the verdict: 0 means the program passed.
#
# This is the advanced, less-common model. Unlike the other models it cannot go
# through process.run (which routes stdio through temp files); we need two live
# pipes wired together. So we spawn both children with subprocess.Popen and use
# two background threads to pump bytes between them:
#
#     solution.stdout  -> interactor.stdin
#     interactor.stdout -> solution.stdin
#
# A wall timeout guards the whole exchange; on overrun we kill both sides.

import os
import subprocess
import threading
import time

from morvix.cases import TestCase
from morvix.models import ExecEnv, Observation, register_model, run_env
from morvix.process import ProcessResult


# Build the argv used to launch the interactor. If the file is executable we run
# it directly; otherwise assume it is a Python script and run it with python3.
def _interactor_argv(path: str) -> list:
    if os.access(path, os.X_OK):
        return [path]
    return ["python3", path]


# Copy bytes from one stream to another until the source is exhausted, then
# close the destination so the reader downstream sees end-of-input. Runs in a
# background thread; any error (a side already gone) just ends the pump quietly.
#
# We use read1() rather than read(n): a conversation sends a little at a time
# and waits for a reply, so we must forward whatever bytes are available now
# instead of blocking for a full buffer that will never fill (a deadlock).
def _pump(src, dst):
    try:
        while True:
            chunk = src.read1(65536)
            if not chunk:
                break
            dst.write(chunk)
            dst.flush()
    except (OSError, ValueError):
        pass
    finally:
        try:
            dst.close()
        except OSError:
            pass


def _fail(message: bytes) -> Observation:
    # A synthesized failing result, matching how the library model reports an
    # error: exit code 1, the reason on stderr, everything else zero/False.
    res = ProcessResult(
        exit_code=1,
        term_signal=None,
        timed_out=False,
        wall_time=0.0,
        cpu_time=0.0,
        peak_mem_kb=0,
        stdout=b"",
        stderr=message,
        output_truncated=False,
        mem_exceeded=False,
    )
    return Observation(result=res, output=b"")


def _kill(proc):
    try:
        proc.kill()
    except (OSError, ProcessLookupError):
        pass


def _interactive(case: TestCase, env: ExecEnv, limits: dict) -> Observation:
    interactor = env.project.languages.get("interactor")
    if not interactor:
        return _fail(b"no interactor configured")

    argv = list(_interactor_argv(interactor))
    # The interactor may want the test input file as its first real argument.
    primary = case.primary_input()
    if primary:
        argv.append(os.path.join(env.project.root, primary))

    run_environment = run_env(env)
    wall = limits.get("wall") or 10

    # - spawn the solution and the interactor, each with piped stdin/stdout
    sol = subprocess.Popen(
        list(env.runspec.argv),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        cwd=env.workdir,
        env=run_environment,
    )
    inter = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        cwd=env.workdir,
        env=run_environment,
    )

    # - wire the two together with background copier threads
    t1 = threading.Thread(target=_pump, args=(sol.stdout, inter.stdin), daemon=True)
    t2 = threading.Thread(target=_pump, args=(inter.stdout, sol.stdin), daemon=True)
    t1.start()
    t2.start()

    # - wait for the interactor (the verdict comes from it), bounded by the wall
    start = time.monotonic()
    timed_out = False
    try:
        verdict = inter.wait(timeout=wall)
    except subprocess.TimeoutExpired:
        timed_out = True
        verdict = None
        _kill(inter)
        _kill(sol)

    # The interactor is done (or killed); make sure the solution stops too so we
    # never leave a stray process behind.
    if sol.poll() is None:
        _kill(sol)
    sol.wait()
    wall_time = time.monotonic() - start

    t1.join(timeout=1.0)
    t2.join(timeout=1.0)

    # The verdict is the interactor's exit code: 0 = pass.
    res = ProcessResult(
        exit_code=verdict if not timed_out else None,
        term_signal=None,
        timed_out=timed_out,
        wall_time=wall_time,
        cpu_time=0.0,
        peak_mem_kb=0,
        stdout=b"",
        stderr=b"",
        output_truncated=False,
        mem_exceeded=False,
    )
    return Observation(result=res, output=b"")


register_model("interactive", _interactive)
