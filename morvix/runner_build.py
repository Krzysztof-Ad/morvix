# Building the shippable runner (Section 16.2).
#
# The runner is two pieces: a portable, stdlib-only Python core (shipped
# verbatim from morvix/runner_core/morvix_runner.py) and a thin run.sh wrapper
# that finds a Python 3 and invokes it. This module assembles them into the
# project's runner/ directory; packaging copies them into the archive.
#
# API (implement in Workflow B):
#   build_runner(project, runner) -> str   # writes runner/, returns its path
#   runner_capabilities(backend: str) -> dict   # what a backend can measure (Section 16.3)


def build_runner(project, runner):
    raise NotImplementedError


def runner_capabilities(backend):
    raise NotImplementedError
