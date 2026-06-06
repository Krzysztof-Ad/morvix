# Shared pytest helpers.
#
# Tests build small throwaway projects in tmp_path and judge tiny programs, so
# they need a couple of conveniences: a way to skip when a toolchain is missing,
# and a quick "make me a configured python project" fixture.

import shutil

import pytest

from morvix.context import Context
from morvix.project import Project
from morvix.theme import make_console


def have(tool: str) -> bool:
    return shutil.which(tool) is not None


def requires(tool: str):
    """Decorator/mark: skip a test when a needed toolchain is absent."""
    return pytest.mark.skipif(not have(tool), reason=f"{tool} not installed")


def write(path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return str(path)


# A correct reference: read all whitespace-separated ints, print their sum.
SUM_ALL_PY = "import sys\nd = sys.stdin.read().split()\nprint(sum(int(x) for x in d))\n"


@pytest.fixture
def make_ctx():
    """Return a factory that builds a non-interactive Context on a directory."""
    def _make(root):
        return Context.create(str(root), interactive=False, console=make_console(force_plain=True))
    return _make


@pytest.fixture
def py_project(tmp_path, make_ctx):
    """A ready python project in tmp_path with the solution imported."""
    sol = tmp_path / "sol.py"
    sol.write_text(SUM_ALL_PY)
    proj = Project.create(str(tmp_path), "t")
    proj.language = "python"
    proj.model = "stdio"
    proj.solution = str(sol)
    proj.save()
    ctx = make_ctx(tmp_path)
    ctx.project = proj
    return ctx, proj
