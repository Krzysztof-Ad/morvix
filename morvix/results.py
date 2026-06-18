# Results and reporting (Section 17).
#
# After a run we have, per case, a verdict and some numbers (wall/CPU time, peak
# memory). This module is the data model for that (CaseResult, RunResult), the
# performance aggregation built on top of it, and the three export formats: JSON
# (machine-readable), Markdown (the human report), and plain text.
#
# performance() and the formatters here are the SINGLE SOURCE for perf figures
# on the in-tool side; the shipped runner core mirrors this logic in stdlib so a
# Receiver sees the same report.

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class CaseResult:
    case_id: str
    group: str
    status: str  # "pass" | "fail" | "skip" | "error"
    verdict: str = ""  # short human reason
    exit_code: Optional[int] = None
    signal: Optional[str] = None
    timed_out: bool = False
    wall_time: float = 0.0
    cpu_time: float = 0.0
    peak_mem_kb: int = 0
    diff: Optional[str] = None  # unified diff when available
    memcheck: Optional[bool] = None  # valgrind verdict; None if not run

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict:
        d = {
            "case": self.case_id,
            "group": self.group,
            "status": self.status,
            "verdict": self.verdict,
            "wall_time": round(self.wall_time, 6),
            "cpu_time": round(self.cpu_time, 6),
            "peak_mem_kb": self.peak_mem_kb,
        }
        if self.exit_code is not None:
            d["exit_code"] = self.exit_code
        if self.signal is not None:
            d["signal"] = self.signal
        if self.timed_out:
            d["timed_out"] = True
        if self.memcheck is not None:
            d["memcheck"] = self.memcheck
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CaseResult":
        return cls(
            case_id=d.get("case", ""),
            group=d.get("group", ""),
            status=d.get("status", "pass"),
            verdict=d.get("verdict", ""),
            exit_code=d.get("exit_code"),
            signal=d.get("signal"),
            timed_out=d.get("timed_out", False),
            wall_time=d.get("wall_time", 0.0),
            cpu_time=d.get("cpu_time", 0.0),
            peak_mem_kb=d.get("peak_mem_kb", 0),
            memcheck=d.get("memcheck"),
        )


@dataclass
class RunResult:
    solution: str
    runner: Optional[str] = None
    cases: List[CaseResult] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    memory_note: str = "peak, approximate"  # honest label (Section 15.1)

    # --- summaries ---

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.cases if c.status in ("fail", "error"))

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.cases if c.status == "skip")

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.total > 0

    def failure_breakdown(self) -> List[tuple]:
        """Count failures by kind, so a big run says *how* it failed at a glance:
        wrong output vs a crash vs a timeout vs a wrong exit code. Returns
        (label, count) pairs in a fixed order, dropping the empty ones."""
        order = ["wrong output", "wrong exit", "crashed", "timed out", "error"]
        counts = {k: 0 for k in order}
        for c in self.cases:
            if c.status not in ("fail", "error"):
                continue
            if c.timed_out:
                counts["timed out"] += 1
            elif c.signal:
                counts["crashed"] += 1
            elif c.status == "error":
                counts["error"] += 1
            elif c.exit_code not in (0, None):
                counts["wrong exit"] += 1
            else:
                counts["wrong output"] += 1
        return [(k, counts[k]) for k in order if counts[k]]

    def by_group(self) -> Dict[str, List[CaseResult]]:
        groups: Dict[str, List[CaseResult]] = {}
        for c in self.cases:
            groups.setdefault(c.group, []).append(c)
        return groups

    @classmethod
    def from_json(cls, d: dict) -> "RunResult":
        """Reconstruct a run from its exported JSON (for precomputed rivals)."""
        r = cls(
            solution=d.get("solution", ""),
            runner=d.get("runner"),
            started_at=d.get("started_at", ""),
            memory_note=d.get("memory_note", "peak, approximate"),
        )
        r.cases = [CaseResult.from_dict(c) for c in d.get("cases", [])]
        return r


# --- formatting (shared by every renderer) ---


def fmt_secs(seconds: float) -> str:
    return "%.3fs" % seconds


def fmt_mem_kb(kb: int) -> str:
    if kb <= 0:
        return "n/a"
    if kb < 1024:
        return "%d KB" % kb
    return "%.1f MB" % (kb / 1024.0)


def pct(passed: int, total: int) -> str:
    return "%.0f%%" % (100.0 * passed / total) if total else "0%"


def failure_line(run: "RunResult") -> str:
    """One-line rollup of how the failing cases failed, or "" if all passed."""
    bd = run.failure_breakdown()
    if not bd:
        return ""
    return "Failures: " + ", ".join("%s %d" % (label, n) for label, n in bd)


# --- performance aggregation (the single source for perf figures) ---


def _stats(values):
    if not values:
        return {"total": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "total": sum(values),
        "avg": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


def performance(run: RunResult, slowest_n: int = 5) -> dict:
    """Aggregate timing/memory across the run (skips skipped cases)."""
    cases = [c for c in run.cases if c.status != "skip"]
    walls = [c.wall_time for c in cases]
    cpus = [c.cpu_time for c in cases]
    mems = [c.peak_mem_kb for c in cases]
    have_mem = any(m > 0 for m in mems)
    slowest = sorted(
        (c for c in cases if c.wall_time > 0), key=lambda c: c.wall_time, reverse=True
    )[:slowest_n]
    return {
        "cases": len(cases),
        "wall": _stats(walls),
        "cpu": _stats(cpus),
        "memory_kb": ({"max": max(mems), "avg": sum(mems) / len(mems)} if have_mem else None),
        "slowest": [{"case": c.case_id, "wall_time": round(c.wall_time, 6)} for c in slowest],
    }


def perf_lines(
    run: RunResult, slowest_n: int = 5, show_time: bool = True, show_mem: bool = True
) -> List[str]:
    """Plain-text performance block, reused by the terminal table and exports."""
    p = performance(run, slowest_n)
    if not p["cases"]:
        return []
    lines = ["Performance:"]
    if show_time:
        w = p["wall"]
        lines.append(
            "  wall   total %s   avg %s   min %s   max %s"
            % (fmt_secs(w["total"]), fmt_secs(w["avg"]), fmt_secs(w["min"]), fmt_secs(w["max"]))
        )
        c = p["cpu"]
        lines.append("  cpu    total %s   max %s" % (fmt_secs(c["total"]), fmt_secs(c["max"])))
    if show_mem and p["memory_kb"]:
        m = p["memory_kb"]
        lines.append(
            "  memory max %s   avg %s   (%s)"
            % (fmt_mem_kb(m["max"]), fmt_mem_kb(int(m["avg"])), run.memory_note)
        )
    if p["slowest"]:
        lines.append(
            "  slowest "
            + ", ".join("%s %s" % (s["case"], fmt_secs(s["wall_time"])) for s in p["slowest"])
        )
    return lines


# --- exports ---


def to_json(run: RunResult) -> dict:
    groups = {
        g: {"passed": sum(1 for c in cs if c.status == "pass"), "total": len(cs)}
        for g, cs in run.by_group().items()
    }
    return {
        "solution": run.solution,
        "runner": run.runner,
        "started_at": run.started_at,
        "memory_note": run.memory_note,
        "summary": {
            "passed": run.passed,
            "failed": run.failed,
            "skipped": run.skipped,
            "total": run.total,
        },
        "groups": groups,
        "performance": performance(run),
        "cases": [c.to_dict() for c in run.cases],
    }


def to_markdown(run: RunResult) -> str:
    lines = [
        f"# Test results: {run.solution}",
        "",
        f"- Run at: {run.started_at}",
        f"- Result: **{run.passed}/{run.total} passed ({pct(run.passed, run.total)})**"
        + (f", {run.failed} failed" if run.failed else "")
        + (f", {run.skipped} skipped" if run.skipped else ""),
    ]
    fl = failure_line(run)
    if fl:
        lines.append(f"- {fl}")
    lines += [
        f"- Memory: {run.memory_note}",
        "",
        "## By group",
        "",
        "| Group | Passed | Total |",
        "| --- | --- | --- |",
    ]
    for g, cs in run.by_group().items():
        lines.append(f"| {g} | {sum(1 for c in cs if c.status == 'pass')} | {len(cs)} |")

    p = performance(run)
    if p["cases"]:
        w, c = p["wall"], p["cpu"]
        lines += [
            "",
            "## Performance",
            "",
            f"- Wall time: total {fmt_secs(w['total'])}, avg {fmt_secs(w['avg'])}, "
            f"min {fmt_secs(w['min'])}, max {fmt_secs(w['max'])}",
            f"- CPU time: total {fmt_secs(c['total'])}, max {fmt_secs(c['max'])}",
        ]
        if p["memory_kb"]:
            m = p["memory_kb"]
            lines.append(
                f"- Peak memory: max {fmt_mem_kb(m['max'])}, avg {fmt_mem_kb(int(m['avg']))}"
            )
        if p["slowest"]:
            lines.append(
                "- Slowest: "
                + ", ".join(f"{s['case']} ({fmt_secs(s['wall_time'])})" for s in p["slowest"])
            )

    lines += [
        "",
        "## Cases",
        "",
        "| Case | Status | Time | Peak mem | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in run.cases:
        note = c.verdict
        if c.memcheck is not None:
            note += " / mem ok" if c.memcheck else " / mem error"
        lines.append(
            f"| {c.case_id} | {c.status} | {fmt_secs(c.wall_time)} | {fmt_mem_kb(c.peak_mem_kb)} | {note} |"
        )
    return "\n".join(lines) + "\n"


def to_text(run: RunResult) -> str:
    lines = [
        f"Test results: {run.solution}",
        f"  {run.passed}/{run.total} passed ({pct(run.passed, run.total)})"
        + (f", {run.failed} failed" if run.failed else "")
        + (f", {run.skipped} skipped" if run.skipped else ""),
    ]
    fl = failure_line(run)
    if fl:
        lines.append("  " + fl)
    lines.append("")
    for c in run.cases:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "error": "ERR "}.get(c.status, "?")
        line = f"  [{mark}] {c.case_id}  {fmt_secs(c.wall_time)}"
        if c.peak_mem_kb > 0:
            line += f"  {fmt_mem_kb(c.peak_mem_kb)}"
        if c.verdict:
            line += f"  - {c.verdict}"
        lines.append(line)
    perf = perf_lines(run)
    if perf:
        lines.append("")
        lines += ["  " + ln for ln in perf]
    return "\n".join(lines) + "\n"


def export(run: RunResult, fmt: str) -> str:
    """Render a run in the requested text format (json/md/text)."""
    import json

    if fmt == "json":
        return json.dumps(to_json(run), indent=2) + "\n"
    if fmt in ("md", "markdown"):
        return to_markdown(run)
    return to_text(run)


# --- rival comparison (single source; mirrored in the runner core) ---
#
# A rival column is {label, run: RunResult, precomputed: bool, env: str}.


def _cmp_cell(cr, show_mem):
    if cr is None:
        return "-"
    if cr.timed_out:
        return "timeout"
    s = fmt_secs(cr.wall_time)
    if show_mem and cr.peak_mem_kb > 0:
        s += " " + fmt_mem_kb(cr.peak_mem_kb)
    if cr.status != "pass":
        s = cr.status.upper() + " " + s
    return s


def comparison_block(main_run, rival_cols, show_mem=True, per_case=True):
    """Text lines comparing the solution against each rival."""
    cols = [{"label": "solution", "run": main_run, "precomputed": False, "env": ""}] + list(
        rival_cols
    )
    lines = []

    if per_case:
        index = [(c["label"], {x.case_id: x for x in c["run"].cases}) for c in cols]
        header = "  %-22s" % "Case"
        for label, _ in index:
            header += " | %-20s" % label
        lines.append(header)
        for case in main_run.cases:
            row = "  %-22s" % case.case_id
            for _, by in index:
                row += " | %-20s" % _cmp_cell(by.get(case.case_id), show_mem)
            lines.append(row)
        lines.append("")

    lines.append("Comparison (vs solution):")
    # Aggregate each column over ONLY the cases in this run (the solution may be
    # a filtered subset while a precomputed rival covers everything).
    main_ids = set(c.case_id for c in main_run.cases)

    def _aligned(run):
        sub = RunResult(solution=run.solution)
        sub.cases = [c for c in run.cases if c.case_id in main_ids]
        return sub

    main_total = performance(_aligned(main_run))["wall"]["total"] or 1e-9
    for c in cols:
        run = _aligned(c["run"])
        p = performance(run)
        bits = "wall total %s  avg %s" % (fmt_secs(p["wall"]["total"]), fmt_secs(p["wall"]["avg"]))
        if show_mem:
            bits += "  peak %s" % (fmt_mem_kb(p["memory_kb"]["max"]) if p["memory_kb"] else "n/a")
        ratio = "" if c["label"] == "solution" else "  %.2fx" % (p["wall"]["total"] / main_total)
        note = (
            "  %d/%d pass" % (run.passed, run.total) if run.total and run.passed < run.total else ""
        )
        tag = ""
        if c.get("precomputed"):
            tag = "  [precomputed: %s]" % c["env"] if c.get("env") else "  [precomputed]"
        lines.append("  %-14s %s%s%s%s" % (c["label"], bits, ratio, note, tag))
    return lines


def comparison_json(main_run, rival_cols):
    return {
        "solution": {
            "name": "solution",
            "passed": main_run.passed,
            "total": main_run.total,
            "performance": performance(main_run),
        },
        "rivals": [
            {
                "name": c["label"],
                "precomputed": c.get("precomputed", False),
                "env": c.get("env", ""),
                "passed": c["run"].passed,
                "total": c["run"].total,
                "performance": performance(c["run"]),
            }
            for c in rival_cols
        ],
    }
