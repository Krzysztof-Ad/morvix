# Results and reporting (Section 17).
#
# After a run we have, per case, a verdict and some numbers. This module is the
# data model for that (CaseResult, RunResult) plus the three export formats:
# JSON (machine-readable, for diffing and cross-solution agreement), Markdown
# (the human report), and plain text (for minimal environments).

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class CaseResult:
    case_id: str
    group: str
    status: str                       # "pass" | "fail" | "skip" | "error"
    verdict: str = ""                 # short human reason
    exit_code: Optional[int] = None
    signal: Optional[str] = None
    timed_out: bool = False
    wall_time: float = 0.0
    cpu_time: float = 0.0
    peak_mem_kb: int = 0
    diff: Optional[str] = None        # unified diff when available
    memcheck: Optional[bool] = None   # valgrind verdict; None if not run

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


@dataclass
class RunResult:
    solution: str
    runner: Optional[str] = None
    cases: List[CaseResult] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    memory_note: str = "peak, approximate"   # honest label (Section 15.1)

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

    def by_group(self) -> Dict[str, List[CaseResult]]:
        groups: Dict[str, List[CaseResult]] = {}
        for c in self.cases:
            groups.setdefault(c.group, []).append(c)
        return groups


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
        "summary": {"passed": run.passed, "failed": run.failed,
                    "skipped": run.skipped, "total": run.total},
        "groups": groups,
        "cases": [c.to_dict() for c in run.cases],
    }


def to_markdown(run: RunResult) -> str:
    lines = [
        f"# Test results: {run.solution}",
        "",
        f"- Run at: {run.started_at}",
        f"- Result: **{run.passed}/{run.total} passed**"
        + (f", {run.failed} failed" if run.failed else "")
        + (f", {run.skipped} skipped" if run.skipped else ""),
        f"- Memory: {run.memory_note}",
        "",
        "## By group",
        "",
        "| Group | Passed | Total |",
        "| --- | --- | --- |",
    ]
    for g, cs in run.by_group().items():
        lines.append(f"| {g} | {sum(1 for c in cs if c.status == 'pass')} | {len(cs)} |")
    lines += ["", "## Cases", "", "| Case | Status | Time (s) | Peak mem (KB) | Notes |",
              "| --- | --- | --- | --- | --- |"]
    for c in run.cases:
        note = c.verdict
        if c.memcheck is not None:
            note += (" / mem ok" if c.memcheck else " / mem error")
        lines.append(
            f"| {c.case_id} | {c.status} | {c.wall_time:.3f} | {c.peak_mem_kb} | {note} |"
        )
    return "\n".join(lines) + "\n"


def to_text(run: RunResult) -> str:
    lines = [f"Test results: {run.solution}",
             f"  {run.passed}/{run.total} passed"
             + (f", {run.failed} failed" if run.failed else "")
             + (f", {run.skipped} skipped" if run.skipped else ""),
             f"  memory: {run.memory_note}", ""]
    for c in run.cases:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "error": "ERR "}.get(c.status, "?")
        line = f"  [{mark}] {c.case_id}  {c.wall_time:.3f}s"
        if c.verdict:
            line += f"  - {c.verdict}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def export(run: RunResult, fmt: str) -> str:
    """Render a run in the requested text format (json/md/text)."""
    import json

    if fmt == "json":
        return json.dumps(to_json(run), indent=2) + "\n"
    if fmt in ("md", "markdown"):
        return to_markdown(run)
    return to_text(run)
