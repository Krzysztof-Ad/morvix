# Building the shippable runner (Section 16.2).
#
# The runner is two pieces: a portable, stdlib-only Python core (shipped
# verbatim from morvix/runner_core/morvix_runner.py) and a thin run.sh wrapper
# that finds a Python 3 and invokes it. This module assembles them into the
# project's runner/ directory; packaging copies them into the archive.

import os
import shutil
import stat

from morvix import layout

# Location of the shipped runner-core templates, next to this package.
_CORE_DIR = os.path.join(os.path.dirname(__file__), "runner_core")


def build_runner(project, runner):
    """Copy morvix_runner.py and run.sh into project.root/runner/.

    Creates runner/ if it does not already exist, then copies the two
    template files from runner_core, and marks both as executable.
    Returns the runner directory path.
    """
    runner_dir = os.path.join(project.root, layout.RUNNER_DIR)
    os.makedirs(runner_dir, exist_ok=True)

    # - copy core Python script
    src_core = os.path.join(_CORE_DIR, "morvix_runner.py")
    dst_core = os.path.join(runner_dir, "morvix_runner.py")
    shutil.copy2(src_core, dst_core)

    # - copy shell wrapper
    src_sh = os.path.join(_CORE_DIR, "run.sh")
    dst_sh = os.path.join(runner_dir, "run.sh")
    shutil.copy2(src_sh, dst_sh)

    # - make both files executable
    for path in (dst_core, dst_sh):
        current = os.stat(path).st_mode
        os.chmod(path, current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return runner_dir


# Capability descriptors keyed by backend name (Section 16.3).
# Each dict has boolean flags and a short human-readable note.
_CAPABILITIES = {
    "bash": {
        "timing": True,
        "peak_memory": False,
        "hard_caps": False,
        "memcheck": False,
        "note": "coarse wall-clock timing via 'time'; no memory measurement; pass/fail only",
    },
    "python": {
        "timing": True,
        "peak_memory": True,
        "hard_caps": True,
        "memcheck": False,
        "note": "precise per-run timing, approximate peak memory via resource, hard rlimit caps",
    },
    "valgrind": {
        "timing": True,
        "peak_memory": True,
        "hard_caps": True,
        "memcheck": True,
        "note": "everything python does plus memory-correctness verdicts via Valgrind",
    },
}


def runner_capabilities(backend):
    """Return a capability dict for the given backend name.

    Raises KeyError for unknown backends.
    """
    return dict(_CAPABILITIES[backend])
