# Run the solution under test and report (Sections 14-17).
#
# Builds the current solution and judges it against the selected cases, showing
# a live table. Scope is --all (default) / --group / --case. Flags can override
# the comparison strategy, toggle timing/memory/valgrind, and set limits. With
# --runner NAME the named profile drives the run; otherwise a transient runner
# reflecting the flags is built on the fly. The result is stashed on the context
# and written to results/last.json so 'result' can pick it up.

import json
import os

from morvix import layout
from morvix.adapters import detect_language
from morvix.cases import list_groups
from morvix.compare import list_strategies
from morvix.components.table import RunTable
from morvix.errors import UserError
from morvix.judge import judge, select_cases
from morvix.project import DEFAULT_LIMITS, Runner
from morvix.results import export

NAME = "run"


def configure(parser):
    scope = parser.add_argument_group("scope")
    scope.add_argument("--all", action="store_true", default=True,
                       help="run every case (the default)")
    scope.add_argument("--group", action="append", metavar="G",
                       help="only this group (repeatable)")
    scope.add_argument("--case", action="append", metavar="C",
                       help="only this case (repeatable)")

    parser.add_argument("--time", action="store_true",
                        help="measure wall/cpu time")
    parser.add_argument("--mem", action="store_true",
                        help="measure peak memory")
    parser.add_argument("--valgrind", action="store_true",
                        help="check for memory errors under valgrind")
    parser.add_argument("--compare", metavar="MODE", choices=list_strategies(),
                        help="override the comparison strategy")
    parser.add_argument("--runner", metavar="NAME",
                        help="use a saved runner profile instead of the flags")

    parser.add_argument("--wall", type=float, metavar="SEC",
                        help="wall-clock time limit (seconds)")
    parser.add_argument("--cpu", type=float, metavar="SEC",
                        help="cpu time limit (seconds)")
    parser.add_argument("--memkb", type=int, metavar="KB",
                        help="address-space limit (KB)")
    parser.add_argument("--output-kb", type=int, metavar="KB",
                        help="output size limit (KB)")


def run(ctx, args) -> int:
    project = ctx.require_project()
    if not project.solution:
        raise UserError(
            "No solution is set.",
            hint="Run 'import <file>' to set the solution under test.",
        )

    # Pick the runner: a saved profile, or a transient one from the flags.
    runner = _pick_runner(project, args)

    cases = select_cases(project, runner, groups=args.group, case_ids=args.case)
    if not cases:
        raise UserError("No cases match that scope.",
                        hint="Generate cases first, or widen --group/--case.")

    language = project.language or detect_language(project.solution) or ""

    table = RunTable(ctx.console, live=ctx.interactive)
    run_result = judge(project, project.solution, language, cases,
                       runner=runner, on_case=table.update)
    table.finish(run_result)

    # Stash for the result command, both in memory and on disk.
    ctx.last_result = run_result
    _write_last(project, run_result)

    summary = f"{run_result.passed}/{run_result.total} passed"
    if run_result.all_passed:
        ctx.messenger.success(summary)
    else:
        ctx.messenger.error(f"{summary}, {run_result.failed} failed")
    return 0 if run_result.all_passed else 1


# Use a saved runner if named, else assemble a transient one from the flags.
def _pick_runner(project, args):
    if args.runner:
        runner = project.runners.get(args.runner)
        if runner is None:
            known = ", ".join(sorted(project.runners)) or "(none)"
            raise UserError(f"No runner named '{args.runner}'.",
                            hint=f"Known runners: {known}.")
        return runner

    limits = dict(DEFAULT_LIMITS)
    if args.wall is not None:
        limits["wall"] = args.wall
    if args.cpu is not None:
        limits["cpu"] = args.cpu
    if args.memkb is not None:
        limits["mem_kb"] = args.memkb
    if args.output_kb is not None:
        limits["output_kb"] = args.output_kb

    return Runner(
        name="(adhoc)",
        compare=args.compare,
        memcheck=args.valgrind,
        time=args.time,
        measure_mem=args.mem,
        limits=limits,
    )


def _write_last(project, run_result):
    results_dir = os.path.join(project.root, layout.RESULTS_DIR)
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "last.json"), "w", encoding="utf-8") as f:
        f.write(export(run_result, "json"))


def complete(ctx, prev_words, word):
    project = ctx.project
    last = prev_words[-1] if prev_words else ""
    if last == "--group" and project:
        return [(g, "group") for g in list_groups(project.cases)]
    if last == "--case" and project:
        return [(c.name, c.id) for c in project.cases]
    if last == "--compare":
        return [(s, "strategy") for s in list_strategies()]
    if last == "--runner" and project:
        return [(n, "runner") for n in sorted(project.runners)]
    return []
