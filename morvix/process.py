# The process layer: the bottom of the stack.
#
# Everything that actually runs a program goes through here - the solution
# under test, the reference, generators, checkers, the memory checker. Its job
# is to spawn a process, feed it input, capture its output, and measure and/or
# limit what it used, in a way that behaves the same on Linux and macOS.
#
# The tricky parts it papers over:
#   - peak memory: getrusage reports it in bytes on macOS but kilobytes on
#     Linux, so we normalise to kilobytes here once and nowhere else worries.
#   - per-run accounting: we reap each child with os.wait4 so its rusage is
#     that child's alone, not polluted by earlier runs.
#   - deadlocks: stdin and the captured streams go through temp files, so there
#     is no pipe buffer that can fill up and hang a chatty program.
#   - locale: LC_ALL is forced to C by default so sort order and number
#     formatting are identical everywhere (Section 21.3).
#
# Windows has none of setsid/setrlimit/wait4, so it gets a plain best-effort
# path with no resource limits, exactly as the design promises (Section 21.2).

import os
import shutil
import signal
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from morvix.errors import EnvError

POSIX = os.name == "posix"

if POSIX:
    import resource

# macOS getrusage.ru_maxrss is bytes; Linux is kilobytes.
_MAXRSS_IS_BYTES = sys.platform == "darwin"


@dataclass
class ProcessResult:
    """Everything observable about one run of a program."""

    exit_code: Optional[int]  # None if the process was killed by a signal
    term_signal: Optional[int]  # the signal number, if it was signalled
    timed_out: bool  # we killed it for exceeding the wall limit
    wall_time: float  # seconds, measured by us
    cpu_time: float  # user + system CPU seconds
    peak_mem_kb: int  # peak RSS in kilobytes (approximate)
    stdout: bytes
    stderr: bytes
    output_truncated: bool  # output hit the cap and was cut off
    mem_exceeded: bool  # best-effort: looks like it was killed for memory

    @property
    def signaled(self) -> bool:
        return self.term_signal is not None

    @property
    def ok(self) -> bool:
        """Clean, expected exit: returned 0, no signal, no timeout."""
        return self.exit_code == 0 and not self.signaled and not self.timed_out

    def describe_exit(self) -> str:
        """Short human phrase for the outcome, used in reports and messages."""
        if self.timed_out:
            return "timed out"
        if self.signaled:
            name = signal.Signals(self.term_signal).name if self.term_signal else "?"
            return f"killed by {name}"
        return f"exit {self.exit_code}"


def find_tool(name: str) -> Optional[str]:
    """Return the path to a tool on PATH, or None if it is not installed."""
    return shutil.which(name)


def require_tool(name: str, install_hint: Optional[str] = None) -> str:
    """Like find_tool, but raises a clear environment error when missing."""
    path = shutil.which(name)
    if path is None:
        hint = install_hint or f"Install {name} and make sure it is on your PATH."
        raise EnvError(f"Required tool '{name}' was not found.", hint=hint)
    return path


def base_env(
    locale: Optional[str] = "C", overrides: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Build the environment for a run.

    Starts from the current environment, pins the locale (C by default, the
    deterministic choice from Section 21.3), then applies any overrides.
    """
    env = dict(os.environ)
    if locale:
        env["LC_ALL"] = locale
        env["LANG"] = locale
    if overrides:
        env.update(overrides)
    return env


def run(
    argv: List[str],
    *,
    stdin: Optional[bytes] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    locale: Optional[str] = "C",
    wall_limit: Optional[float] = None,
    cpu_limit: Optional[float] = None,
    mem_limit_kb: Optional[int] = None,
    output_cap_bytes: Optional[int] = None,
) -> ProcessResult:
    """Run a program once and report what it did.

    - argv:            the command and its arguments (argv[0] must be runnable).
    - stdin:           bytes fed on standard input (None means no input).
    - wall_limit:      kill it after this many real seconds (None = no timeout).
    - cpu_limit:       hard CPU-seconds cap via RLIMIT_CPU (POSIX only).
    - mem_limit_kb:    hard address-space cap via RLIMIT_AS (POSIX only).
    - output_cap_bytes: stop capturing past this many bytes of stdout.

    Returns a ProcessResult; it never raises for a program that merely crashed
    or timed out - that is normal data, not an error.
    """
    full_env = env if env is not None else base_env(locale)
    if not POSIX:
        return _run_windows(argv, stdin, cwd, full_env, wall_limit, output_cap_bytes)
    return _run_posix(
        argv, stdin, cwd, full_env, wall_limit, cpu_limit, mem_limit_kb, output_cap_bytes
    )


def _run_posix(argv, stdin_bytes, cwd, env, wall_limit, cpu_limit, mem_limit_kb, output_cap):
    # Route stdin and the captured streams through temp files. This sidesteps
    # the classic pipe-deadlock (a program that writes a lot before reading)
    # without us having to juggle reader threads.
    tmpdir = tempfile.mkdtemp(prefix="morvix-run-")
    in_path = os.path.join(tmpdir, "stdin")
    out_path = os.path.join(tmpdir, "stdout")
    err_path = os.path.join(tmpdir, "stderr")

    with open(in_path, "wb") as f:
        if stdin_bytes:
            f.write(stdin_bytes)

    def child_setup():
        # Runs in the forked child, before exec. New session so we can kill the
        # whole group on timeout, plus the hard resource caps.
        os.setsid()
        if cpu_limit is not None:
            sec = int(cpu_limit) + 1
            resource.setrlimit(resource.RLIMIT_CPU, (sec, sec))
        if mem_limit_kb is not None:
            nbytes = int(mem_limit_kb) * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (nbytes, nbytes))
            except (ValueError, OSError):
                # RLIMIT_AS is not honoured on some platforms (notably macOS);
                # we just skip it rather than fail the run.
                pass

    start = time.monotonic()
    pid = None
    try:
        fin = os.open(in_path, os.O_RDONLY)
        fout = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        ferr = os.open(err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            import subprocess

            proc = subprocess.Popen(
                argv,
                stdin=fin,
                stdout=fout,
                stderr=ferr,
                cwd=cwd,
                env=env,
                preexec_fn=child_setup,
                close_fds=True,
            )
            pid = proc.pid
        finally:
            os.close(fin)
            os.close(fout)
            os.close(ferr)

        status, rusage, timed_out = _wait_with_timeout(pid, wall_limit)
        wall = time.monotonic() - start

        # Tell Popen the child is already reaped so it does not wait again.
        proc.returncode = 0

        exit_code, term_signal = _decode_status(status)
        cpu = rusage.ru_utime + rusage.ru_stime if rusage else 0.0
        peak_kb = _maxrss_to_kb(rusage.ru_maxrss) if rusage else 0

        stdout, out_trunc = _read_capped(out_path, output_cap)
        stderr, _ = _read_capped(err_path, output_cap)

        mem_exceeded = (
            mem_limit_kb is not None
            and not timed_out
            and term_signal in (signal.SIGKILL, signal.SIGSEGV, signal.SIGABRT)
        )

        return ProcessResult(
            exit_code=exit_code if not timed_out else None,
            term_signal=term_signal,
            timed_out=timed_out,
            wall_time=wall,
            cpu_time=cpu,
            peak_mem_kb=peak_kb,
            stdout=stdout,
            stderr=stderr,
            output_truncated=out_trunc,
            mem_exceeded=mem_exceeded,
        )
    except FileNotFoundError as exc:
        raise EnvError(
            f"Could not run '{argv[0]}': {exc.strerror}.",
            hint="Check the command exists and the path is correct.",
        )
    except PermissionError as exc:
        raise EnvError(
            f"Permission denied running '{argv[0]}': {exc.strerror}.",
            hint="Make sure the file is executable (chmod +x).",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _wait_with_timeout(pid, wall_limit):
    """Wait for a child, killing its group if it overruns the wall limit.

    Returns (status, rusage, timed_out). Uses os.wait4 so the rusage belongs
    to this child alone.
    """
    if wall_limit is None:
        _, status, rusage = os.wait4(pid, 0)
        return status, rusage, False

    deadline = time.monotonic() + wall_limit
    sleep = 0.001
    while True:
        done, status, rusage = os.wait4(pid, os.WNOHANG)
        if done != 0:
            return status, rusage, False
        if time.monotonic() >= deadline:
            _kill_group(pid)
            _, status, rusage = os.wait4(pid, 0)
            return status, rusage, True
        time.sleep(sleep)
        if sleep < 0.02:
            sleep *= 1.5  # back off so we are responsive but not busy-looping


def _kill_group(pid):
    for sig in (signal.SIGKILL,):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return


def _decode_status(status):
    """Turn a raw wait status into (exit_code, signal_number)."""
    if os.WIFSIGNALED(status):
        return None, os.WTERMSIG(status)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status), None
    return None, None


def _maxrss_to_kb(maxrss: int) -> int:
    return int(maxrss // 1024) if _MAXRSS_IS_BYTES else int(maxrss)


def _read_capped(path, cap):
    """Read a file, optionally stopping at a byte cap. Returns (data, truncated)."""
    with open(path, "rb") as f:
        if cap is None:
            return f.read(), False
        data = f.read(cap + 1)
        if len(data) > cap:
            return data[:cap], True
        return data, False


def _run_windows(argv, stdin_bytes, cwd, env, wall_limit, output_cap):
    # Best-effort path: the Python core still runs, but resource limits and
    # precise CPU/memory accounting are not available here.
    import subprocess

    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            input=stdin_bytes or b"",
            cwd=cwd,
            env=env,
            capture_output=True,
            timeout=wall_limit,
        )
        wall = time.monotonic() - start
        stdout = proc.stdout[:output_cap] if output_cap else proc.stdout
        trunc = bool(output_cap and len(proc.stdout) > output_cap)
        return ProcessResult(
            exit_code=proc.returncode,
            term_signal=None,
            timed_out=False,
            wall_time=wall,
            cpu_time=0.0,
            peak_mem_kb=0,
            stdout=stdout,
            stderr=proc.stderr,
            output_truncated=trunc,
            mem_exceeded=False,
        )
    except subprocess.TimeoutExpired as exc:
        wall = time.monotonic() - start
        return ProcessResult(
            exit_code=None,
            term_signal=None,
            timed_out=True,
            wall_time=wall,
            cpu_time=0.0,
            peak_mem_kb=0,
            stdout=(exc.stdout or b"")[: output_cap or None],
            stderr=exc.stderr or b"",
            output_truncated=False,
            mem_exceeded=False,
        )
    except FileNotFoundError as exc:
        raise EnvError(f"Could not run '{argv[0]}': {exc.strerror}.")
