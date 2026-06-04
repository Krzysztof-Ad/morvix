# NASM assembler adapter.
#
# Two-step build: assemble with nasm, then link with gcc (or ld).
# macOS (macho64 + ld for pure-syscall programs) is best-effort; the ABI
# and system call conventions differ from Linux elf64 in ways morvix does
# not abstract.

import os
import sys

from morvix.adapters import Adapter, BuildResult, RunSpec, register
from morvix import process


def _default_format():
    return "macho64" if sys.platform == "darwin" else "elf64"


class NasmAdapter(Adapter):
    name = "nasm"

    def build(self, source: str, config: dict, workdir: str) -> BuildResult:
        assembler = config.get("assembler", "nasm")
        fmt = config.get("format", _default_format())
        linker = config.get("link", "gcc")
        extra_flags = config.get("flags", [])
        link_flags = config.get("linkflags", [])

        # Locate required tools before we attempt anything.
        asm_path = process.require_tool(
            assembler,
            f"Install nasm (e.g. 'brew install nasm' or 'apt install nasm').",
        )

        # Step 1: assemble source -> object file.
        obj = os.path.join(workdir, "obj.o")
        asm_cmd = [asm_path, "-f", fmt, *extra_flags, source, "-o", obj]
        res = process.run(asm_cmd, wall_limit=180)
        if not res.ok:
            diag = (res.stdout + res.stderr).decode("utf-8", "replace")
            return BuildResult(
                ok=False,
                diagnostics=diag,
                error="assembly failed",
                build_command=" ".join(asm_cmd),
            )

        # Step 2: link object -> executable.
        out = os.path.join(workdir, "a.out")
        if linker == "ld":
            ld_path = process.require_tool(
                "ld",
                "Install ld (usually part of binutils or the system toolchain).",
            )
            link_cmd = [ld_path, obj, "-o", out, *link_flags]
        else:
            # Prefer gcc; fall back to cc.
            cc = process.find_tool("gcc") or process.find_tool("cc")
            if cc is None:
                process.require_tool(
                    "gcc",
                    "Install gcc or cc (e.g. 'apt install gcc' or Xcode command-line tools).",
                )
            link_cmd = [cc, obj, "-o", out, *link_flags]

        res2 = process.run(link_cmd, wall_limit=180)
        if not res2.ok:
            diag = (res2.stdout + res2.stderr).decode("utf-8", "replace")
            return BuildResult(
                ok=False,
                diagnostics=diag,
                error="link failed",
                build_command=" ".join(link_cmd),
            )

        return BuildResult(
            ok=True,
            artifact=out,
            run_argv=[out],
            run_env={},
            build_command=" ".join(asm_cmd) + " && " + " ".join(link_cmd),
        )

    def run_spec(self, build: BuildResult, config: dict) -> RunSpec:
        return RunSpec(argv=build.run_argv, env=build.run_env)

    def describe(self, config: dict) -> str:
        assembler = config.get("assembler", "nasm")
        fmt = config.get("format", _default_format())
        linker = config.get("link", "gcc")
        return f"NASM, {assembler}, {fmt}, link={linker}"


register(NasmAdapter())
