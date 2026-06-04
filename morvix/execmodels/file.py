# "file" execution model (Section 10.4): the program reads and writes named
# files rather than using stdin/stdout.  This targets the common single-output-
# file assignment where students are told "read from input.txt, write to
# output.txt" (or similarly named files).

import os
import shutil

from morvix import process
from morvix.cases import TestCase
from morvix.models import ExecEnv, Observation, limits_to_kwargs, register_model, run_env


def _file(case: TestCase, env: ExecEnv, limits: dict) -> Observation:
    # Copy each input file into workdir under the logical name the program expects.
    for logical_name, relpath in case.inputs.items():
        src = os.path.join(env.project.root, relpath)
        dst = os.path.join(env.workdir, logical_name)
        if os.path.exists(src):
            shutil.copy2(src, dst)

    res = process.run(
        env.runspec.argv,
        stdin=None,
        cwd=env.workdir,
        env=run_env(env),
        locale=getattr(env.project, "locale", "C"),
        **limits_to_kwargs(limits),
    )

    # Determine the primary output filename:
    # - use the first key of expected_files when the case declares them
    # - fall back to "output.txt" for the typical single-output assignment
    if case.expected_files:
        primary_out = next(iter(case.expected_files))
    else:
        primary_out = "output.txt"

    # Read the primary output; empty bytes if the file was not produced.
    primary_path = os.path.join(env.workdir, primary_out)
    if os.path.exists(primary_path):
        with open(primary_path, "rb") as f:
            output = f.read()
    else:
        output = b""

    # Collect every file named in expected_files so comparators can check each one.
    produced: dict = {}
    for filename in case.expected_files:
        path = os.path.join(env.workdir, filename)
        if os.path.exists(path):
            with open(path, "rb") as f:
                produced[filename] = f.read()
        else:
            produced[filename] = b""

    return Observation(result=res, output=output, produced_files=produced)


register_model("file", _file)
