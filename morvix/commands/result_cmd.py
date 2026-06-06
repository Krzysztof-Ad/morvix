# Export the last run as a report, or diff two results files (Section 17).
#
# Formats:
#   --json   machine-readable (default for piping / cross-solution diff)
#   --md     Markdown report (default)
#   --text   plain text for minimal environments
#
# "result diff other.json" compares per-case status/output between the last
# run and another saved results/last.json, showing where the two solutions
# disagree (the cross-solution agreement signal, Sections 13.5/20.2).

import json
import os

from morvix import layout
from morvix.errors import UserError
from morvix.results import export

NAME = "result"


def configure(parser):
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument(
        "--json",
        dest="fmt",
        action="store_const",
        const="json",
        help="output as JSON (machine-readable)",
    )
    fmt.add_argument(
        "--md", dest="fmt", action="store_const", const="md", help="output as Markdown (default)"
    )
    fmt.add_argument(
        "--text", dest="fmt", action="store_const", const="text", help="output as plain text"
    )
    parser.set_defaults(fmt="md")

    parser.add_argument("--out", metavar="PATH", help="write output to this file instead of stdout")

    # Catch "result diff <other.json>" or bare invocation.
    # nargs="*" so "result" with no positionals is valid too.
    parser.add_argument(
        "args",
        nargs="*",
        metavar="[diff OTHER]",
        help="optional: diff <path-to-other-results.json>",
    )


def run(ctx, args) -> int:
    ctx.require_project()
    project = ctx.project

    positional = args.args or []

    # - diff mode: compare last run vs another results file
    if positional and positional[0] == "diff":
        return _run_diff(ctx, project, positional)

    # - normal mode: render last run
    return _run_export(ctx, project, args)


# --- diff ---


def _run_diff(ctx, project, positional):
    if len(positional) < 2:
        raise UserError(
            "Usage: result diff <other-results.json>",
            hint="Point at a results/last.json from another run.",
        )

    other_path = positional[1]
    if not os.path.isabs(other_path):
        other_path = os.path.join(project.root, other_path)

    if not os.path.exists(other_path):
        raise UserError(f"File not found: {other_path}")

    mine_data = _load_last_dict(ctx, project)
    with open(other_path, encoding="utf-8") as f:
        other_data = json.load(f)

    mine_by_case = {c["case"]: c for c in mine_data.get("cases", [])}
    other_by_case = {c["case"]: c for c in other_data.get("cases", [])}

    all_ids = sorted(set(mine_by_case) | set(other_by_case))
    if not all_ids:
        ctx.messenger.info("No cases in either result.")
        return 0

    # Build a diff table: only rows where something differs.
    from rich.table import Table

    agree, differ = [], []
    for cid in all_ids:
        m = mine_by_case.get(cid)
        o = other_by_case.get(cid)
        m_status = m["status"] if m else "missing"
        o_status = o["status"] if o else "missing"
        if m_status == o_status:
            agree.append(cid)
        else:
            differ.append((cid, m_status, o_status))

    mine_label = mine_data.get("solution", "mine")
    other_label = other_data.get("solution", other_path)

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("Case")
    table.add_column(f"This  ({mine_label})", justify="center")
    table.add_column(f"Other ({other_label})", justify="center")
    table.add_column("Agree?", justify="center")

    def _status_style(s):
        return {"pass": "pass", "fail": "fail", "error": "fail", "skip": "skip"}.get(s, "")

    for cid, ms, os_ in differ:
        ms_style = _status_style(ms)
        os_style = _status_style(os_)
        table.add_row(
            cid,
            f"[{ms_style}]{ms}[/{ms_style}]" if ms_style else ms,
            f"[{os_style}]{os_}[/{os_style}]" if os_style else os_,
            "[fail]no[/fail]",
        )

    ctx.messenger.heading("Cross-solution diff")
    if differ:
        ctx.console.print(table)
        ctx.messenger.warning(f"{len(differ)} case(s) differ, {len(agree)} agree.")
    else:
        ctx.messenger.success(f"All {len(agree)} case(s) agree between the two runs.")

    return 0


# --- normal export ---


def _run_export(ctx, project, args):
    fmt = args.fmt

    # Prefer in-session RunResult; fall back to reading results/last.json.
    if ctx.last_result is not None:
        rendered = export(ctx.last_result, fmt)
    else:
        last_path = os.path.join(project.root, layout.RESULTS_DIR, "last.json")
        if not os.path.exists(last_path):
            raise UserError(
                "No results yet.",
                hint="Run 'run' to test the solution first.",
            )
        with open(last_path, encoding="utf-8") as f:
            data = json.load(f)

        if fmt == "json":
            import json as _json

            rendered = _json.dumps(data, indent=2) + "\n"
        else:
            # Reconstruct a minimal RunResult from the stored dict so we can
            # reuse the standard formatters without duplicating logic.
            rendered = _format_dict(data, fmt)

    if args.out:
        out_path = args.out if os.path.isabs(args.out) else os.path.join(project.root, args.out)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rendered)
        ctx.messenger.success(f"Report written to {out_path}")
    else:
        ctx.messenger.plain(rendered)

    return 0


# --- helpers ---


def _load_last_dict(ctx, project) -> dict:
    """Return last run data as a dict (from memory or disk)."""
    if ctx.last_result is not None:
        import json as _json

        raw = export(ctx.last_result, "json")
        return _json.loads(raw)
    last_path = os.path.join(project.root, layout.RESULTS_DIR, "last.json")
    if not os.path.exists(last_path):
        raise UserError(
            "No results yet.",
            hint="Run 'run' to test the solution first.",
        )
    with open(last_path, encoding="utf-8") as f:
        return json.load(f)


def _format_dict(data: dict, fmt: str) -> str:
    """Reconstruct a RunResult from the stored JSON dict and format it."""
    from morvix.results import CaseResult, RunResult

    run = RunResult(
        solution=data.get("solution", "?"),
        runner=data.get("runner"),
        started_at=data.get("started_at", ""),
        memory_note=data.get("memory_note", "peak, approximate"),
    )
    for c in data.get("cases", []):
        run.cases.append(
            CaseResult(
                case_id=c.get("case", "?"),
                group=c.get("group", ""),
                status=c.get("status", "?"),
                verdict=c.get("verdict", ""),
                exit_code=c.get("exit_code"),
                signal=c.get("signal"),
                timed_out=c.get("timed_out", False),
                wall_time=c.get("wall_time", 0.0),
                cpu_time=c.get("cpu_time", 0.0),
                peak_mem_kb=c.get("peak_mem_kb", 0),
                memcheck=c.get("memcheck"),
            )
        )
    return export(run, fmt)


# --- completion ---


def complete(ctx, prev_words, word):
    # "result diff <path>" - offer json files
    last = prev_words[-1] if prev_words else ""
    if last == "diff" or (len(prev_words) >= 2 and prev_words[-2] == "diff"):
        import glob

        matches = glob.glob(word + "*.json") if word else glob.glob("*.json")
        return [(m, "json file") for m in matches]
    if last == "--out":
        import glob

        matches = glob.glob(word + "*") if word else []
        return [(m, "path") for m in matches]
    # offer "diff" as the first positional
    if not prev_words or prev_words[-1].startswith("-"):
        return [("diff", "compare with another results file")]
    return []
