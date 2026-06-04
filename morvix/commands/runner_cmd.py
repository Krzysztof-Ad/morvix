# runner command - create, edit, inspect, list and build runner profiles (Section 16).
#
# A runner is a named, shareable execution profile: which backend runs the
# tests, which comparison to use, the limits and the toggles (timing, memory,
# diff, ...). 'runner new'/'edit' open a guided form; 'runner build' writes the
# portable runner/ (run.sh + the stdlib Python core) so the profile can ship.

from morvix.compare import list_strategies
from morvix.components.choice import choose
from morvix.components.form import run_form, Field
from morvix.components.selection import select
from morvix.errors import UserError
from morvix.project import Runner, DEFAULT_LIMITS
from morvix import runner_build, suggestions
from morvix.cases import list_groups

NAME = "runner"

ACTIONS = ["new", "edit", "show", "list", "build"]

_BACKENDS = ["bash", "python", "valgrind"]
_VERBOSITIES = ["quiet", "normal", "verbose"]
_RESULT_FORMATS = ["md", "json", "text", "none"]

# Sentinel value the compare choice maps to "use the project default".
_PROJECT_DEFAULT = "__project_default__"


def configure(parser):
    parser.add_argument(
        "action",
        nargs="?",
        choices=ACTIONS,
        default="list",
        help="new | edit | show | list | build (default: list)",
    )
    parser.add_argument("name", nargs="?", help="runner profile name")


def run(ctx, args) -> int:
    project = ctx.require_project()
    action = getattr(args, "action", None) or "list"
    name = getattr(args, "name", None)

    if action == "list":
        return _list(ctx, project)
    if action == "show":
        return _show(ctx, project, name)
    if action == "build":
        return _build(ctx, project, name)
    if action in ("new", "edit"):
        return _new_or_edit(ctx, project, name, action)
    raise UserError(f"Unknown runner action '{action}'.", hint="Use one of: " + ", ".join(ACTIONS))


# --- list ---

def _list(ctx, project) -> int:
    if not project.runners:
        ctx.messenger.info("No runner profiles yet.")
        ctx.messenger.plain("Create one with:  runner new <name>")
        return 0
    ctx.messenger.heading("Runner profiles")
    for rname in sorted(project.runners):
        ctx.messenger.plain(f"  {rname}  -  {_summary(project, project.runners[rname])}")
    return 0


# One-line summary: backend, comparison and the enabled toggles.
def _summary(project, runner) -> str:
    compare = runner.compare or f"{project.compare.get('strategy', 'whitespace')} (project default)"
    toggles = [name for name, on in (
        ("time", runner.time),
        ("mem", runner.measure_mem),
        ("hard-kill", runner.hard_kill),
        ("memcheck", runner.memcheck),
        ("diff", runner.diff),
    ) if on]
    toggle_str = ", ".join(toggles) if toggles else "no toggles"
    return f"backend={runner.backend}, compare={compare}, {toggle_str}"


# --- show ---

def _show(ctx, project, name) -> int:
    runner = _require_runner(project, name, "show")
    ctx.messenger.heading(f"Runner '{runner.name}'")
    groups = ", ".join(runner.groups) if runner.groups else "all groups"
    cases = ", ".join(runner.cases) if runner.cases else "all cases"
    rows = [
        ("backend", runner.backend),
        ("compare", runner.compare or f"(project default: {project.compare.get('strategy', 'whitespace')})"),
        ("groups", groups),
        ("cases", cases),
        ("time", runner.time),
        ("measure_mem", runner.measure_mem),
        ("hard_kill", runner.hard_kill),
        ("memcheck", runner.memcheck),
        ("diff", runner.diff),
        ("color", runner.color),
        ("verbosity", runner.verbosity),
        ("result_format", runner.result_format),
        ("result_path", runner.result_path or "(default)"),
        ("wall limit", _fmt_limit(runner.limits.get("wall"))),
        ("cpu limit", _fmt_limit(runner.limits.get("cpu"))),
        ("mem_kb limit", _fmt_limit(runner.limits.get("mem_kb"))),
    ]
    width = max(len(k) for k, _ in rows)
    for key, value in rows:
        ctx.messenger.plain(f"  {key.ljust(width)}  {value}")
    return 0


def _fmt_limit(value):
    return "(unset)" if value is None else value


# --- new / edit ---

def _new_or_edit(ctx, project, name, action) -> int:
    if not name:
        raise UserError(
            f"runner {action} needs a name.",
            hint=f"Try:  runner {action} <name>",
        )
    if action == "edit" and name not in project.runners:
        raise UserError(
            f"No runner profile named '{name}'.",
            hint="List existing profiles with:  runner list",
        )

    existing = project.runners.get(name)

    # Non-interactive with nothing to drive a form: lay down a sensible default.
    if not ctx.interactive:
        runner = existing or _default_runner(name)
        project.runners[name] = runner
        ctx.save_project()
        suggestions.warn_backend_metrics(ctx, runner)
        verb = "Updated" if action == "edit" else "Created"
        ctx.messenger.success(f"{verb} runner '{name}'.")
        ctx.messenger.info(_summary(project, runner))
        return 0

    runner = _form_runner(ctx, project, name, existing)
    if runner is None:
        ctx.messenger.info("Cancelled.")
        return 0

    # Pick the groups this runner covers ([] means all groups).
    groups = list_groups(project.cases)
    if groups:
        items = [(g, g, g) for g in groups]
        preselected = set(runner.groups) if runner.groups else set(groups)
        chosen = select(ctx, "Groups this runner covers", items, preselected=preselected)
        runner.groups = [] if set(chosen) == set(groups) else list(chosen)

    project.runners[name] = runner
    ctx.save_project()
    suggestions.warn_backend_metrics(ctx, runner)
    verb = "Updated" if action == "edit" else "Created"
    ctx.messenger.success(f"{verb} runner '{name}'.")
    ctx.messenger.info(_summary(project, runner))
    return 0


# Build the guided form, prefilled from an existing runner when editing.
def _form_runner(ctx, project, name, existing):
    base = existing or _default_runner(name)

    compare_choices = [(_PROJECT_DEFAULT, "(project default)")]
    compare_choices += [(s, s) for s in list_strategies()]
    compare_default = base.compare if base.compare is not None else _PROJECT_DEFAULT

    fields = [
        Field("backend", "Backend", "choice",
              choices=[(b, b) for b in _BACKENDS], default=base.backend,
              help="how tests run: bash (coarse), python (precise), valgrind (+memcheck)"),
        Field("compare", "Comparison", "choice",
              choices=compare_choices, default=compare_default,
              help="output comparison strategy, or the project default"),
        Field("time", "Measure time", "bool", default=base.time, help="record per-run wall time"),
        Field("measure_mem", "Measure memory", "bool", default=base.measure_mem,
              help="record approximate peak memory"),
        Field("hard_kill", "Hard kill on limit", "bool", default=base.hard_kill,
              help="enforce limits with hard rlimit caps"),
        Field("memcheck", "Memory check", "bool", default=base.memcheck,
              help="run Valgrind memory-correctness check (valgrind backend)"),
        Field("diff", "Show diff", "bool", default=base.diff, help="show output diffs on failure"),
        Field("verbosity", "Verbosity", "choice",
              choices=[(v, v) for v in _VERBOSITIES], default=base.verbosity),
        Field("result_format", "Result format", "choice",
              choices=[(f, f) for f in _RESULT_FORMATS], default=base.result_format),
        Field("wall", "Wall limit (s, blank = unset)", "float",
              default=base.limits.get("wall"), help="seconds; blank leaves it unset"),
        Field("cpu", "CPU limit (s, blank = unset)", "float",
              default=base.limits.get("cpu"), help="seconds; blank leaves it unset"),
    ]

    result = run_form(ctx, f"Runner '{name}'", fields)
    if result is None:
        return None

    runner = existing or Runner(name=name)
    runner.name = name
    runner.backend = result["backend"]
    runner.compare = None if result["compare"] == _PROJECT_DEFAULT else result["compare"]
    runner.time = bool(result["time"])
    runner.measure_mem = bool(result["measure_mem"])
    runner.hard_kill = bool(result["hard_kill"])
    runner.memcheck = bool(result["memcheck"])
    runner.diff = bool(result["diff"])
    runner.verbosity = result["verbosity"]
    runner.result_format = result["result_format"]

    limits = dict(runner.limits) if runner.limits else dict(DEFAULT_LIMITS)
    limits["wall"] = result.get("wall")
    limits["cpu"] = result.get("cpu")
    runner.limits = limits
    return runner


# A reasonable starting profile: python backend, project-default comparison.
def _default_runner(name) -> Runner:
    return Runner(name=name, backend="python", compare=None, limits=dict(DEFAULT_LIMITS))


# --- build ---

def _build(ctx, project, name) -> int:
    runner = _require_runner(project, name, "build")
    runner_dir = runner_build.build_runner(project, runner)
    ctx.messenger.success(f"Built runner for '{runner.name}'.")
    ctx.messenger.info(f"Wrote runner/ at {runner_dir}")

    caps = runner_build.runner_capabilities(runner.backend)
    ctx.messenger.heading(f"Backend '{runner.backend}' measures:")
    for key in ("timing", "peak_memory", "hard_caps", "memcheck"):
        mark = "yes" if caps.get(key) else "no"
        ctx.messenger.plain(f"  {key.ljust(11)}  {mark}")
    ctx.messenger.plain(f"  {caps.get('note', '')}")
    return 0


# --- helpers ---

def _require_runner(project, name, action) -> Runner:
    if not name:
        raise UserError(
            f"runner {action} needs a name.",
            hint="List existing profiles with:  runner list",
        )
    runner = project.runners.get(name)
    if runner is None:
        raise UserError(
            f"No runner profile named '{name}'.",
            hint="List existing profiles with:  runner list",
        )
    return runner


def complete(ctx, prev_words, word):
    # - first word: the action; afterwards: existing runner names
    names = sorted(ctx.project.runners) if ctx.project else []
    relevant = [w for w in prev_words if w not in ("runner",)]
    if not relevant:
        out = [(a, "action") for a in ACTIONS]
        out += [(n, "runner") for n in names]
        return out
    return [(n, "runner") for n in names]
