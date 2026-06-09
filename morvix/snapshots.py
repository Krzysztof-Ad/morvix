# Snapshots: pin the current inputs+answers so later drift is visible.
#
# A snapshot is a small JSON file recording, per case, a content hash of its
# input bytes and (if frozen) of its expected answer, plus the fingerprint of
# the solution that froze those answers. It is purely read-only bookkeeping:
# pinning sets no expectations and computes no answers, and a diff is framed as
# "drift to verify" - a list of what changed since the pin - never a pass/fail
# verdict. The student decides whether a change is intended. Snapshots live
# under .morvix/snapshots/<name>.json so the project root stays clean.

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

from morvix import layout, provenance
from morvix.errors import UserError


@dataclass
class SnapshotDiff:
    """What changed since a snapshot - drift to verify, not a verdict.

    Every list is a set of case ids; framed as "these moved, go check them",
    never as right/wrong. `solution_changed` flags that the answer-producing
    program itself was edited, so any frozen answer may now be stale.
    """

    name: str
    inputs_changed: List[str] = field(default_factory=list)  # input bytes differ now
    expected_changed: List[str] = field(default_factory=list)  # frozen answer hash differs
    added: List[str] = field(default_factory=list)  # cases that exist now but not in the pin
    removed: List[str] = field(default_factory=list)  # cases in the pin but gone now
    solution_changed: bool = False  # the solution fingerprint moved

    @property
    def drifted(self) -> bool:
        """True if anything moved at all (inputs, answers, set of cases, solution)."""
        return bool(
            self.inputs_changed
            or self.expected_changed
            or self.added
            or self.removed
            or self.solution_changed
        )


def _snapshot_path(project, name: str) -> str:
    return project.abspath(layout.SNAPSHOTS_DIR, name + ".json")


# The hash of a case's frozen answer, or None when no answer is frozen.
# An inline expected_hash is itself a digest, so we record it directly; an
# expected_output file is hashed from disk. We never compute the answer - only
# fingerprint whatever gen_expected already froze.
def _expected_hash(project, case):
    if case.expected_hash:
        return case.expected_hash
    if case.expected_output:
        path = project.abspath(case.expected_output)
        if os.path.exists(path):
            with open(path, "rb") as f:
                return provenance.hash_bytes(f.read())
    return None


# One per-case record: the input hash plus the frozen-answer hash (if any).
def _case_record(project, case) -> Dict:
    return {
        "input_hash": provenance.compute_input_hash(case, project.root),
        "expected_hash": _expected_hash(project, case),
    }


def pin(project, name: str) -> str:
    """Save a named snapshot of the current inputs + frozen answers; return its path.

    Records, per case id, a hash of the input bytes and of the expected answer
    (if one is frozen), plus the solution fingerprint that produced those
    answers. Read-only: it sets no expectations and runs no program.
    """
    if not name:
        raise UserError("A snapshot needs a name.", hint="For example: gen --pin before-refactor")
    cases = {case.id: _case_record(project, case) for case in project.cases}
    payload = {
        "name": name,
        "solution_fingerprint": provenance.solution_fingerprint(project),
        "cases": cases,
    }
    path = _snapshot_path(project, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return path


def list_snapshots(project) -> List[str]:
    """The names of every saved snapshot, sorted."""
    sdir = project.abspath(layout.SNAPSHOTS_DIR)
    if not os.path.isdir(sdir):
        return []
    return sorted(fn[:-5] for fn in os.listdir(sdir) if fn.endswith(".json"))


def load_snapshot(project, name: str) -> Dict:
    """Load a saved snapshot by name; raise UserError if there is no such pin."""
    path = _snapshot_path(project, name)
    if not os.path.exists(path):
        known = ", ".join(list_snapshots(project)) or "(none)"
        raise UserError(
            f"No snapshot named '{name}'.",
            hint=f"Saved snapshots: {known}. Make one with 'gen --pin {name}'.",
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def diff(project, name: str) -> SnapshotDiff:
    """Compare the current project against snapshot `name`; return the drift.

    Read-only hashing: it recomputes the same content hashes the pin recorded
    and reports which cases' inputs or frozen answers moved, which cases came or
    went, and whether the solution fingerprint changed. It never decides whether
    a change is correct - that is the student's call.
    """
    snap = load_snapshot(project, name)
    old_cases = snap.get("cases", {})
    diff_out = SnapshotDiff(name=name)

    now = {case.id: case for case in project.cases}
    diff_out.added = sorted(cid for cid in now if cid not in old_cases)
    diff_out.removed = sorted(cid for cid in old_cases if cid not in now)

    for cid, case in now.items():
        old = old_cases.get(cid)
        if old is None:
            continue
        if provenance.compute_input_hash(case, project.root) != old.get("input_hash"):
            diff_out.inputs_changed.append(cid)
        if _expected_hash(project, case) != old.get("expected_hash"):
            diff_out.expected_changed.append(cid)
    diff_out.inputs_changed.sort()
    diff_out.expected_changed.sort()

    old_fp = snap.get("solution_fingerprint", "")
    diff_out.solution_changed = provenance.solution_fingerprint(project) != old_fp
    return diff_out
