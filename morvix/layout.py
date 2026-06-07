# The names of things on disk, in one place.
#
# A Morvix project keeps all of its state inside a single hidden directory,
# .morvix/, so the project root stays clean - just the user's own source files
# next to one .morvix/ folder. Everything here is rooted under that dir, so the
# rest of the codebase never spells out ".morvix" itself.
#
# A package archive is FLAT instead (see packaging.py): run.sh, README, the
# manifest and the tests/expected/runner trees all sit at the archive root, so a
# receiver sees the harness directly. A Morvix-equipped receiver that opens one
# re-adopts it back into .morvix/.

import os

STATE_DIR = ".morvix"  # the one hidden directory that holds everything

# Top-level files
MANIFEST = os.path.join(STATE_DIR, "morvix.json")  # generated, shareable descriptor
README = "README.md"  # stays at the (project / archive) root

# Directories, all under .morvix/
CONFIG_DIR = os.path.join(STATE_DIR, "config")
TESTS_DIR = os.path.join(STATE_DIR, "tests")  # input cases, grouped
EXPECTED_DIR = os.path.join(STATE_DIR, "expected")  # expected outputs / hashes
SOLUTIONS_DIR = os.path.join(STATE_DIR, "solutions")  # imported solutions (never packaged)
GENERATORS_DIR = os.path.join(STATE_DIR, "generators")
RUNNER_DIR = os.path.join(STATE_DIR, "runner")  # the shippable runner (core + run.sh)
RESULTS_DIR = os.path.join(STATE_DIR, "results")
WORKFLOWS_DIR = os.path.join(STATE_DIR, "workflows")
SNAPSHOTS_DIR = os.path.join(STATE_DIR, "snapshots")  # named input/answer snapshots

# Files under config/
PROJECT_FILE = os.path.join(CONFIG_DIR, "project.json")  # editable config
CASES_FILE = os.path.join(CONFIG_DIR, "cases.json")  # the case index
RUNNERS_DIR = os.path.join(CONFIG_DIR, "runners")  # one file per runner

DEFAULT_GROUP = "baseline"

# Every directory a fresh project gets.
PROJECT_DIRS = [
    CONFIG_DIR,
    RUNNERS_DIR,
    TESTS_DIR,
    EXPECTED_DIR,
    SOLUTIONS_DIR,
    GENERATORS_DIR,
    RUNNER_DIR,
    RESULTS_DIR,
    WORKFLOWS_DIR,
    SNAPSHOTS_DIR,
]

# The flat (pre-0.2) layout, kept only so old projects can be detected and
# migrated into .morvix/ automatically.
_LEGACY_PROJECT_FILE = os.path.join("config", "project.json")
_LEGACY_MANIFEST = "morvix.json"
_LEGACY_DIRS = [
    "config",
    "tests",
    "expected",
    "solutions",
    "generators",
    "runner",
    "results",
    "workflows",
]


def is_project(root: str) -> bool:
    """True if root holds a Morvix project - new .morvix/ layout or legacy flat."""
    return is_new_layout(root) or is_legacy_layout(root)


def is_new_layout(root: str) -> bool:
    return os.path.exists(os.path.join(root, PROJECT_FILE)) or os.path.exists(
        os.path.join(root, MANIFEST)
    )


def is_legacy_layout(root: str) -> bool:
    return os.path.exists(os.path.join(root, _LEGACY_PROJECT_FILE)) or os.path.exists(
        os.path.join(root, _LEGACY_MANIFEST)
    )
