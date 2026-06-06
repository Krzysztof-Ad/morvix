# Project state and configuration (Section 3, Section 9, Section 25).
#
# A project is one assignment's worth of state living in a directory. This
# module is the in-memory view of it: the editable config (config/project.json),
# the runner profiles (config/runners/*.json) and the case index (cases.py),
# loaded on open and written back as you go. There is no database - the
# directory is the state.

import json
import os
import shutil
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
    groups: List[str] = field(default_factory=list)  # [] means every group
    cases: List[str] = field(default_factory=list)  # specific case ids; [] means all
    compare: Optional[str] = None  # None = project default
    backend: str = "python"  # bash | python | valgrind
    time: bool = True
    measure_mem: bool = True
    hard_kill: bool = False
    memcheck: bool = False
    diff: bool = True
    color: bool = True
    verbosity: str = "normal"  # quiet | normal | verbose
    report: bool = True  # show the performance summary after the run
    slowest: int = 5  # how many slowest cases to list
    limits: Dict[str, Optional[float]] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    result_format: str = "md"  # md | json | text | none
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
            "report": self.report,
            "slowest": self.slowest,
            "limits": self.limits,
            "result_format": self.result_format,
            "result_path": self.result_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Runner":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Rival:
    """An alternative implementation kept for PERFORMANCE comparison (not for
    correctness). Many are allowed; one may be tagged as the stress oracle. A
    rival never affects the expected answers - those always come from the
    solution under test."""

    name: str
    path: str
    stress: bool = False  # use this one as the stress-test oracle

    def to_dict(self) -> dict:
        return {"name": self.name, "path": self.path, "stress": self.stress}

    @classmethod
    def from_dict(cls, d: dict) -> "Rival":
        return cls(name=d["name"], path=d["path"], stress=d.get("stress", False))


@dataclass
class Project:
    root: str
    name: str
    model: str = "stdio"
    locale: str = "C"
    compare: Dict = field(default_factory=lambda: dict(DEFAULT_COMPARE))
    limits: Dict = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    languages: Dict[str, dict] = field(default_factory=dict)  # lang -> settings
    raw_build: Optional[str] = None
    raw_run: Optional[str] = None
    solution: Optional[str] = None  # current solution under test
    solution_copied: bool = False  # was it copied in, or referenced in place
    language: Optional[str] = None  # active language for build/run
    rivals: List[Rival] = field(default_factory=list)  # perf-comparison solutions
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
        editable (Section 19.4, Section 20.3). A pre-0.2 flat project is migrated
        into .morvix/ first, transparently.
        """
        if not layout.is_new_layout(root) and layout.is_legacy_layout(root):
            migrate_legacy_layout(root)
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
        proj = cls(
            root=root,
            name=data.get("name", os.path.basename(os.path.abspath(root))),
            model=data.get("model", "stdio"),
            locale=data.get("locale", "C"),
            compare={**DEFAULT_COMPARE, **data.get("compare", {})},
            limits={**DEFAULT_LIMITS, **data.get("limits", {})},
            languages=data.get("languages", {}),
            raw_build=data.get("raw_build"),
            raw_run=data.get("raw_run"),
            solution=data.get("solution"),
            solution_copied=data.get("solution_copied", False),
            language=data.get("language"),
            rivals=[Rival.from_dict(r) for r in data.get("rivals", [])],
        )
        # Back-compat: pre-0.7 projects stored a single 'bruteforce' path and a
        # 'reference'. The reference role is gone (answers come from the solution
        # now); a bruteforce folds into a stress-test rival so old projects keep
        # their oracle.
        legacy_bf = data.get("bruteforce")
        if legacy_bf and not any(r.name == "brute" for r in proj.rivals):
            proj.rivals.append(Rival(name="brute", path=legacy_bf, stress=True))
        return proj

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
            "solution": self.solution,
            "solution_copied": self.solution_copied,
            "language": self.language,
            "rivals": [r.to_dict() for r in self.rivals],
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

    def get_rival(self, name: str) -> Optional[Rival]:
        for r in self.rivals:
            if r.name == name:
                return r
        return None

    def add_rival(self, rival: Rival) -> None:
        self.rivals = [r for r in self.rivals if r.name != rival.name]
        self.rivals.append(rival)

    def remove_rival(self, name: str) -> None:
        self.rivals = [r for r in self.rivals if r.name != name]

    def stress_rival(self) -> Optional[Rival]:
        for r in self.rivals:
            if r.stress:
                return r
        return None

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


# --- migrating a pre-0.2 flat project into .morvix/ ---


def migrate_legacy_layout(root: str) -> None:
    """Move an old flat layout (config/, tests/, ... at the root) into .morvix/.

    Old projects stored their state directly in the project root; new ones tuck
    it all under .morvix/. We move the directories, then prefix the stored case
    paths and any copied-in solution path so they resolve against the new home.
    """
    state = os.path.join(root, layout.STATE_DIR)
    os.makedirs(state, exist_ok=True)
    for name in layout._LEGACY_DIRS + ["morvix.json"]:
        src = os.path.join(root, name)
        dst = os.path.join(state, name)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.move(src, dst)
    _prefix_case_paths(root)
    _prefix_copied_paths(root)


def _with_state(p: str) -> str:
    if p.startswith(layout.STATE_DIR + os.sep) or p.startswith(layout.STATE_DIR + "/"):
        return p
    return os.path.join(layout.STATE_DIR, p)


def _prefix_case_paths(root: str) -> None:
    path = os.path.join(root, layout.CASES_FILE)
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for c in data.get("cases", []):
        if c.get("inputs"):
            c["inputs"] = {k: _with_state(v) for k, v in c["inputs"].items()}
        if c.get("expected_output"):
            c["expected_output"] = _with_state(c["expected_output"])
        if c.get("expected_files"):
            c["expected_files"] = {k: _with_state(v) for k, v in c["expected_files"].items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _prefix_copied_paths(root: str) -> None:
    # A copied-in solution lived under solutions/; point at its new home.
    path = os.path.join(root, layout.PROJECT_FILE)
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    changed = False
    # Only the solution is ever copied in under solutions/; a legacy bruteforce
    # may still carry a relative path that needs re-homing too.
    for key in ("solution", "bruteforce"):
        v = d.get(key)
        if (
            v
            and not os.path.isabs(v)
            and (v.startswith("solutions" + os.sep) or v.startswith("solutions/"))
        ):
            d[key] = _with_state(v)
            changed = True
    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
            f.write("\n")


# --- .gitignore for a project ---

# What a fresh project ignores: transient run results, the private copied-in
# solution, and the usual build artifacts. The shareable harness (tests,
# expected answers, config, manifest) stays committed.
GITIGNORE = """# Morvix - transient and private state
.morvix/results/
.morvix/solutions/

# Build artifacts
a.out
*.o
*.obj
*.class
*.exe
__pycache__/
*.pyc
/target/
"""


def ensure_gitignore(root: str) -> bool:
    """Write a sensible .gitignore at the project root if there isn't one.

    Returns True if it created the file, False if one already existed (we never
    overwrite the user's own .gitignore).
    """
    path = os.path.join(root, ".gitignore")
    if os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(GITIGNORE)
    return True


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
