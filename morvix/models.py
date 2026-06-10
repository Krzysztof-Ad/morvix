# Execution models: how a program is invoked and what counts as its output
# (Section 10).
#
# The model is independent of language and of comparison (Section 4.1). It takes
# a built solution plus one case, drives it the right way (stdin? argv? files?),
# and returns an Observation - the raw process result plus the bytes that should
# be judged. A comparator decides pass/fail from there.
#
# Models are registered by name. The stdio model lives here as the reference
# implementation; the others register themselves from their own modules.

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict

from morvix import process
from morvix.adapters import BuildResult, RunSpec
from morvix.cases import TestCase
from morvix.process import ProcessResult

if TYPE_CHECKING:
    from morvix.project import Project


@dataclass
class ExecEnv:
    """Everything a model needs to run a case, bundled so signatures stay short."""

    project: "Project"  # typed via TYPE_CHECKING to avoid a runtime import cycle
    build: BuildResult
    runspec: RunSpec
    workdir: str


@dataclass
class Observation:
    """What was observed from one run."""

    result: ProcessResult
    output: bytes = b""  # the bytes to judge


# A model handler: (case, env, limits) -> Observation.
ModelFn = Callable[[TestCase, ExecEnv, dict], Observation]

_REGISTRY: Dict[str, ModelFn] = {}


def register_model(name: str, fn: ModelFn) -> None:
    _REGISTRY[name] = fn


def get_model(name: str) -> ModelFn:
    _load_builtins()
    if name not in _REGISTRY:
        from morvix.errors import UserError

        known = ", ".join(sorted(_REGISTRY))
        raise UserError(f"Unknown execution model '{name}'.", hint=f"Choose one of: {known}.")
    return _REGISTRY[name]


def list_models():
    _load_builtins()
    return sorted(_REGISTRY)


def run_case(model: str, case: TestCase, env: ExecEnv, limits: dict) -> Observation:
    return get_model(model)(case, env, limits)


def limits_to_kwargs(limits: dict) -> dict:
    """Translate a limits dict into process.run keyword arguments."""
    out = {
        "wall_limit": limits.get("wall"),
        "cpu_limit": limits.get("cpu"),
        "mem_limit_kb": limits.get("mem_kb"),
    }
    output_kb = limits.get("output_kb")
    out["output_cap_bytes"] = int(output_kb * 1024) if output_kb else None
    return out


def run_env(env: ExecEnv) -> Dict[str, str]:
    """The environment for a run: deterministic locale plus the adapter's extras."""
    locale = getattr(env.project, "locale", "C")
    return process.base_env(locale=locale, overrides=env.runspec.env)


# --- the stdio model (the classic, and the default) ---


def _stdio(case: TestCase, env: ExecEnv, limits: dict) -> Observation:
    stdin = b""
    primary = case.primary_input()
    if primary:
        path = os.path.join(env.project.root, primary)
        if os.path.exists(path):
            with open(path, "rb") as f:
                stdin = f.read()
    res = process.run(
        env.runspec.argv,
        stdin=stdin,
        cwd=env.workdir,
        env=run_env(env),
        locale=getattr(env.project, "locale", "C"),
        **limits_to_kwargs(limits),
    )
    return Observation(result=res, output=res.stdout)


register_model("stdio", _stdio)


_loaded = False


def _load_builtins() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    # The remaining models self-register on import.
    from morvix.execmodels import args as _args  # noqa: F401
    from morvix.execmodels import file as _file  # noqa: F401
    from morvix.execmodels import interactive as _interactive  # noqa: F401
    from morvix.execmodels import library as _library  # noqa: F401
