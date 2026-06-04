# "args" execution model (Section 10.3): the program receives its input as
# command-line arguments rather than on stdin.  The case's args list is appended
# to the runspec argv, and the primary input file (if any) is still fed on stdin
# so that programs that want both remain possible.

import os

from morvix import process
from morvix.models import ExecEnv, Observation, limits_to_kwargs, register_model, run_env
from morvix.cases import TestCase


def _args(case: TestCase, env: ExecEnv, limits: dict) -> Observation:
    argv = list(env.runspec.argv) + list(case.args)

    # Feed primary input on stdin when it exists; otherwise send nothing.
    stdin = b""
    primary = case.primary_input()
    if primary:
        path = os.path.join(env.project.root, primary)
        if os.path.exists(path):
            with open(path, "rb") as f:
                stdin = f.read()

    res = process.run(
        argv,
        stdin=stdin,
        cwd=env.workdir,
        env=run_env(env),
        locale=getattr(env.project, "locale", "C"),
        **limits_to_kwargs(limits),
    )
    return Observation(result=res, output=res.stdout)


register_model("args", _args)
