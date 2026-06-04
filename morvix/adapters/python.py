# Python language adapter.
#
# Python scripts need no compilation step, so build() is a lightweight
# syntax check via "python3 -m py_compile". If the check passes the script
# itself is the artifact and run_argv points straight at the interpreter.

from morvix import process
from morvix.adapters import Adapter, BuildResult, RunSpec, register


class PythonAdapter(Adapter):
    name = "python"

    def build(self, source: str, config: dict, workdir: str) -> BuildResult:
        interpreter = config.get("interpreter") or "python3"

        # Ensure the interpreter exists before doing anything else.
        process.require_tool(
            interpreter,
            install_hint=f"Install Python and make sure '{interpreter}' is on your PATH.",
        )

        # Run an optional syntax check; a real compile error should surface
        # here rather than at run time so the user gets a clear message.
        cmd = [interpreter, "-m", "py_compile", source]
        res = process.run(cmd, wall_limit=30)
        if not res.ok:
            diagnostics = (res.stdout + res.stderr).decode("utf-8", "replace")
            return BuildResult(
                ok=False,
                diagnostics=diagnostics,
                error="syntax error",
                build_command=" ".join(cmd),
            )

        # No binary to produce - the script is the artifact.
        return BuildResult(
            ok=True,
            artifact=source,
            run_argv=[interpreter, source],
            run_env={},
            build_command=" ".join(cmd),
        )

    def run_spec(self, build: BuildResult, config: dict) -> RunSpec:
        return RunSpec(argv=build.run_argv, env=build.run_env)

    def describe(self, config: dict) -> str:
        interpreter = config.get("interpreter") or "python3"
        return f"Python, {interpreter}"


register(PythonAdapter())
