# C++ language adapter.
#
# Compiles a single .cpp file with g++ (or a configured compiler) and produces
# a native binary. Config keys are all optional - sensible defaults apply so
# a plain {"language": "cpp"} config works out of the box.

import os

from morvix import process
from morvix.adapters import Adapter, BuildResult, RunSpec, register


class CppAdapter(Adapter):
    name = "cpp"

    def build(self, source: str, config: dict, workdir: str) -> BuildResult:
        compiler = config.get("compiler", "g++")
        process.require_tool(
            compiler,
            install_hint=f"Install g++ (e.g. 'sudo apt install g++' or 'brew install gcc') "
                         f"and make sure '{compiler}' is on your PATH.",
        )

        artifact = os.path.join(workdir, "a.out")

        # Build up the compile command:
        # - compiler, output flag, source
        # - -std= (defaults to c++20), optional -O, extra flags, -I, -L, -l entries
        cmd = [compiler, "-o", artifact, source]

        std = config.get("std", "c++20")
        cmd.append(f"-std={std}")

        opt = config.get("opt")
        if opt:
            cmd.append(f"-{opt}")

        for flag in config.get("flags", []):
            cmd.append(flag)

        for inc in config.get("include", []):
            cmd.extend(["-I", inc])

        for libdir in config.get("libdirs", []):
            cmd.extend(["-L", libdir])

        for lib in config.get("lib", []):
            cmd.append(f"-l{lib}")

        res = process.run(cmd, wall_limit=180)
        build_command = " ".join(cmd)

        if not res.ok:
            return BuildResult(
                ok=False,
                diagnostics=(res.stdout + res.stderr).decode("utf-8", "replace"),
                error="compilation failed",
                build_command=build_command,
            )

        return BuildResult(
            ok=True,
            artifact=artifact,
            run_argv=[artifact],
            run_env={},
            build_command=build_command,
        )

    def run_spec(self, build: BuildResult, config: dict) -> RunSpec:
        return RunSpec(argv=build.run_argv, env=build.run_env)

    def describe(self, config: dict) -> str:
        compiler = config.get("compiler", "g++")
        std = config.get("std", "c++20")
        parts = ["C++", compiler, f"-std={std}"]
        if "opt" in config:
            parts.append(f"-{config['opt']}")
        for flag in config.get("flags", []):
            parts.append(flag)
        return ", ".join(parts)


register(CppAdapter())
