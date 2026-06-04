# Test cases: what one is, and how it lives on disk (Section 12).
#
# A case is a small bundle of metadata plus some files. The metadata (group,
# manual flag, expected behaviour, per-case overrides) lives in a JSON index;
# the bulk data (the input bytes, the expected output) lives as plain files
# under tests/ and expected/ so it stays inspectable, diffable and git-friendly.
# The files are the truth; the index just points at them and records intent.

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from morvix.layout import CASES_FILE, EXPECTED_DIR, TESTS_DIR


@dataclass
class TestCase:
    # Keep pytest from trying to collect this as a test class (the name starts
    # with "Test"); it is a data model, not a test.
    __test__ = False

    name: str
    group: str
    manual: bool = False                       # hand-written & permanent vs generated & disposable

    # Inputs: logical name -> path relative to tests/<group>/. The stdio model
    # uses the key "stdin"; a case may carry several named inputs at once.
    inputs: Dict[str, str] = field(default_factory=dict)
    args: List[str] = field(default_factory=list)   # argv, for the 'args' model

    # Expected behaviour. Several dimensions can be set at once and the judge
    # requires all enabled ones to pass (Section 14.7).
    expected_output: Optional[str] = None      # path under expected/ (full output)
    expected_hash: Optional[str] = None        # hex digest, when hashing instead
    expected_exit: Optional[int] = None        # expected exit code (None = expect clean 0)
    expected_signal: Optional[str] = None      # expected terminating signal, e.g. "SIGSEGV"
    expected_files: Dict[str, str] = field(default_factory=dict)  # produced name -> expected path

    compare: Optional[str] = None              # per-case comparison override
    limits: Dict[str, float] = field(default_factory=dict)        # per-case limit overrides

    @property
    def id(self) -> str:
        return f"{self.group}/{self.name}"

    def primary_input(self) -> Optional[str]:
        """The main input path (stdin if present, else the first one)."""
        if "stdin" in self.inputs:
            return self.inputs["stdin"]
        return next(iter(self.inputs.values()), None)

    # --- on-disk paths (absolute, given the project root) ---

    def input_abspath(self, root: str, key: str = "stdin") -> Optional[str]:
        rel = self.inputs.get(key)
        return os.path.join(root, rel) if rel else None

    def expected_output_abspath(self, root: str) -> Optional[str]:
        return os.path.join(root, self.expected_output) if self.expected_output else None

    def to_dict(self) -> dict:
        # Drop empty optionals so the JSON stays small and readable.
        d = {"name": self.name, "group": self.group, "manual": self.manual}
        for key in ("inputs", "args", "expected_files", "limits"):
            val = getattr(self, key)
            if val:
                d[key] = val
        for key in ("expected_output", "expected_hash", "expected_exit",
                    "expected_signal", "compare"):
            val = getattr(self, key)
            if val is not None:
                d[key] = val
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TestCase":
        return cls(
            name=d["name"],
            group=d.get("group", "baseline"),
            manual=d.get("manual", False),
            inputs=d.get("inputs", {}),
            args=d.get("args", []),
            expected_output=d.get("expected_output"),
            expected_hash=d.get("expected_hash"),
            expected_exit=d.get("expected_exit"),
            expected_signal=d.get("expected_signal"),
            expected_files=d.get("expected_files", {}),
            compare=d.get("compare"),
            limits=d.get("limits", {}),
        )


def default_input_relpath(group: str, name: str, key: str = "stdin") -> str:
    """Where a fresh input file should live under tests/."""
    suffix = "in" if key == "stdin" else key
    return os.path.join(TESTS_DIR, group, f"{name}.{suffix}")


def default_expected_relpath(group: str, name: str) -> str:
    """Where a fresh expected-output file should live under expected/."""
    return os.path.join(EXPECTED_DIR, group, f"{name}.out")


def load_cases(root: str) -> List[TestCase]:
    path = os.path.join(root, CASES_FILE)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [TestCase.from_dict(c) for c in data.get("cases", [])]


def save_cases(root: str, cases: List[TestCase]) -> None:
    path = os.path.join(root, CASES_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"cases": [c.to_dict() for c in cases]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def list_groups(cases: List[TestCase]) -> List[str]:
    """Distinct group names, in first-seen order."""
    seen = []
    for c in cases:
        if c.group not in seen:
            seen.append(c.group)
    return seen
