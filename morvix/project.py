# Project state and configuration (Section 3, Section 9, Section 25).
#
# A project is one assignment's worth of state living in a directory. This
# module is the in-memory view of it: the editable config (config/project.json),
# the runner profiles (config/runners/*.json) and the case index (cases.py),
# loaded on open and written back as you go. There is no database - the
# directory is the state.

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from morvix import layout
from morvix.cases import TestCase, load_cases, save_cases

# Built-in defaults, the lowest rung of the precedence ladder
# (flags > project > global > built-in, Section 9.2).
DEFAULT_COMPARE = {"strategy": "whitespace", "epsilon_abs": 1e-6, "epsilon_rel": 1e-9}
DEFAULT_LIMITS = {"wall": 10.0, "cpu": None, "mem_kb": None, "output_kb": None}


@dataclass
class Runner:
    """A named, shareable execution profile (Section 16)."""

    name: str
    groups: List[str] = field(default_factory=list)   # [] means every group
    cases: List[str] = field(default_factory=list)     # specific case ids; [] means all
    compare: Optional[str] = None                      # None = project default
    backend: str = "python"                            # bash | python | valgrind
    time: bool = True
    measure_mem: bool = True
    hard_kill: bool = False
    memcheck: bool = False
    diff: bool = True
    color: bool = True
    verbosity: str = "normal"                          # quiet | normal | verbose
    limits: Dict[str, Optional[float]] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    result_format: str = "md"                          # md | json | text | none
    result_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "groups": self.groups,
            "cases": self.cases,
            "compare": self.compare,
            "backend": self.backend,
            "time": self.time,
            "measure_mem": self.measure_mem,
            "hard_kill": self.hard_kill,
            "memcheck": self.memcheck,
            "diff": self.diff,
            "color": self.color,
            "verbosity": self.verbosity,
            "limits": self.limits,
            "result_format": self.result_format,
            "result_path": self.result_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Runner":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Project:
    root: str
    name: str
    model: str = "stdio"
    locale: str = "C"
    compare: Dict = field(default_factory=lambda: dict(DEFAULT_COMPARE))
    limits: Dict = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    languages: Dict[str, dict] = field(default_factory=dict)   # lang -> settings
    raw_build: Optional[str] = None
    raw_run: Optional[str] = None
    reference: Optional[str] = None        # solution that defines expected answers
    bruteforce: Optional[str] = None       # slow trusted solution for stress testing
    solution: Optional[str] = None         # current solution under test
    solution_copied: bool = False          # was it copied in, or referenced in place
    language: Optional[str] = None         # active language for build/run
    cases: List[TestCase] = field(default_factory=list)
    runners: Dict[str, Runner] = field(default_factory=dict)

    # --- creation / loading / saving ---

    @classmethod
    def create(cls, root: str, name: str) -> "Project":
        """Lay down a fresh project on disk and return it."""
        for d in layout.PROJECT_DIRS:
            os.makedirs(os.path.join(root, d), exist_ok=True)
        proj = cls(root=root, name=name)
        proj.save()
        return proj

    @classmethod
    def load(cls, root: str) -> "Project":
        """Load a project from disk.

        Prefers the editable config/project.json. If only a manifest is present
        (a received package), it is adopted into a fresh project so it becomes
        editable (Section 19.4, Section 20.3).
        """
        project_path = os.path.join(root, layout.PROJECT_FILE)
        if os.path.exists(project_path):
            with open(project_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            proj = cls._from_config(root, data)
        elif os.path.exists(os.path.join(root, layout.MANIFEST)):
            from morvix.manifest import adopt_manifest
            proj = adopt_manifest(root)
        else:
            raise FileNotFoundError(f"No Morvix project in {root}")
        proj.cases = load_cases(root)
        proj.runners = _load_runners(root)
        return proj

    @classmethod
    def _from_config(cls, root: str, data: dict) -> "Project":
        return cls(
            root=root,
            name=data.get("name", os.path.basename(os.path.abspath(root))),
            model=data.get("model", "stdio"),
            locale=data.get("locale", "C"),
            compare={**DEFAULT_COMPARE, **data.get("compare", {})},
            limits={**DEFAULT_LIMITS, **data.get("limits", {})},
            languages=data.get("languages", {}),
            raw_build=data.get("raw_build"),
            raw_run=data.get("raw_run"),
            reference=data.get("reference"),
            bruteforce=data.get("bruteforce"),
            solution=data.get("solution"),
            solution_copied=data.get("solution_copied", False),
            language=data.get("language"),
        )

    def _config_dict(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "locale": self.locale,
            "compare": self.compare,
            "limits": self.limits,
            "languages": self.languages,
            "raw_build": self.raw_build,
            "raw_run": self.raw_run,
            "reference": self.reference,
            "bruteforce": self.bruteforce,
            "solution": self.solution,
            "solution_copied": self.solution_copied,
            "language": self.language,
        }

    def save(self) -> None:
        """Write config and the case index back to disk."""
        os.makedirs(os.path.join(self.root, layout.CONFIG_DIR), exist_ok=True)
        path = os.path.join(self.root, layout.PROJECT_FILE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._config_dict(), f, indent=2)
            f.write("\n")
        save_cases(self.root, self.cases)
        _save_runners(self.root, self.runners)

    # --- convenience ---

    def lang_config(self, language: str) -> dict:
        return self.languages.get(language, {})

    def set_lang_config(self, language: str, config: dict) -> None:
        self.languages[language] = config

    def get_case(self, case_id: str) -> Optional[TestCase]:
        for c in self.cases:
            if c.id == case_id:
                return c
        return None

    def add_case(self, case: TestCase) -> None:
        """Add or replace a case with the same id."""
        self.cases = [c for c in self.cases if c.id != case.id]
        self.cases.append(case)

    def remove_case(self, case_id: str) -> None:
        self.cases = [c for c in self.cases if c.id != case_id]

    def abspath(self, *parts: str) -> str:
        return os.path.join(self.root, *parts)


def resolve_limits(project: Project, runner: Optional[Runner], case: Optional[TestCase]) -> Dict:
    """Effective limits, applying case > runner > project precedence."""
    limits = dict(project.limits)
    if runner:
        limits.update({k: v for k, v in runner.limits.items() if v is not None})
    if case and case.limits:
        limits.update(case.limits)
    return limits


def _load_runners(root: str) -> Dict[str, Runner]:
    runners: Dict[str, Runner] = {}
    rdir = os.path.join(root, layout.RUNNERS_DIR)
    if not os.path.isdir(rdir):
        return runners
    for fn in sorted(os.listdir(rdir)):
        if fn.endswith(".json"):
            with open(os.path.join(rdir, fn), "r", encoding="utf-8") as f:
                runners[fn[:-5]] = Runner.from_dict(json.load(f))
    return runners


def _save_runners(root: str, runners: Dict[str, Runner]) -> None:
    rdir = os.path.join(root, layout.RUNNERS_DIR)
    os.makedirs(rdir, exist_ok=True)
    on_disk = {fn[:-5] for fn in os.listdir(rdir) if fn.endswith(".json")}
    for name, runner in runners.items():
        with open(os.path.join(rdir, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(runner.to_dict(), f, indent=2)
            f.write("\n")
    # Drop runner files that were deleted in memory.
    for stale in on_disk - set(runners):
        os.remove(os.path.join(rdir, stale + ".json"))


# --- global personal config (Section 25.5) ---

def global_config_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "morvix", "config.json")


def load_global_config() -> dict:
    path = global_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_global_config(config: dict) -> None:
    path = global_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
