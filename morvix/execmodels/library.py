# "library" execution model (Section 10.2): the solution under test is a
# LIBRARY, not a standalone program. Each case is a small C *harness* that
# #includes the library's headers, calls into it, and returns 0 when the
# library behaves correctly. We compile that harness, link it against the
# built library, and run it.
#
# Library cases are therefore judged mainly by exit status - the harness
# returns 0 on pass and non-zero on failure - so the gen/judge layers set
# expected_exit=0 for them. (valgrind, when asked for, is layered on top of
# this run separately by the judge; it is not our concern here.)

import os
import sys

from morvix import process
from morvix.cases import TestCase
from morvix.models import ExecEnv, Observation, limits_to_kwargs, register_model, run_env
from morvix.process import ProcessResult


# Pull the library link settings out of project.languages["library"].
# - incdir:   one path or a list of paths, each turned into -I<dir>
# - libdir:   the directory holding the built library (-L<dir> and the
#             runtime loader path), defaults to the artifact's directory
# - lib:      the library name for -l<lib>
# - compiler: the C compiler (default "cc")
# - cflags:   extra flags appended verbatim
def _settings(env: ExecEnv) -> dict:
    return env.project.languages.get("library", {})


def _incdirs(cfg: dict):
    inc = cfg.get("incdir")
    if not inc:
        return []
    return [inc] if isinstance(inc, str) else list(inc)


def _library(case: TestCase, env: ExecEnv, limits: dict) -> Observation:
    cfg = _settings(env)
    compiler = cfg.get("compiler", "cc")
    lib = cfg.get("lib")
    cflags = list(cfg.get("cflags", []))

    # Where the library lives. Fall back to the build artifact's directory so a
    # plain artifact path still works whether it points at the .so or its dir.
    libdir = cfg.get("libdir")
    if not libdir and env.build.artifact:
        artifact = env.build.artifact
        libdir = artifact if os.path.isdir(artifact) else os.path.dirname(artifact)

    # The harness source lives under the project root, like any other input.
    primary = case.primary_input()
    if not primary:
        result = ProcessResult(
            exit_code=1,
            term_signal=None,
            timed_out=False,
            wall_time=0.0,
            cpu_time=0.0,
            peak_mem_kb=0,
            stdout=b"",
            stderr=b"library case has no harness source file",
            output_truncated=False,
            mem_exceeded=False,
        )
        return Observation(result=result, output=b"")
    harness_src = os.path.join(env.project.root, primary)
    binary = os.path.join(env.workdir, "htest")

    # - compiler, harness, includes, the library search dir, -l<lib>
    # - any extra cflags, then the output binary
    cmd = [compiler, harness_src]
    for inc in _incdirs(cfg):
        cmd.append(f"-I{inc}")
    if libdir:
        cmd.append(f"-L{libdir}")
    if lib:
        cmd.append(f"-l{lib}")
    cmd += cflags + ["-o", binary]

    comp = process.run(cmd, wall_limit=180)
    if not comp.ok:
        # Compilation failed: there is nothing to run, so synthesize a failing
        # observation carrying the toolchain diagnostics for the judge to show.
        diag = comp.stdout + comp.stderr
        result = ProcessResult(
            exit_code=1,
            term_signal=None,
            timed_out=False,
            wall_time=0.0,
            cpu_time=0.0,
            peak_mem_kb=0,
            stdout=b"",
            stderr=diag,
            output_truncated=False,
            mem_exceeded=False,
        )
        return Observation(result=result, output=b"")

    # The harness links against a shared library, so the dynamic loader needs to
    # find it at runtime: DYLD_LIBRARY_PATH on macOS, LD_LIBRARY_PATH elsewhere.
    run_environment = run_env(env)
    if libdir:
        var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        existing = run_environment.get(var)
        run_environment[var] = f"{libdir}{os.pathsep}{existing}" if existing else libdir

    res = process.run(
        [binary],
        cwd=env.workdir,
        env=run_environment,
        locale=getattr(env.project, "locale", "C"),
        **limits_to_kwargs(limits),
    )
    return Observation(result=res, output=res.stdout)


register_model("library", _library)
