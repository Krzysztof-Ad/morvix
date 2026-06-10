# "file" execution model (Section 10.4): the program reads and writes named
# files rather than using stdin/stdout.  This targets the common single-output-
# file assignment where students are told "read from input.txt, write to
# output.txt": inputs are copied in under their logical names, and the judged
# output is whatever the program wrote to output.txt.

import os
import shutil

from morvix import process
from morvix.cases import TestCase
from morvix.models import ExecEnv, Observation, limits_to_kwargs, register_model, run_env

# The conventional output filename for file-model assignments.
OUTPUT_NAME = "output.txt"


def _remove(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _file(case: TestCase, env: ExecEnv, limits: dict) -> Observation:
    # The workdir is shared by every case in a run (the built solution lives
    # there), so clear the previous case's output before running: a program
    # that writes nothing must be judged on no output, not on stale bytes.
    _remove(os.path.join(env.workdir, OUTPUT_NAME))

    # Copy each input file into workdir under the logical name the program
    # expects. A declared input missing on disk also clears any same-named
    # leftover from an earlier case rather than silently reusing it.
    for logical_name, relpath in case.inputs.items():
        src = os.path.join(env.project.root, relpath)
        dst = os.path.join(env.workdir, logical_name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
        else:
            _remove(dst)

    res = process.run(
        env.runspec.argv,
        stdin=None,
        cwd=env.workdir,
        env=run_env(env),
        locale=getattr(env.project, "locale", "C"),
        **limits_to_kwargs(limits),
    )

    # Read the produced output (the conventional "output.txt"); empty bytes if
    # the program did not write it.
    primary_path = os.path.join(env.workdir, OUTPUT_NAME)
    if os.path.exists(primary_path):
        with open(primary_path, "rb") as f:
            output = f.read()
    else:
        output = b""

    return Observation(result=res, output=output)


register_model("file", _file)
