# Live results table (Section 6.5, Section 17.2).
#
# The colored, updating table that shows a run in progress and its outcome:
# per-case status, time, CPU, memory and verdict, then a per-group breakdown,
# the overall pass line (with a percentage), and a performance summary. Built on
# rich, and it reuses morvix.results for figures and formatting so the terminal
# view matches the exported report exactly.
#
# API:
#   class RunTable(console, live=True, show_time=True, show_mem=True,
#                  show_perf=True, slowest_n=5): update(case_result); finish(run_result)
#   render_run(console, run_result, show_time=True, show_mem=True,
#              show_perf=True, slowest_n=5)   # static full render

from rich.live import Live
from rich.table import Table

from morvix.results import fmt_mem_kb, fmt_secs, pct, perf_lines

_STATUS_STYLE = {"pass": "pass", "fail": "fail", "error": "fail", "skip": "skip"}


def _make_table(show_time, show_mem):
    t = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    t.add_column("Case")
    t.add_column("Status")
    if show_time:
        t.add_column("Time", justify="right")
        t.add_column("CPU", justify="right")
    if show_mem:
        t.add_column("Mem", justify="right")
    t.add_column("Verdict")
    return t


def _add_case_row(table, cr, show_time, show_mem):
    style = _STATUS_STYLE.get(cr.status, "")
    cells = [cr.case_id, f"[{style}]{cr.status}[/{style}]" if style else cr.status]
    if show_time:
        cells += [fmt_secs(cr.wall_time), fmt_secs(cr.cpu_time)]
    if show_mem:
        cells += [fmt_mem_kb(cr.peak_mem_kb)]
    cells += [cr.verdict or ""]
    table.add_row(*cells)


def _print_summary(console, run, show_perf, show_time, show_mem, slowest_n):
    r = run
    console.print("")
    for group, cases in r.by_group().items():
        p = sum(1 for c in cases if c.status == "pass")
        console.print(f"  [muted]{group}:[/muted] {p}/{len(cases)}")
    console.print("")

    summary = f"{r.passed}/{r.total} passed ({pct(r.passed, r.total)})"
    if r.failed:
        summary += f", {r.failed} failed"
    if r.skipped:
        summary += f", {r.skipped} skipped"
    overall_style = "success" if r.all_passed else "error"
    console.print(f"[{overall_style}]{summary}[/{overall_style}]")

    if show_perf:
        lines = perf_lines(r, slowest_n=slowest_n, show_time=show_time, show_mem=show_mem)
        if lines:
            console.print("")
            for ln in lines:
                console.print(f"[muted]{ln}[/muted]")
    elif show_mem:
        console.print(f"[muted]memory: {r.memory_note}[/muted]")


class RunTable:
    def __init__(
        self, console, live=True, show_time=True, show_mem=True, show_perf=True, slowest_n=5
    ):
        self._console = console
        self._show_time = show_time
        self._show_mem = show_mem
        self._show_perf = show_perf
        self._slowest_n = slowest_n
        self._table = _make_table(show_time, show_mem)
        use_live = live and getattr(console.file, "isatty", lambda: False)()
        if use_live:
            self._live = Live(self._table, console=console, refresh_per_second=8)
            self._live.start()
        else:
            self._live = None

    def update(self, case_result):
        _add_case_row(self._table, case_result, self._show_time, self._show_mem)
        if self._live:
            self._live.refresh()

    def finish(self, run_result):
        if self._live:
            self._live.stop()
        else:
            self._console.print(self._table)
        _print_summary(
            self._console,
            run_result,
            self._show_perf,
            self._show_time,
            self._show_mem,
            self._slowest_n,
        )


def render_run(console, run_result, show_time=True, show_mem=True, show_perf=True, slowest_n=5):
    """Build the full static table and summary from a finished RunResult."""
    table = _make_table(show_time, show_mem)
    for cr in run_result.cases:
        _add_case_row(table, cr, show_time, show_mem)
    console.print(table)
    _print_summary(console, run_result, show_perf, show_time, show_mem, slowest_n)
