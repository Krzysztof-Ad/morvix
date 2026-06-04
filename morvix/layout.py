# The names of things on disk, in one place.
#
# A Morvix project IS its directory (Section 24), so the directory layout is a
# contract shared by half the codebase. Keeping the names here means nobody
# hard-codes "tests" or "morvix.json" in three different spellings.

import os

# Top-level files
MANIFEST = "morvix.json"          # the generated, shareable descriptor
README = "README.md"

# Directories
CONFIG_DIR = "config"
TESTS_DIR = "tests"               # input cases, grouped into subdirectories
EXPECTED_DIR = "expected"         # expected outputs / hashes, paralleling tests/
SOLUTIONS_DIR = "solutions"       # imported solutions (never packaged)
GENERATORS_DIR = "generators"
RUNNER_DIR = "runner"             # the shippable runner (core + run.sh)
RESULTS_DIR = "results"
WORKFLOWS_DIR = "workflows"

# Files under config/
PROJECT_FILE = os.path.join(CONFIG_DIR, "project.json")   # editable config
CASES_FILE = os.path.join(CONFIG_DIR, "cases.json")       # the case index
RUNNERS_DIR = os.path.join(CONFIG_DIR, "runners")         # one file per runner

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
]


def is_project(root: str) -> bool:
    """A directory is a project if it has our config or a manifest to adopt."""
    return os.path.exists(os.path.join(root, PROJECT_FILE)) or os.path.exists(
        os.path.join(root, MANIFEST)
    )
