# Rust language adapter.
#
# Compiles a single .rs file with rustc and produces a native binary.
# Cargo-project builds are a future extension; single-file rustc is supported now.
# Config keys are all optional - sensible defaults apply.

import os

from morvix import process
from morvix.adapters import Adapter, BuildResult, RunSpec, register


class RustAdapter(Adapter):
    name = "rust"

    def build(self, source: str, config: dict, workdir: str) -> BuildResult:
        rustc = config.get("rustc", "rustc")
        process.require_tool(
            rustc,
            "Install Rust via rustup for the rust adapter.",
        )

        artifact = os.path.join(workdir, "a.out")

        # Build up the compile command:
        # - rustc, optional --edition, optional -O, source, -o output
        cmd = [rustc]

        edition = config.get("edition")
        if edition:
            cmd.extend(["--edition", str(edition)])

        if config.get("release"):
            cmd.append("-O")

        cmd.extend([source, "-o", artifact])

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
        rustc = config.get("rustc", "rustc")
        parts = ["Rust", rustc]
        if "edition" in config:
            parts.append(f"--edition {config['edition']}")
        if config.get("release"):
            parts.append("-O")
        return ", ".join(parts)


register(RustAdapter())
