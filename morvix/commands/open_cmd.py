# open: load (or adopt) the project in the current directory.
#
# Usually the context already has a project loaded on startup, but "open" is
# the explicit way to (re)load it mid-session or after dropping a received
# package here. If neither a config nor a manifest is present we say so and
# point at init.

import os

from morvix import layout
from morvix.project import Project

NAME = "open"


def configure(parser):
    pass  # no arguments; open acts on ctx.root


def _detect_adoption(root: str) -> bool:
    """True when the config was written after the manifest.

    save_project writes config/project.json first then morvix.json, so for an
    authored project config_mtime <= manifest_mtime. A received package has
    only morvix.json; adopt_manifest writes the config afterward, giving
    config_mtime > manifest_mtime.
    """
    config_path = os.path.join(root, layout.PROJECT_FILE)
    manifest_path = os.path.join(root, layout.MANIFEST)
    if not os.path.exists(config_path) or not os.path.exists(manifest_path):
        return False
    return os.path.getmtime(config_path) > os.path.getmtime(manifest_path) + 0.001


def run(ctx, args) -> int:
    root = ctx.root

    if not layout.is_project(root):
        ctx.messenger.info("No Morvix project found here.")
        ctx.messenger.plain(f"  Run 'init' to create one in {root}")
        return 0

    # Detect adoption before (re)loading — see _detect_adoption for rationale.
    adopted = _detect_adoption(root)

    # (Re)load from disk so open always reflects the current file state.
    ctx.project = Project.load(root)

    if adopted:
        ctx.messenger.success(
            f"Package adopted: '{ctx.project.name}' — morvix.json converted to editable project."
        )
        # Persist config + manifest so config_mtime flips back below manifest_mtime;
        # subsequent opens show "Opened" rather than "Package adopted".
        ctx.save_project()
    else:
        ctx.messenger.success(f"Opened '{ctx.project.name}'.")

    # One-line summary: language, execution model, solution under test, case count.
    p = ctx.project
    lang = p.language or "(none)"
    solution = os.path.basename(p.solution) if p.solution else "(none)"
    total = len(p.cases)
    ctx.messenger.plain(f"  language={lang}  model={p.model}  solution={solution}  cases={total}")

    return 0
