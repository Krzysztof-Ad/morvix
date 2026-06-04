# Guards the zero-install promise (Section 16.2): the runner core that ships
# inside packages must import ONLY the standard library and never morvix. This
# is the easiest thing to break by accident, so it gets a permanent test.

import ast
import importlib
import os
import sys

RUNNER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "morvix", "runner_core", "morvix_runner.py")


def _top_level_imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:   # absolute imports only
                mods.add(node.module.split(".")[0])
    return mods


def test_runner_core_never_imports_morvix():
    assert "morvix" not in _top_level_imports(RUNNER)


def test_runner_core_is_stdlib_only():
    # Every top-level import must resolve to the stdlib, never site-packages.
    offenders = []
    for name in sorted(_top_level_imports(RUNNER)):
        if name in sys.builtin_module_names:
            continue
        try:
            mod = importlib.import_module(name)
        except ImportError:
            offenders.append(name + " (not importable)")
            continue
        path = (getattr(mod, "__file__", None) or "").replace(os.sep, "/")
        if "site-packages" in path or "dist-packages" in path:
            offenders.append(name + " -> " + path)
    assert not offenders, "runner core imports non-stdlib modules: %s" % offenders
