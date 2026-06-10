#!/usr/bin/env python3
# The shippable runner core: a single, self-contained, stdlib-only script.
#
# This file travels INSIDE every shared package (Section 16, Section 20.1). It
# is the sacred path: a Receiver with nothing but a Python 3 install must be
# able to run the harness on a clean machine. So it imports NOTHING from morvix
# and uses ONLY the standard library, and it targets Python 3.6+ (no walrus, no
# match, no 3.10+ typing).
#
# It is config-driven. It reads morvix.json (the manifest) for everything: the
# model, comparison, limits, languages, the case index and the runner profiles.
# It then mirrors the same judging logic Morvix itself uses (process.py,
# judge.py, compare.py/comparators.py, results.py) so the verdicts match.
#
# The whole thing is one file on purpose. It is organised top to bottom as:
#   - process layer (run a program, measure/limit it; POSIX + Windows fallback)
#   - language build (python/c/cpp/java/rust/nasm + raw build/run escape hatch)
#   - comparison (exact, whitespace, float, hash, checker)
#   - judging (build once, run each case, combine dimensions)
#   - results (json/markdown/text export, plus a terminal table)
#   - the CLI

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

POSIX = os.name == "posix"

if POSIX:
    import resource

# macOS getrusage.ru_maxrss is bytes; Linux is kilobytes. Normalise once here.
_MAXRSS_IS_BYTES = sys.platform == "darwin"

# Where the manifest lives and where its referenced files are rooted. A project
# keeps it under .morvix/; case paths are stored relative to the package root
# (the directory that contains .morvix/).
MANIFEST_NAME = "morvix.json"
STATE_DIR = ".morvix"

# Map a source file extension to a language name (mirrors adapters/__init__.py).
_EXTENSIONS = {
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".c++": "cpp",
    ".hpp": "cpp",
    ".asm": "nasm",
    ".s": "nasm",
    ".nasm": "nasm",
    ".py": "python",
    ".java": "java",
    ".rs": "rust",
}

# Languages where a valgrind memcheck is meaningful.
_NATIVE_LANGS = ("c", "cpp", "nasm")

# Manifest models we have already noted as unsupported, so we warn only once.
_NOTED_MODELS = set()


# ===========================================================================
# Process layer (mirrors morvix/process.py)
# ===========================================================================


class ProcessResult(object):
    """Everything observable about one run of a program."""

    def __init__(
        self,
        exit_code,
        term_signal,
        timed_out,
        wall_time,
        cpu_time,
        peak_mem_kb,
        stdout,
        stderr,
        output_truncated,
        mem_exceeded,
    ):
        self.exit_code = exit_code  # None if killed by a signal
        self.term_signal = term_signal  # the signal number, if signalled
        self.timed_out = timed_out  # we killed it for the wall limit
        self.wall_time = wall_time  # seconds, measured by us
        self.cpu_time = cpu_time  # user + system CPU seconds
        self.peak_mem_kb = peak_mem_kb  # peak RSS in KB (approximate)
        self.stdout = stdout
        self.stderr = stderr
        self.output_truncated = output_truncated
        self.mem_exceeded = mem_exceeded

    @property
    def signaled(self):
        return self.term_signal is not None

    @property
    def ok(self):
        return self.exit_code == 0 and not self.signaled and not self.timed_out

    def describe_exit(self):
        if self.timed_out:
            return "timed out"
        if self.signaled:
            return "killed by " + _signal_name(self.term_signal)
        return "exit " + str(self.exit_code)


def _signal_name(num):
    if num is None:
        return "?"
    try:
        return signal.Signals(num).name
    except (ValueError, AttributeError):
        return "SIG" + str(num)


def _stderr_tail(stderr, limit=200):
    # The last non-empty line of stderr - usually the real diagnosis when a run
    # exits badly (a traceback's exception line, "can't open file", an assertion).
    # Mirrors judge._stderr_tail.
    if not stderr:
        return ""
    for line in reversed(stderr.decode("utf-8", "replace").splitlines()):
        line = line.strip()
        if line:
            return line[:limit]
    return ""


def _with_stderr(detail, stderr):
    tail = _stderr_tail(stderr)
    return ("%s: %s" % (detail, tail)) if tail else detail


def find_tool(name):
    return shutil.which(name)


def base_env(locale="C", overrides=None):
    # Start from the current environment, pin the locale (C by default, the
    # deterministic choice from Section 21.3), then apply any overrides.
    env = dict(os.environ)
    if locale:
        env["LC_ALL"] = locale
        env["LANG"] = locale
    if overrides:
        env.update(overrides)
    return env


def run(
    argv,
    stdin=None,
    cwd=None,
    env=None,
    locale="C",
    wall_limit=None,
    cpu_limit=None,
    mem_limit_kb=None,
    output_cap_bytes=None,
):
    """Run a program once and report what it did.

    Never raises for a program that merely crashed or timed out - that is data,
    not an error. A missing/unrunnable command does raise RunnerError.
    """
    full_env = env if env is not None else base_env(locale)
    if not POSIX:
        return _run_windows(argv, stdin, cwd, full_env, wall_limit, output_cap_bytes)
    return _run_posix(
        argv, stdin, cwd, full_env, wall_limit, cpu_limit, mem_limit_kb, output_cap_bytes
    )


def _run_posix(argv, stdin_bytes, cwd, env, wall_limit, cpu_limit, mem_limit_kb, output_cap):
    # Route stdin and the captured streams through temp files so a chatty
    # program can never deadlock on a full pipe buffer.
    tmpdir = tempfile.mkdtemp(prefix="morvix-run-")
    in_path = os.path.join(tmpdir, "stdin")
    out_path = os.path.join(tmpdir, "stdout")
    err_path = os.path.join(tmpdir, "stderr")

    with open(in_path, "wb") as f:
        if stdin_bytes:
            f.write(stdin_bytes)

    def child_setup():
        # In the forked child, before exec: new session (so we can kill the
        # whole group on timeout) plus the hard resource caps.
        os.setsid()
        if cpu_limit is not None:
            sec = int(cpu_limit) + 1
            resource.setrlimit(resource.RLIMIT_CPU, (sec, sec))
        if mem_limit_kb is not None:
            nbytes = int(mem_limit_kb) * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (nbytes, nbytes))
            except (ValueError, OSError):
                # RLIMIT_AS is not honoured everywhere (notably macOS); skip it.
                pass

    start = time.monotonic()
    try:
        fin = os.open(in_path, os.O_RDONLY)
        fout = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        ferr = os.open(err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
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
        cpu = (rusage.ru_utime + rusage.ru_stime) if rusage else 0.0
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
        raise RunnerError("Could not run '%s': %s." % (argv[0], exc.strerror))
    except PermissionError as exc:
        raise RunnerError("Permission denied running '%s': %s." % (argv[0], exc.strerror))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _wait_with_timeout(pid, wall_limit):
    # Wait for the child with os.wait4, so its rusage is that child's alone.
    # Kill the whole process group if it overruns the wall limit.
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
            sleep *= 1.5  # back off: responsive but not busy-looping


def _kill_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _decode_status(status):
    if os.WIFSIGNALED(status):
        return None, os.WTERMSIG(status)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status), None
    return None, None


def _maxrss_to_kb(maxrss):
    return int(maxrss // 1024) if _MAXRSS_IS_BYTES else int(maxrss)


def _read_capped(path, cap):
    with open(path, "rb") as f:
        if cap is None:
            return f.read(), False
        data = f.read(cap + 1)
        if len(data) > cap:
            return data[:cap], True
        return data, False


def _run_windows(argv, stdin_bytes, cwd, env, wall_limit, output_cap):
    # Best-effort path: no resource limits, no precise CPU/memory accounting,
    # exactly as the design promises (Section 21.2).
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            input=stdin_bytes or b"",
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
        out = exc.stdout or b""
        return ProcessResult(
            exit_code=None,
            term_signal=None,
            timed_out=True,
            wall_time=wall,
            cpu_time=0.0,
            peak_mem_kb=0,
            stdout=(out[:output_cap] if output_cap else out),
            stderr=exc.stderr or b"",
            output_truncated=False,
            mem_exceeded=False,
        )
    except FileNotFoundError as exc:
        raise RunnerError("Could not run '%s': %s." % (argv[0], exc.strerror))


class RunnerError(Exception):
    """A fatal, user-facing problem (bad config, missing tool, build failure)."""

    pass


# ===========================================================================
# Building the solution (mirrors judge.build_solution + the language adapters)
# ===========================================================================


class Build(object):
    """The outcome of compiling/assembling: how to run it, or why it failed."""

    def __init__(
        self, ok, artifact=None, run_argv=None, run_env=None, diagnostics="", build_command=""
    ):
        self.ok = ok
        self.artifact = artifact  # binary / class dir / script path
        self.run_argv = run_argv or []
        self.run_env = run_env or {}
        self.diagnostics = diagnostics  # toolchain output, shown on failure
        self.build_command = build_command


def require_tool(name):
    path = shutil.which(name)
    if path is None:
        raise RunnerError("Required tool '%s' was not found on PATH." % name)
    return path


def detect_language(path):
    return _EXTENSIONS.get(os.path.splitext(path)[1].lower())


def looks_like_binary(path):
    """Heuristic: True when path is a compiled artifact rather than source.

    Receivers in C/Java often pass a.out or Main.class by mistake; feeding that
    to a compiler (or py_compile) yields a baffling error like "source code
    string cannot contain null bytes". A NUL byte in the first chunk is the
    classic text/binary test; we also match a few executable magic numbers.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
    except (OSError, IOError):
        return False
    if not chunk:
        return False
    if b"\x00" in chunk:
        return True
    magics = (
        b"\x7fELF",  # Linux ELF
        b"\xca\xfe\xba\xbe",  # Java .class / Mach-O fat
        b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit
        b"\xfe\xed\xfa\xce",  # Mach-O 32-bit
        b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit (BE)
        b"MZ",  # Windows PE
    )
    for m in magics:
        if chunk.startswith(m):
            return True
    return False


def build_solution(manifest, source, language, workdir):
    """Build the solution, honouring a raw build command if the manifest sets one."""
    raw_build = manifest.get("raw_build")
    raw_run = manifest.get("raw_run")
    if raw_build:
        res = run(["/bin/sh", "-c", raw_build], cwd=manifest["_root"], wall_limit=180)
        diag = (res.stdout + res.stderr).decode("utf-8", "replace")
        if not res.ok:
            return Build(ok=False, diagnostics=diag, build_command=raw_build)
        run_cmd = raw_run or source
        return Build(
            ok=True, artifact=source, run_argv=["/bin/sh", "-c", run_cmd], build_command=raw_build
        )

    config = manifest.get("languages", {}).get(language, {})
    builder = _BUILDERS.get(language)
    if builder is None:
        raise RunnerError(
            "No builder for language '%s'. Supported: %s. Or use a raw build/run."
            % (language, ", ".join(sorted(_BUILDERS)))
        )
    return builder(source, config, workdir)


def _build_python(source, config, workdir):
    interpreter = config.get("interpreter")
    if not interpreter:
        # "python3" is the norm on POSIX; on Windows it may not exist, so fall
        # back to the interpreter running this runner (always a Python 3).
        interpreter = "python3" if find_tool("python3") else (sys.executable or "python")
    require_tool(interpreter)
    # A lightweight syntax check, so errors surface at build time.
    cmd = [interpreter, "-m", "py_compile", source]
    res = run(cmd, wall_limit=30)
    if not res.ok:
        diag = (res.stdout + res.stderr).decode("utf-8", "replace")
        return Build(ok=False, diagnostics=diag, build_command=" ".join(cmd))
    return Build(
        ok=True, artifact=source, run_argv=[interpreter, source], build_command=" ".join(cmd)
    )


# Shared logic for the gcc/g++/cc family (C and C++ differ only in defaults).
def _build_cfamily(source, config, workdir, default_compiler, default_std):
    compiler = config.get("compiler", default_compiler)
    require_tool(compiler)
    artifact = os.path.join(workdir, "a.out")
    cmd = [compiler, "-o", artifact, source]

    std = config.get("std", default_std)
    if std:
        cmd.append("-std=" + str(std))
    opt = config.get("opt")
    if opt:
        cmd.append("-" + str(opt))
    for flag in config.get("flags", []):
        cmd.append(flag)
    for inc in config.get("include", []):
        cmd.extend(["-I", inc])
    for libdir in config.get("libdirs", []):
        cmd.extend(["-L", libdir])
    for lib in config.get("lib", []):
        cmd.append("-l" + str(lib))

    res = run(cmd, wall_limit=180)
    if not res.ok:
        diag = (res.stdout + res.stderr).decode("utf-8", "replace")
        return Build(ok=False, diagnostics=diag, build_command=" ".join(cmd))
    return Build(ok=True, artifact=artifact, run_argv=[artifact], build_command=" ".join(cmd))


def _build_c(source, config, workdir):
    return _build_cfamily(source, config, workdir, "gcc", config.get("std"))


def _build_cpp(source, config, workdir):
    return _build_cfamily(source, config, workdir, "g++", "c++20")


def _build_rust(source, config, workdir):
    rustc = config.get("rustc", "rustc")
    require_tool(rustc)
    artifact = os.path.join(workdir, "a.out")
    cmd = [rustc]
    edition = config.get("edition")
    if edition:
        cmd.extend(["--edition", str(edition)])
    if config.get("release"):
        cmd.append("-O")
    cmd.extend([source, "-o", artifact])
    res = run(cmd, wall_limit=180)
    if not res.ok:
        diag = (res.stdout + res.stderr).decode("utf-8", "replace")
        return Build(ok=False, diagnostics=diag, build_command=" ".join(cmd))
    return Build(ok=True, artifact=artifact, run_argv=[artifact], build_command=" ".join(cmd))


def _build_nasm(source, config, workdir):
    # Two-step: assemble with nasm, then link with gcc/cc (or ld).
    assembler = config.get("assembler", "nasm")
    fmt = config.get("format", "macho64" if sys.platform == "darwin" else "elf64")
    linker = config.get("link", "gcc")
    asm = require_tool(assembler)

    obj = os.path.join(workdir, "obj.o")
    asm_cmd = [asm, "-f", fmt] + list(config.get("flags", [])) + [source, "-o", obj]
    res = run(asm_cmd, wall_limit=180)
    if not res.ok:
        diag = (res.stdout + res.stderr).decode("utf-8", "replace")
        return Build(ok=False, diagnostics=diag, build_command=" ".join(asm_cmd))

    out = os.path.join(workdir, "a.out")
    link_flags = list(config.get("linkflags", []))
    if linker == "ld":
        ld = require_tool("ld")
        link_cmd = [ld, obj, "-o", out] + link_flags
    else:
        cc = shutil.which("gcc") or shutil.which("cc") or require_tool("gcc")
        link_cmd = [cc, obj, "-o", out] + link_flags
    res2 = run(link_cmd, wall_limit=180)
    if not res2.ok:
        diag = (res2.stdout + res2.stderr).decode("utf-8", "replace")
        return Build(ok=False, diagnostics=diag, build_command=" ".join(link_cmd))
    return Build(
        ok=True,
        artifact=out,
        run_argv=[out],
        build_command=" ".join(asm_cmd) + " && " + " ".join(link_cmd),
    )


def _build_java(source, config, workdir):
    javac = config.get("javac", "javac")
    java = config.get("java", "java")
    classpath = config.get("classpath", "")
    release = config.get("release")
    require_tool(javac)
    require_tool(java)

    source_dir = os.path.dirname(source) or "."
    cmd = [javac, "-d", workdir]
    if release:
        cmd += ["--release", str(release)]
    if classpath:
        cmd += ["-cp", classpath]
    cmd += ["-sourcepath", source_dir, source]
    res = run(cmd, wall_limit=180)
    if not res.ok:
        diag = (res.stdout + res.stderr).decode("utf-8", "replace")
        return Build(ok=False, diagnostics=diag, build_command=" ".join(cmd))

    main_class = _java_main_class(source)
    rt_cp = workdir + ((os.pathsep + classpath) if classpath else "")
    return Build(
        ok=True,
        artifact=workdir,
        run_argv=[java, "-cp", rt_cp, main_class],
        build_command=" ".join(cmd),
    )


def _java_main_class(source):
    # The class name is the file stem; prepend the package if one is declared.
    import re

    stem = os.path.splitext(os.path.basename(source))[0]
    try:
        text = open(source, encoding="utf-8", errors="replace").read()
    except OSError:
        return stem
    m = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.MULTILINE)
    if m:
        return m.group(1) + "." + stem
    return stem


_BUILDERS = {
    "python": _build_python,
    "c": _build_c,
    "cpp": _build_cpp,
    "rust": _build_rust,
    "nasm": _build_nasm,
    "java": _build_java,
}


# ===========================================================================
# Comparison (mirrors morvix/compare.py + comparators.py)
# ===========================================================================


class Verdict(object):
    def __init__(self, passed, detail="", diff=None):
        self.passed = passed
        self.detail = detail
        self.diff = diff


def make_diff(expected, observed, context=3):
    import difflib

    exp = expected.decode("utf-8", "replace").splitlines()
    obs = observed.decode("utf-8", "replace").splitlines()
    lines = difflib.unified_diff(exp, obs, "expected", "observed", n=context, lineterm="")
    return "\n".join(lines)


def _cmp_exact(observed, expected, case, params):
    if observed == expected:
        return Verdict(True)
    return Verdict(False, "output differs", diff=make_diff(expected, observed))


def _normalize_ws(data):
    # Collapse runs of whitespace and strip each line, then drop trailing blanks.
    text = data.decode("utf-8", "replace")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).encode("utf-8")


def _cmp_whitespace(observed, expected, case, params):
    if _normalize_ws(observed) == _normalize_ws(expected):
        return Verdict(True)
    return Verdict(
        False, "output differs (ignoring whitespace)", diff=make_diff(expected, observed)
    )


def _cmp_float(observed, expected, case, params):
    eps_abs = params.get("epsilon_abs", 1e-6)
    eps_rel = params.get("epsilon_rel", 1e-9)
    obs_tokens = observed.decode("utf-8", "replace").split()
    exp_tokens = expected.decode("utf-8", "replace").split()
    if len(obs_tokens) != len(exp_tokens):
        detail = "token count mismatch: expected %d, got %d" % (len(exp_tokens), len(obs_tokens))
        return Verdict(False, detail, diff=make_diff(expected, observed))
    for i in range(len(exp_tokens)):
        a_tok, b_tok = exp_tokens[i], obs_tokens[i]
        # Fast path (mirrors comparators.py): identical strings always match -
        # this is what handles inf, nan, -inf, 1e400 and the like.
        if a_tok == b_tok:
            continue
        try:
            a = float(a_tok)
            b = float(b_tok)
            diff = abs(a - b)
            scale = max(abs(a), abs(b))
            if diff <= eps_abs or (scale > 0 and diff <= eps_rel * scale):
                continue
            detail = "token %d: expected %r, got %r (diff %s)" % (i, a_tok, b_tok, diff)
            return Verdict(False, detail, diff=make_diff(expected, observed))
        except ValueError:
            if a_tok != b_tok:
                detail = "token %d: expected %r, got %r" % (i, a_tok, b_tok)
                return Verdict(False, detail, diff=make_diff(expected, observed))
    return Verdict(True)


def _cmp_hash(observed, expected, case, params):
    observed_hex = hashlib.sha256(observed).hexdigest()
    expected_hex = case.get("expected_hash") or ""
    if observed_hex == expected_hex:
        return Verdict(True)
    detail = "hash mismatch: expected %s..., got %s..." % (expected_hex[:12], observed_hex[:12])
    return Verdict(False, detail)


def _cmp_checker(observed, expected, case, params):
    # Delegate to an external special-judge: [checker, input_file, observed_file].
    # Exit 0 means accepted; any other exit means rejected. The checker gets 4x
    # the case's wall limit (mirrors comparators.py) so a looping checker can
    # never hang the whole run.
    checker_path = params.get("checker")
    if not checker_path:
        return Verdict(False, "no checker configured")
    root = params.get("_root", ".")
    input_rel = _primary_input(case)
    input_file = os.path.join(root, input_rel) if input_rel else os.devnull
    fd, tmp_path = tempfile.mkstemp(prefix="morvix-checker-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(observed)
        wall = (params.get("_wall") or 10) * 4
        result = run([checker_path, input_file, tmp_path], wall_limit=wall)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    if result.timed_out:
        return Verdict(False, "checker timed out")
    if result.exit_code == 0:
        return Verdict(True)
    return Verdict(False, "checker rejected")


_COMPARATORS = {
    "exact": _cmp_exact,
    "whitespace": _cmp_whitespace,
    "float": _cmp_float,
    "hash": _cmp_hash,
    "checker": _cmp_checker,
}


def compare(strategy, observed, expected, case, params):
    fn = _COMPARATORS.get(strategy)
    if fn is None:
        known = ", ".join(sorted(_COMPARATORS))
        raise RunnerError(
            "Unknown comparison strategy '%s'. Choose one of: %s." % (strategy, known)
        )
    return fn(observed, expected, case, params)


# ===========================================================================
# Case results + run results (mirrors morvix/results.py)
# ===========================================================================


class CaseResult(object):
    def __init__(self, case_id, group):
        self.case_id = case_id
        self.group = group
        self.status = "pass"  # pass | fail | skip | error
        self.verdict = ""
        self.exit_code = None
        self.signal = None
        self.timed_out = False
        self.wall_time = 0.0
        self.cpu_time = 0.0
        self.peak_mem_kb = 0
        self.diff = None
        self.memcheck = None  # valgrind verdict; None if not run

    @property
    def passed(self):
        return self.status == "pass"

    def to_dict(self):
        d = {
            "case": self.case_id,
            "group": self.group,
            "status": self.status,
            "verdict": self.verdict,
            "wall_time": round(self.wall_time, 6),
            "cpu_time": round(self.cpu_time, 6),
            "peak_mem_kb": self.peak_mem_kb,
        }
        if self.exit_code is not None:
            d["exit_code"] = self.exit_code
        if self.signal is not None:
            d["signal"] = self.signal
        if self.timed_out:
            d["timed_out"] = True
        if self.memcheck is not None:
            d["memcheck"] = self.memcheck
        return d

    @staticmethod
    def from_dict(d):
        cr = CaseResult(d.get("case", ""), d.get("group", ""))
        cr.status = d.get("status", "pass")
        cr.verdict = d.get("verdict", "")
        cr.exit_code = d.get("exit_code")
        cr.signal = d.get("signal")
        cr.timed_out = d.get("timed_out", False)
        cr.wall_time = d.get("wall_time", 0.0)
        cr.cpu_time = d.get("cpu_time", 0.0)
        cr.peak_mem_kb = d.get("peak_mem_kb", 0)
        cr.memcheck = d.get("memcheck")
        return cr


class RunResult(object):
    def __init__(self, solution, runner=None):
        self.solution = solution
        self.runner = runner
        self.cases = []
        from datetime import datetime

        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.memory_note = "peak, approximate"  # honest label (Section 15.1)

    @staticmethod
    def from_json(d):
        r = RunResult(d.get("solution", ""), d.get("runner"))
        r.started_at = d.get("started_at", "")
        r.memory_note = d.get("memory_note", "peak, approximate")
        r.cases = [CaseResult.from_dict(c) for c in d.get("cases", [])]
        return r

    @property
    def total(self):
        return len(self.cases)

    @property
    def passed(self):
        return sum(1 for c in self.cases if c.status == "pass")

    @property
    def failed(self):
        return sum(1 for c in self.cases if c.status in ("fail", "error"))

    @property
    def skipped(self):
        return sum(1 for c in self.cases if c.status == "skip")

    @property
    def all_passed(self):
        return self.failed == 0 and self.total > 0

    def by_group(self):
        groups = {}
        for c in self.cases:
            groups.setdefault(c.group, []).append(c)
        return groups


# --- performance aggregation + formatting (mirrors morvix/results.py) ---


def fmt_secs(s):
    return "%.3fs" % s


def fmt_mem_kb(kb):
    if kb <= 0:
        return "n/a"
    if kb < 1024:
        return "%d KB" % kb
    return "%.1f MB" % (kb / 1024.0)


def pct(passed, total):
    return ("%.0f%%" % (100.0 * passed / total)) if total else "0%"


def performance(run_result, slowest_n=5):
    cases = [c for c in run_result.cases if c.status != "skip"]
    walls = [c.wall_time for c in cases]
    cpus = [c.cpu_time for c in cases]
    mems = [c.peak_mem_kb for c in cases]
    have_mem = any(m > 0 for m in mems)

    def stats(xs):
        if not xs:
            return {"total": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
        return {"total": sum(xs), "avg": sum(xs) / len(xs), "min": min(xs), "max": max(xs)}

    slowest = sorted(
        [c for c in cases if c.wall_time > 0], key=lambda c: c.wall_time, reverse=True
    )[:slowest_n]
    return {
        "cases": len(cases),
        "wall": stats(walls),
        "cpu": stats(cpus),
        "memory_kb": ({"max": max(mems), "avg": sum(mems) / len(mems)} if have_mem else None),
        "slowest": [{"case": c.case_id, "wall_time": round(c.wall_time, 6)} for c in slowest],
    }


def perf_text_lines(run_result, slowest_n=5, show_time=True, show_mem=True):
    p = performance(run_result, slowest_n)
    if not p["cases"]:
        return []
    lines = ["Performance:"]
    if show_time:
        w, c = p["wall"], p["cpu"]
        lines.append(
            "  wall   total %s   avg %s   min %s   max %s"
            % (fmt_secs(w["total"]), fmt_secs(w["avg"]), fmt_secs(w["min"]), fmt_secs(w["max"]))
        )
        lines.append("  cpu    total %s   max %s" % (fmt_secs(c["total"]), fmt_secs(c["max"])))
    if show_mem and p["memory_kb"]:
        m = p["memory_kb"]
        lines.append(
            "  memory max %s   avg %s   (%s)"
            % (fmt_mem_kb(m["max"]), fmt_mem_kb(int(m["avg"])), run_result.memory_note)
        )
    if p["slowest"]:
        lines.append(
            "  slowest "
            + ", ".join("%s %s" % (s["case"], fmt_secs(s["wall_time"])) for s in p["slowest"])
        )
    return lines


def _cmp_cell(cr, show_mem):
    if cr is None:
        return "-"
    if cr.timed_out:
        return "timeout"
    s = fmt_secs(cr.wall_time)
    if show_mem and cr.peak_mem_kb > 0:
        s += " " + fmt_mem_kb(cr.peak_mem_kb)
    if cr.status != "pass":
        s = cr.status.upper() + " " + s
    return s


def comparison_block(main_run, rival_cols, show_mem=True, per_case=True):
    """Solution-vs-rivals comparison text (mirrors morvix/results.py)."""
    cols = [{"label": "solution", "run": main_run, "precomputed": False, "env": ""}] + list(
        rival_cols
    )
    lines = []
    if per_case:
        index = [(c["label"], dict((x.case_id, x) for x in c["run"].cases)) for c in cols]
        header = "  %-22s" % "Case"
        for label, _ in index:
            header += " | %-20s" % label
        lines.append(header)
        for case in main_run.cases:
            row = "  %-22s" % case.case_id
            for _, by in index:
                row += " | %-20s" % _cmp_cell(by.get(case.case_id), show_mem)
            lines.append(row)
        lines.append("")
    lines.append("Comparison (vs solution):")
    # Aggregate each column over ONLY the cases in this run (a precomputed rival
    # may cover every case while the solution run was filtered with --case).
    main_ids = set(c.case_id for c in main_run.cases)

    def _aligned(run):
        sub = RunResult(run.solution)
        sub.cases = [c for c in run.cases if c.case_id in main_ids]
        return sub

    main_total = performance(_aligned(main_run))["wall"]["total"] or 1e-9
    for c in cols:
        run = _aligned(c["run"])
        p = performance(run)
        bits = "wall total %s  avg %s" % (fmt_secs(p["wall"]["total"]), fmt_secs(p["wall"]["avg"]))
        if show_mem:
            bits += "  peak %s" % (fmt_mem_kb(p["memory_kb"]["max"]) if p["memory_kb"] else "n/a")
        ratio = "" if c["label"] == "solution" else "  %.2fx" % (p["wall"]["total"] / main_total)
        note = (
            "  %d/%d pass" % (run.passed, run.total) if run.total and run.passed < run.total else ""
        )
        tag = ""
        if c.get("precomputed"):
            tag = "  [precomputed: %s]" % c["env"] if c.get("env") else "  [precomputed]"
        lines.append("  %-14s %s%s%s%s" % (c["label"], bits, ratio, note, tag))
    return lines


def result_to_json(run_result):
    groups = {}
    for g, cs in run_result.by_group().items():
        groups[g] = {"passed": sum(1 for c in cs if c.status == "pass"), "total": len(cs)}
    return {
        "solution": run_result.solution,
        "runner": run_result.runner,
        "started_at": run_result.started_at,
        "memory_note": run_result.memory_note,
        "summary": {
            "passed": run_result.passed,
            "failed": run_result.failed,
            "skipped": run_result.skipped,
            "total": run_result.total,
        },
        "groups": groups,
        "performance": performance(run_result),
        "cases": [c.to_dict() for c in run_result.cases],
    }


def result_to_markdown(run_result):
    r = run_result
    lines = [
        "# Test results: " + r.solution,
        "",
        "- Run at: " + r.started_at,
        "- Result: **%d/%d passed (%s)**" % (r.passed, r.total, pct(r.passed, r.total))
        + ((", %d failed" % r.failed) if r.failed else "")
        + ((", %d skipped" % r.skipped) if r.skipped else ""),
        "- Memory: " + r.memory_note,
        "",
        "## By group",
        "",
        "| Group | Passed | Total |",
        "| --- | --- | --- |",
    ]
    for g, cs in r.by_group().items():
        lines.append("| %s | %d | %d |" % (g, sum(1 for c in cs if c.status == "pass"), len(cs)))

    p = performance(r)
    if p["cases"]:
        w, c = p["wall"], p["cpu"]
        lines += [
            "",
            "## Performance",
            "",
            "- Wall time: total %s, avg %s, min %s, max %s"
            % (fmt_secs(w["total"]), fmt_secs(w["avg"]), fmt_secs(w["min"]), fmt_secs(w["max"])),
            "- CPU time: total %s, max %s" % (fmt_secs(c["total"]), fmt_secs(c["max"])),
        ]
        if p["memory_kb"]:
            m = p["memory_kb"]
            lines.append(
                "- Peak memory: max %s, avg %s" % (fmt_mem_kb(m["max"]), fmt_mem_kb(int(m["avg"])))
            )
        if p["slowest"]:
            lines.append(
                "- Slowest: "
                + ", ".join("%s (%s)" % (s["case"], fmt_secs(s["wall_time"])) for s in p["slowest"])
            )

    lines += [
        "",
        "## Cases",
        "",
        "| Case | Status | Time | Peak mem | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in r.cases:
        note = c.verdict
        if c.memcheck is not None:
            note += " / mem ok" if c.memcheck else " / mem error"
        lines.append(
            "| %s | %s | %s | %s | %s |"
            % (c.case_id, c.status, fmt_secs(c.wall_time), fmt_mem_kb(c.peak_mem_kb), note)
        )
    return "\n".join(lines) + "\n"


def result_to_text(run_result):
    r = run_result
    lines = [
        "Test results: " + r.solution,
        "  %d/%d passed (%s)" % (r.passed, r.total, pct(r.passed, r.total))
        + ((", %d failed" % r.failed) if r.failed else "")
        + ((", %d skipped" % r.skipped) if r.skipped else ""),
        "",
    ]
    marks = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "error": "ERR "}
    for c in r.cases:
        mark = marks.get(c.status, "?")
        line = "  [%s] %s  %s" % (mark, c.case_id, fmt_secs(c.wall_time))
        if c.peak_mem_kb > 0:
            line += "  " + fmt_mem_kb(c.peak_mem_kb)
        if c.verdict:
            line += "  - " + c.verdict
        lines.append(line)
    perf = perf_text_lines(r)
    if perf:
        lines.append("")
        lines += ["  " + ln for ln in perf]
    return "\n".join(lines) + "\n"


def export_result(run_result, fmt):
    if fmt == "json":
        return json.dumps(result_to_json(run_result), indent=2) + "\n"
    if fmt in ("md", "markdown"):
        return result_to_markdown(run_result)
    return result_to_text(run_result)


# ===========================================================================
# Judging (mirrors morvix/judge.py)
# ===========================================================================


def _primary_input(case):
    # The main input relpath: "stdin" if present, else the first one.
    inputs = case.get("inputs", {})
    if "stdin" in inputs:
        return inputs["stdin"]
    for value in inputs.values():
        return value
    return None


def _missing_input(manifest, case):
    # A declared primary input whose file is absent on disk - a broken package,
    # not a wrong answer. Returns the relpath when missing, else None.
    rel = _primary_input(case)
    if rel and not os.path.exists(os.path.join(manifest["_root"], rel)):
        return rel
    return None


def resolve_limits(manifest, runner, case):
    # Effective limits, applying case > runner > project precedence.
    limits = dict(manifest.get("limits", {}))
    if runner:
        for k, v in runner.get("limits", {}).items():
            if v is not None:
                limits[k] = v
    case_limits = case.get("limits", {})
    if case_limits:
        limits.update(case_limits)
    return limits


def limits_to_kwargs(limits):
    out = {
        "wall_limit": limits.get("wall"),
        "cpu_limit": limits.get("cpu"),
        "mem_limit_kb": limits.get("mem_kb"),
    }
    output_kb = limits.get("output_kb")
    out["output_cap_bytes"] = int(output_kb * 1024) if output_kb else None
    return out


def run_case_program(manifest, build, case, workdir):
    """Drive the built solution for one case (stdio / args models)."""
    root = manifest["_root"]
    locale = manifest.get("locale", "C")
    model = manifest.get("model", "stdio")
    limits = resolve_limits(manifest, manifest.get("_runner"), case)
    env = base_env(locale=locale, overrides=build.run_env)

    # This core only drives the stdio and args models. Anything else is treated
    # as stdio, but say so plainly (once) rather than failing silently.
    if model not in ("stdio", "args") and model not in _NOTED_MODELS:
        _NOTED_MODELS.add(model)
        sys.stderr.write(
            "note: model '%s' is not driven by this portable core; running it as stdio.\n" % model
        )

    argv = list(build.run_argv)
    if model == "args":
        argv = argv + list(case.get("args", []))

    stdin = b""
    primary = _primary_input(case)
    if primary:
        path = os.path.join(root, primary)
        if os.path.exists(path):
            with open(path, "rb") as f:
                stdin = f.read()

    kwargs = limits_to_kwargs(limits)
    return run(argv, stdin=stdin, cwd=workdir, env=env, locale=locale, **kwargs)


def _case_id(case):
    return case.get("group", "baseline") + "/" + case["name"]


def _has_output_expectation(manifest, case, strategy):
    if strategy == "checker":
        return True
    if case.get("expected_hash"):
        return True
    rel = case.get("expected_output")
    if not rel:
        return False
    return os.path.exists(os.path.join(manifest["_root"], rel))


def judge_case(manifest, build, case, workdir, runner, opts):
    """Run one case and combine every enabled dimension into a verdict.

    The dimensions are checked in the same order as judge.py - timeout, then
    exit/signal, then output, then optional memcheck - and ALL enabled ones
    must pass (Section 14.7).
    """
    # Setup check (mirrors judge.py): a declared input file that isn't on disk is
    # a broken package, not a wrong answer - report it distinctly so a missing
    # input is never mistaken for the solution crashing.
    missing = _missing_input(manifest, case)
    if missing:
        result = CaseResult(_case_id(case), case.get("group", "baseline"))
        result.status = "error"
        result.verdict = "input file missing: " + missing
        return result

    res = run_case_program(manifest, build, case, workdir)

    result = CaseResult(_case_id(case), case.get("group", "baseline"))
    result.exit_code = res.exit_code
    result.signal = _signal_name(res.term_signal) if res.signaled else None
    result.timed_out = res.timed_out
    result.wall_time = res.wall_time
    result.cpu_time = res.cpu_time
    result.peak_mem_kb = res.peak_mem_kb

    def fail(reason, diff=None):
        result.status = "fail"
        result.verdict = reason
        # Only attach a diff when the runner allows it and --diff is on.
        if diff and opts.diff and (runner is None or runner.get("diff", True)):
            result.diff = diff

    # --- timeout dimension ---
    if res.timed_out:
        fail("timed out")
        return result

    # --- exit / signal dimension (Section 14.6) ---
    expected_exit = case.get("expected_exit")
    expected_signal = case.get("expected_signal")
    expects_exit = expected_exit is not None or expected_signal is not None
    if expects_exit:
        ok = True
        if expected_signal:
            ok = result.signal == expected_signal
        if expected_exit is not None:
            ok = ok and res.exit_code == expected_exit
        if not ok:
            want = expected_signal or ("exit " + str(expected_exit))
            fail(_with_stderr("expected %s, got %s" % (want, res.describe_exit()), res.stderr))
            return result
        # A crash that was expected is a pass; record it plainly.
        result.verdict = "expected " + (expected_signal or ("exit " + str(expected_exit)))
    elif res.signaled or (res.exit_code is not None and res.exit_code != 0):
        # No expectation was set, so a clean exit 0 is required. A crash OR any
        # non-zero exit is a failure - even if the output happens to match. Fold in
        # the first stderr line, which is usually the actual diagnosis.
        fail(_with_stderr(res.describe_exit(), res.stderr))
        return result

    # --- output dimension ---
    params = dict(manifest.get("compare", {}))
    params["_root"] = manifest["_root"]
    # _wall rides along so the checker comparator can bound its own run.
    params["_wall"] = resolve_limits(manifest, runner, case).get("wall")
    default_strategy = params.get("strategy", "whitespace")
    strategy = case.get("compare") or (runner and runner.get("compare")) or default_strategy
    if case.get("expected_hash") and strategy != "checker":
        strategy = "hash"

    if _has_output_expectation(manifest, case, strategy):
        expected = b""
        rel = case.get("expected_output")
        if rel:
            path = os.path.join(manifest["_root"], rel)
            if os.path.exists(path):
                with open(path, "rb") as f:
                    expected = f.read()
        verdict = compare(strategy, res.stdout, expected, case, params)
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
    if _valgrind_on(runner, opts) and _wants_memcheck(manifest, build, opts):
        result.memcheck = run_memcheck(manifest, build, case, workdir, runner)
        if result.memcheck is False:
            fail("memory error")

    return result


def _valgrind_on(runner, opts):
    # Mirror judge.py: the runner profile's memcheck flag turns valgrind on.
    # --valgrind forces it on, --no-valgrind forces it off; otherwise the
    # profile decides (default off).
    if opts.valgrind is True:
        return True
    if opts.valgrind is False:
        return False
    return bool(runner and runner.get("memcheck"))


def _wants_memcheck(manifest, build, opts):
    # Only for native languages, only when valgrind is actually on PATH, and
    # only for the stdio model: the valgrind rerun feeds the primary input on
    # stdin with the bare argv, which is the stdio invocation (mirrors judge.py).
    if manifest.get("model", "stdio") != "stdio":
        return False
    if not build.artifact:
        return False
    if opts.language not in _NATIVE_LANGS:
        return False
    return find_tool("valgrind") is not None


def run_memcheck(manifest, build, case, workdir, runner):
    """Run the case under valgrind; True = clean, False = errors, None = skipped."""
    valgrind = find_tool("valgrind")
    if not valgrind or not build.artifact:
        return None
    argv = [valgrind, "--error-exitcode=99", "--leak-check=full", "-q"] + list(build.run_argv)
    stdin = b""
    primary = _primary_input(case)
    if primary:
        p = os.path.join(manifest["_root"], primary)
        if os.path.exists(p):
            with open(p, "rb") as f:
                stdin = f.read()
    limits = resolve_limits(manifest, runner, case)
    wall = (limits.get("wall") or 10) * 4
    res = run(
        argv, stdin=stdin, cwd=workdir, env=base_env(manifest.get("locale", "C")), wall_limit=wall
    )
    return res.exit_code != 99


def select_cases(manifest, runner, groups, case_ids):
    """Pick which cases to run: runner scope first, then explicit filters."""
    cases = list(manifest.get("cases", []))
    if runner and runner.get("groups"):
        wanted = set(runner["groups"])
        cases = [c for c in cases if c.get("group", "baseline") in wanted]
    if runner and runner.get("cases"):
        wanted = set(runner["cases"])
        cases = [c for c in cases if _case_id(c) in wanted]
    if groups:
        wanted = set(groups)
        cases = [c for c in cases if c.get("group", "baseline") in wanted]
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if _case_id(c) in wanted or c.get("name") in wanted]
    return cases


def judge(manifest, solution, language, cases, runner, opts):
    """Build the solution, run each selected case, return the full RunResult.

    By default it shows the live table; when opts._quiet is set it runs silently,
    which is how rivals are run before the comparison is printed.
    """
    show_live = not getattr(opts, "_quiet", False)
    printer = TablePrinter(opts, _display_config(runner, opts)) if show_live else None

    run_result = RunResult(
        solution=os.path.basename(solution), runner=(runner.get("name") if runner else None)
    )
    manifest["_runner"] = runner
    opts.language = language

    workdir = tempfile.mkdtemp(prefix="morvix-build-")
    try:
        build = build_solution(manifest, solution, language, workdir)
        if not build.ok:
            raise BuildFailure(build)
        if printer:
            printer.start(cases)
        for case in cases:
            result = judge_case(manifest, build, case, workdir, runner, opts)
            run_result.cases.append(result)
            if printer:
                printer.case_done(result)
        if printer:
            printer.finish(run_result)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return run_result


def _run_quiet(manifest, solution, language, cases, runner, opts):
    """Run a solution without printing (used for rivals)."""
    saved = getattr(opts, "_quiet", False)
    opts._quiet = True
    try:
        return judge(manifest, solution, language, cases, runner, opts)
    finally:
        opts._quiet = saved


def _build_rival_cols(manifest, rivals_meta, language, cases, runner, opts):
    """Gather rival columns: precomputed numbers, or rival code run live here."""
    root = manifest["_root"]
    cols = []
    for rv in rivals_meta:
        name = rv.get("name", "rival")
        mode = rv.get("mode")
        if mode == "precomputed":
            path = os.path.join(root, "rivals", name + ".json")
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            cols.append(
                {
                    "label": name,
                    "run": RunResult.from_json(d),
                    "precomputed": True,
                    "env": rv.get("env") or d.get("env", ""),
                }
            )
        elif mode == "code":
            src = os.path.join(root, rv.get("source", ""))
            if not os.path.exists(src):
                continue
            lang = detect_language(src) or language
            try:
                run = _run_quiet(manifest, src, lang, cases, runner, opts)
            except BuildFailure:
                continue
            cols.append({"label": name, "run": run, "precomputed": False, "env": ""})
    return cols


class BuildFailure(Exception):
    def __init__(self, build):
        self.build = build


# ===========================================================================
# Terminal table (plain text always; ANSI colour only on a tty when asked)
# ===========================================================================


def _display_config(runner, opts):
    """What to show: the runner profile decides, CLI flags override."""
    show_time = runner.get("time", True) if runner else True
    show_mem = runner.get("measure_mem", True) if runner else True
    show_perf = runner.get("report", True) if runner else True
    slowest = runner.get("slowest", 5) if runner else 5
    if getattr(opts, "time", False):  # --time forces the detail columns on
        show_time = True
        show_mem = True
    if getattr(opts, "perf", None) is not None:
        show_perf = opts.perf
    if getattr(opts, "slowest", None) is not None:
        slowest = opts.slowest
    return {"time": show_time, "mem": show_mem, "perf": show_perf, "slowest": slowest}


class TablePrinter(object):
    """Prints a live, per-case results table plus a per-group / overall summary."""

    def __init__(self, opts, display):
        self.opts = opts
        self.display = display  # {time, mem, perf, slowest}
        self.color = opts.color and sys.stdout.isatty()

    def _c(self, text, code):
        if not self.color:
            return text
        return "\033[%sm%s\033[0m" % (code, text)

    def start(self, cases):
        print("Running %d case(s)..." % len(cases))
        print("")

    def case_done(self, result):
        # A coloured badge, the case id, its time/memory, and the short verdict.
        marks = {
            "pass": ("PASS", "32"),
            "fail": ("FAIL", "31"),
            "skip": ("SKIP", "33"),
            "error": ("ERR ", "35"),
        }
        label, code = marks.get(result.status, ("?", "0"))
        line = "  [%s] %-24s" % (self._c(label, code), result.case_id)
        if self.display["time"]:
            line += " %9s cpu %8s" % (fmt_secs(result.wall_time), fmt_secs(result.cpu_time))
        if self.display["mem"]:
            line += " %9s" % fmt_mem_kb(result.peak_mem_kb)
        if result.verdict:
            line += "  - " + result.verdict
        if result.memcheck is not None:
            line += "  (mem ok)" if result.memcheck else "  (mem error)"
        print(line)
        if result.diff and self.opts.diff:
            for dl in result.diff.splitlines():
                print("        " + dl)

    def finish(self, run_result):
        print("")
        print("By group:")
        for g, cs in run_result.by_group().items():
            p = sum(1 for c in cs if c.status == "pass")
            print("  %-20s %d/%d" % (g, p, len(cs)))
        print("")
        summary = "%d/%d passed (%s)" % (
            run_result.passed,
            run_result.total,
            pct(run_result.passed, run_result.total),
        )
        if run_result.failed:
            summary += ", %d failed" % run_result.failed
        if run_result.skipped:
            summary += ", %d skipped" % run_result.skipped
        print(self._c(summary, "32" if run_result.all_passed else "31"))
        if self.display["perf"]:
            lines = perf_text_lines(
                run_result, self.display["slowest"], self.display["time"], self.display["mem"]
            )
            if lines:
                print("")
                for ln in lines:
                    print(ln)
        elif self.display["mem"]:
            print("memory: %s" % run_result.memory_note)


# ===========================================================================
# Manifest discovery + CLI
# ===========================================================================


def find_manifest(start_dir, script_dir):
    """Locate morvix.json: search the start dir and walk up, then the script dir.

    - The package root is the directory that contains morvix.json.
    - tests/ and expected/ are relative to that root.
    """
    for base in (start_dir, script_dir):
        cur = os.path.abspath(base)
        while True:
            for candidate in (
                os.path.join(cur, MANIFEST_NAME),
                os.path.join(cur, STATE_DIR, MANIFEST_NAME),
            ):
                if os.path.exists(candidate):
                    return candidate
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None


def load_manifest(path):
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    # The package root is the dir that holds .morvix/ (case paths are stored
    # relative to it). When the manifest is inside .morvix/, step up one level.
    d = os.path.dirname(os.path.abspath(path))
    if os.path.basename(d) == STATE_DIR:
        d = os.path.dirname(d)
    manifest["_root"] = d
    return manifest


def resolve_runner(manifest, name):
    runners = manifest.get("runners", {})
    if name is None:
        return None
    if name not in runners:
        known = ", ".join(sorted(runners)) or "(none defined)"
        raise RunnerError("Unknown runner '%s'. Defined runners: %s." % (name, known))
    runner = runners[name]
    runner.setdefault("name", name)
    return runner


def build_parser():
    p = argparse.ArgumentParser(
        prog="run.sh",
        description="Morvix portable runner - test a solution against this package.",
    )
    p.add_argument("solution", help="path to the solution to test")
    p.add_argument("--runner", metavar="NAME", help="use this runner profile from the manifest")
    p.add_argument(
        "--language",
        metavar="LANG",
        help="override the detected language (c, cpp, python, java, rust, nasm)",
    )
    p.add_argument(
        "--group", action="append", default=[], metavar="G", help="only run this group (repeatable)"
    )
    p.add_argument(
        "--case",
        action="append",
        default=[],
        metavar="C",
        help="only run this case id or name (repeatable)",
    )
    p.add_argument("--all", action="store_true", help="run every case (the default)")

    # On/off toggles, in the style real harnesses use.
    # valgrind defaults to None: unset lets the runner profile's memcheck decide.
    _toggle(p, "valgrind", None, "run cases under valgrind memcheck (C/C++/asm)")
    _toggle(p, "diff", True, "show a unified diff on output mismatch")
    p.add_argument("--time", action="store_true", help="show per-case CPU time and peak memory")
    _toggle(p, "perf", None, "show the performance summary at the end")
    p.add_argument(
        "--slowest",
        type=int,
        default=None,
        metavar="N",
        help="list the N slowest cases in the performance summary",
    )
    p.add_argument(
        "--no-rivals",
        action="store_true",
        help="skip the rival performance comparison shipped in this package",
    )
    p.add_argument(
        "--allow-raw",
        action="store_true",
        help="allow a package that ships raw build/run shell commands to execute them",
    )

    p.add_argument(
        "--results",
        metavar="FORMAT",
        choices=["json", "md", "text"],
        help="also write a results file in this format",
    )
    p.add_argument("--out", metavar="PATH", help="path for the --results file")

    _toggle(p, "color", True, "colourise the table (only on a tty)")
    return p


def _toggle(parser, name, default, help_text):
    # Add a paired --name / --no-name flag with a shared destination.
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--" + name, dest=name, action="store_true", default=default, help=help_text)
    group.add_argument(
        "--no-" + name, dest=name, action="store_false", help="disable: " + help_text
    )


def main(argv=None):
    args = build_parser().parse_args(argv)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    manifest_path = find_manifest(os.getcwd(), script_dir)
    if manifest_path is None:
        sys.stderr.write(
            "error: could not find %s in the current directory or above it.\n" % MANIFEST_NAME
        )
        return 2
    manifest = load_manifest(manifest_path)

    # A raw_build package executes the AUTHOR's shell commands on this machine,
    # not just your own solution. Refuse unless the receiver opts in explicitly,
    # and always show exactly what will run.
    raw_build = manifest.get("raw_build")
    raw_run = manifest.get("raw_run")
    if raw_build:
        if os.name != "posix":
            sys.stderr.write(
                "error: this package builds via the author's shell commands, which need\n"
                "       a POSIX shell; that is not supported on Windows.\n"
            )
            return 2
        if not args.allow_raw:
            sys.stderr.write(
                "error: this package builds and runs via the author's own shell commands:\n"
            )
            sys.stderr.write("         build: %s\n" % raw_build)
            if raw_run:
                sys.stderr.write("         run:   %s\n" % raw_run)
            sys.stderr.write(
                "       Only proceed if you trust the author. Re-run with --allow-raw to accept.\n"
            )
            return 2
        sys.stderr.write("note: running the author's commands (--allow-raw):\n")
        sys.stderr.write("        build: %s\n" % raw_build)
        if raw_run:
            sys.stderr.write("        run:   %s\n" % raw_run)

    solution = os.path.abspath(args.solution)
    if not os.path.exists(solution):
        sys.stderr.write("error: solution not found: %s\n" % solution)
        # A whole command ("java -cp . Main") looks like a path that doesn't exist;
        # point the receiver at what we actually want.
        if " " in args.solution.strip():
            sys.stderr.write(
                "       This looks like a command. Pass the path to a single source\n"
                "       file instead, e.g. ./run.sh WordFreq.java\n"
            )
        return 2

    # A compiled binary is never valid source. Catch it early with a clear hint
    # rather than letting the compiler choke (raw_build packages run anything).
    if not manifest.get("raw_build") and looks_like_binary(solution):
        sys.stderr.write(
            "error: %s looks like a compiled binary, not source code.\n"
            "       Pass the path to your source file instead, e.g. ./run.sh solution.c\n"
            % os.path.basename(solution)
        )
        return 2

    # Pick the language: explicit override wins, then the receiver's own file
    # extension (they may solve in a different language than the author), then
    # the manifest default. raw_build needs no language.
    detected = detect_language(solution)
    language = args.language or detected or manifest.get("language")
    if not language and not manifest.get("raw_build"):
        sys.stderr.write(
            "error: could not detect a language for %s; pass --language.\n"
            % os.path.basename(solution)
        )
        return 2
    # When the receiver's language differs from the author's, say so - it's the
    # common cross-language case and the note saves a confused debugging session.
    authored = manifest.get("language")
    if not args.language and detected and authored and detected != authored:
        sys.stderr.write(
            "note: building as %s (from %s); this package was authored in %s.\n"
            % (detected, os.path.basename(solution), authored)
        )

    try:
        runner = resolve_runner(manifest, args.runner)
    except RunnerError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    cases = select_cases(manifest, runner, args.group, args.case)
    if not cases:
        sys.stderr.write("error: no cases match the given filters.\n")
        return 2

    rivals_meta = [] if args.no_rivals else manifest.get("rivals", [])
    try:
        if rivals_meta:
            run_result = _run_quiet(manifest, solution, language, cases, runner, args)
            cols = _build_rival_cols(manifest, rivals_meta, language, cases, runner, args)
            display = _display_config(runner, args)
            print("")
            for line in comparison_block(run_result, cols, show_mem=display["mem"]):
                print(line)
            line = "%d/%d passed (%s)" % (
                run_result.passed,
                run_result.total,
                pct(run_result.passed, run_result.total),
            )
            if run_result.failed:
                line += ", %d failed" % run_result.failed
            print(line)
        else:
            run_result = judge(manifest, solution, language, cases, runner, args)
    except BuildFailure as exc:
        b = exc.build
        sys.stderr.write("Build failed (%s):\n" % b.build_command)
        sys.stderr.write(b.diagnostics)
        if not b.diagnostics.endswith("\n"):
            sys.stderr.write("\n")
        return 1
    except RunnerError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 1

    # Write a results file when asked (--results) or when the runner profile is
    # configured to produce one (Section 16.4) - so a Receiver's run can
    # automatically leave a shareable report.
    fmt = args.results or (runner.get("result_format") if runner else None)
    if fmt and fmt != "none":
        out_path = args.out or _default_results_path(fmt)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(export_result(run_result, fmt))
        print("")
        print("Wrote results to %s" % out_path)

    return 0 if run_result.all_passed else 1


def _default_results_path(fmt):
    ext = {"json": "json", "md": "md", "text": "txt"}.get(fmt, "txt")
    return "morvix-results." + ext


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
