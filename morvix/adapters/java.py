# Java language adapter.
#
# Compiles a .java file with javac and runs the resulting class with java.
# The main class is inferred from the source file name and an optional package
# declaration. Config keys are all optional - a plain {"language": "java"}
# config works out of the box.

import os
import re

from morvix import process
from morvix.adapters import Adapter, BuildResult, RunSpec, register

# Matches: package some.pkg.name;
_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)


def _detect_main_class(source: str) -> str:
    """Return the fully-qualified main class name.

    - The class name is always the file stem (filename without .java).
    - Read the source text to look for a package declaration; if found,
      prepend it with a dot separator.
    """
    stem = os.path.splitext(os.path.basename(source))[0]
    try:
        text = open(source, encoding="utf-8", errors="replace").read()
    except OSError:
        return stem
    m = _PACKAGE_RE.search(text)
    if m:
        return m.group(1) + "." + stem
    return stem


class JavaAdapter(Adapter):
    name = "java"

    def build(self, source: str, config: dict, workdir: str) -> BuildResult:
        javac = config.get("javac", "javac")
        java = config.get("java", "java")
        classpath = config.get("classpath", "")
        release = config.get("release")

        # Raise a clear error if the JDK is not installed.
        process.require_tool(
            javac,
            install_hint="Install a JDK (e.g. 'sudo apt install default-jdk' or "
            "'brew install openjdk') and make sure 'javac' is on your PATH.",
        )
        process.require_tool(
            java,
            install_hint="Install a JRE/JDK and make sure 'java' is on your PATH.",
        )

        # Build the javac command:
        # - "-d workdir" places .class files under workdir
        # - "--release N" pins the language level if configured
        # - "-cp classpath" adds the extra classpath for compilation
        # - "-sourcepath" lets javac pull in other .java files the source needs
        source_dir = os.path.dirname(source) or "."
        cmd = [javac, "-d", workdir]
        if release:
            cmd += ["--release", str(release)]
        if classpath:
            cmd += ["-cp", classpath]
        cmd += ["-sourcepath", source_dir, source]

        res = process.run(cmd, wall_limit=180)
        build_command = " ".join(cmd)

        if not res.ok:
            return BuildResult(
                ok=False,
                diagnostics=(res.stdout + res.stderr).decode("utf-8", "replace"),
                error="javac reported errors",
                build_command=build_command,
            )

        main_class = _detect_main_class(source)

        # Runtime classpath = workdir (where .class files live) + extra classpath.
        rt_cp = workdir + (os.pathsep + classpath if classpath else "")
        run_argv = [java, "-cp", rt_cp, main_class]

        return BuildResult(
            ok=True,
            artifact=workdir,
            run_argv=run_argv,
            run_env={},
            build_command=build_command,
        )

    def run_spec(self, build: BuildResult, config: dict) -> RunSpec:
        return RunSpec(argv=build.run_argv, env=build.run_env)

    def describe(self, config: dict) -> str:
        javac = config.get("javac", "javac")
        java = config.get("java", "java")
        parts = ["Java", javac, java]
        release = config.get("release")
        if release:
            parts.append(f"--release {release}")
        return ", ".join(parts)


register(JavaAdapter())
