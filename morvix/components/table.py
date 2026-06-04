# Live results table (Section 6.5, Section 17.2).
#
# The colored, updating table that shows a run in progress and its outcome:
# per-case status, timing, memory, verdict, with per-group and overall
# summaries. Built on rich. Every command that shows results uses this one
# table, never a bespoke variant.
#
# API (implement in Workflow B):
#   class RunTable:
#       __init__(self, console, live: bool = True)
#       update(self, case_result)   # call as each case finishes
#       finish(self, run_result)    # render the per-group + overall summary
#   render_run(console, run_result) -> None   # static full render (non-interactive / after the fact)

from rich.live import Live
from rich.table import Table

from morvix.theme import ROLE_COLORS


# Map a case status to the theme role name used for color.
_STATUS_STYLE = {
    "pass": "pass",
    "fail": "fail",
    "error": "fail",
    "skip": "skip",
}


def _make_table():
    """Build a fresh rich Table with the standard run columns."""
    # "bold" is a built-in rich style (works with and without the morvix theme).
    t = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    t.add_column("Case", style="")
    t.add_column("Status", style="")
    t.add_column("Time (s)", justify="right")
    t.add_column("Mem (KB)", justify="right")
    t.add_column("Verdict", style="")
    return t


def _add_case_row(table, case_result):
    """Append one row to the table for the given CaseResult."""
    cr = case_result
    style = _STATUS_STYLE.get(cr.status, "")
    table.add_row(
        cr.case_id,
        f"[{style}]{cr.status}[/{style}]" if style else cr.status,
        f"{cr.wall_time:.3f}",
        str(cr.peak_mem_kb),
        cr.verdict or "",
    )


def _print_summary(console, run_result):
    """Print the per-group counts and the overall pass/total line."""
    r = run_result
    console.print("")

    # Per-group breakdown
    for group, cases in r.by_group().items():
        p = sum(1 for c in cases if c.status == "pass")
        console.print(f"  [muted]{group}:[/muted] {p}/{len(cases)}")

    console.print("")

    # Overall pass line - green when all passed, red otherwise
    summary = f"{r.passed}/{r.total} passed"
    if r.failed:
        summary += f", {r.failed} failed"
    if r.skipped:
        summary += f", {r.skipped} skipped"
    overall_style = "success" if r.all_passed else "error"
    console.print(f"[{overall_style}]{summary}[/{overall_style}]")

    # Honest memory label (Section 15.1)
    console.print(f"[muted]memory: {r.memory_note}[/muted]")


class RunTable:
    def __init__(self, console, live=True):
        self._console = console
        self._table = _make_table()
        # Use Live only when requested and the console is writing to a real tty.
        use_live = live and getattr(console.file, "isatty", lambda: False)()
        if use_live:
            self._live = Live(self._table, console=console, refresh_per_second=8)
            self._live.start()
        else:
            self._live = None

    def update(self, case_result):
        """Append a row for the finished case; refreshes the live display if active."""
        _add_case_row(self._table, case_result)
        if self._live:
            self._live.refresh()

    def finish(self, run_result):
        """Stop the live display (if any) and print group counts + overall summary."""
        if self._live:
            self._live.stop()
        else:
            # Not live - print the collected table now, then the summary.
            self._console.print(self._table)
        _print_summary(self._console, run_result)


def render_run(console, run_result):
    """Build the full static table and summary from a finished RunResult."""
    table = _make_table()
    for cr in run_result.cases:
        _add_case_row(table, cr)
    console.print(table)
    _print_summary(console, run_result)
