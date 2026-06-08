# Run the solution under test and report (Sections 14-17).
#
# Builds the current solution and judges it against the selected cases, showing
# a live table. Scope is --all (default) / --group / --case. Flags can override
# the comparison strategy, toggle timing/memory/valgrind, and set limits. With
# --runner NAME the named profile drives the run; otherwise a transient runner
# reflecting the flags is built on the fly. The result is stashed on the context
# and written to results/last.json so 'result' can pick it up.

import os

from morvix import comparison, layout
from morvix.adapters import detect_language
from morvix.cases import list_groups
from morvix.compare import list_strategies
from morvix.components.table import RunTable
from morvix.errors import UserError
from morvix.judge import judge, select_cases
from morvix.project import DEFAULT_LIMITS, Runner
from morvix.results import comparison_block, export

NAME = "run"


def configure(parser):
    scope = parser.add_argument_group("scope")
    scope.add_argument(
        "--all", action="store_true", default=True, help="run every case (the default)"
    )
    scope.add_argument("--group", action="append", metavar="G", help="only this group (repeatable)")
    scope.add_argument("--case", action="append", metavar="C", help="only this case (repeatable)")

    parser.add_argument(
        "--time", action="store_true", help="show wall/cpu time per case (on by default for run)"
    )
    parser.add_argument(
        "--mem", action="store_true", help="show peak memory per case (on by default for run)"
    )
    parser.add_argument(
        "--no-perf", action="store_true", help="hide the performance summary at the end"
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="show a unified diff under each case whose output differs",
    )
    parser.add_argument(
        "--slowest",
        type=int,
        default=5,
        metavar="N",
        help="list the N slowest cases in the performance summary (default 5)",
    )
    parser.add_argument(
        "--no-rivals", action="store_true", help="skip the rival performance comparison"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="run rivals in parallel (faster, but perf numbers become approximate)",
    )
    parser.add_argument(
        "--valgrind", action="store_true", help="check for memory errors under valgrind"
    )
    parser.add_argument(
        "--compare",
        metavar="MODE",
        choices=list_strategies(),
        help="override the comparison strategy",
    )
    parser.add_argument(
        "--runner", metavar="NAME", help="use a saved runner profile instead of the flags"
    )

    parser.add_argument("--wall", type=float, metavar="SEC", help="wall-clock time limit (seconds)")
    parser.add_argument("--cpu", type=float, metavar="SEC", help="cpu time limit (seconds)")
    parser.add_argument("--memkb", type=int, metavar="KB", help="address-space limit (KB)")
    parser.add_argument("--output-kb", type=int, metavar="KB", help="output size limit (KB)")


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
        raise UserError(
            "No cases match that scope.", hint="Generate cases first, or widen --group/--case."
        )

    language = project.language or detect_language(project.solution) or ""

    # If rivals are registered (and not skipped), run the performance comparison.
    rivals = [] if args.no_rivals else comparison.selected_rivals(project, runner)
    if rivals:
        return _run_with_comparison(
            ctx, project, runner, project.solution, language, cases, rivals, args
        )

    table = RunTable(
        ctx.console,
        live=ctx.interactive,
        show_time=runner.time,
        show_mem=runner.measure_mem,
        show_perf=runner.report,
        slowest_n=runner.slowest,
        show_diff=args.diff,
    )
    run_result = judge(
        project, project.solution, language, cases, runner=runner, on_case=table.update
    )
    table.finish(run_result)

    # Stash for the result command, both in memory and on disk.
    ctx.last_result = run_result
    _write_last(project, run_result)

    # A named runner can auto-emit the report it was configured to produce.
    if args.runner:
        _emit_configured_report(ctx, project, runner, run_result)

    return _summarize(ctx, run_result)


def _run_with_comparison(ctx, project, runner, solution, language, cases, rivals, args):
    """Run the solution + rivals and print the comparison (no live table)."""
    main, cols = comparison.compare_live(
        project, solution, language, cases, rivals, runner=runner, parallel=args.parallel
    )
    ctx.console.print("")
    for line in comparison_block(
        main, cols, show_mem=runner.measure_mem, per_case=(runner.verbosity != "quiet")
    ):
        ctx.console.print(f"[muted]{line}[/muted]")

    ctx.last_result = main
    _write_last(project, main)
    if args.runner:
        _emit_configured_report(ctx, project, runner, main)

    rc = _summarize(ctx, main)
    if args.parallel:
        ctx.messenger.warning("Rivals ran in parallel - time/memory figures are approximate.")
    return rc


# Print the pass/fail line for a finished run and return the process exit code.
def _summarize(ctx, result) -> int:
    summary = f"{result.passed}/{result.total} passed"
    if result.all_passed:
        ctx.messenger.success(summary)
    else:
        ctx.messenger.error(f"{summary}, {result.failed} failed")
    return 0 if result.all_passed else 1


# Use a saved runner if named, else assemble a transient one from the flags.
def _pick_runner(project, args):
    if args.runner:
        runner = project.runners.get(args.runner)
        if runner is None:
            known = ", ".join(sorted(project.runners)) or "(none)"
            raise UserError(f"No runner named '{args.runner}'.", hint=f"Known runners: {known}.")
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

    # The interactive run is the dev view: always show time/memory and the perf
    # summary (a named runner is what tailors what a Receiver sees).
    return Runner(
        name="(adhoc)",
        compare=args.compare,
        memcheck=args.valgrind,
        time=True,
        measure_mem=True,
        report=not args.no_perf,
        slowest=args.slowest,
        limits=limits,
    )


_EXT = {"md": "md", "markdown": "md", "json": "json", "text": "txt"}


def _emit_configured_report(ctx, project, runner, run_result):
    """Write the report a named runner is configured to produce (Section 16.4)."""
    fmt = runner.result_format
    if not fmt or fmt == "none":
        return
    rel = runner.result_path or os.path.join(
        layout.RESULTS_DIR, f"{runner.name}.{_EXT.get(fmt, 'txt')}"
    )
    path = rel if os.path.isabs(rel) else project.abspath(rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(export(run_result, fmt))
    ctx.messenger.info(f"Wrote report to {rel}")


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
