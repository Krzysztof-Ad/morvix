# Project status summary.
#
# Shows a compact snapshot of the current project so a user can confirm
# what morvix knows about their setup before running tests.

import os

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from morvix import layout
from morvix.cases import list_groups
from morvix.importers import INPUT_EXTS

NAME = "status"


def configure(parser):
    pass  # no arguments; status is always a full snapshot


def run(ctx, args) -> int:
    if ctx.project is None:
        ctx.messenger.info("No project found here.")
        ctx.messenger.info("Run 'init' to create one in this directory.")
        return 0

    p = ctx.project

    # --- build the two-column info table ---
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column("key", style="muted", no_wrap=True)
    t.add_column("value", style="")

    def row(label, value, style=""):
        t.add_row(label, Text(str(value), style=style) if style else str(value))

    row("name", p.name, "heading")
    row("language", p.language or "—")
    row("model", p.model)
    row("locale", p.locale)

    # Comparison strategy - default key is usually "strategy"
    compare_str = p.compare.get("strategy", None) or str(p.compare)
    row("compare", compare_str)

    # Default limits: show the most relevant ones compactly
    limit_parts = [f"{k}={v}" for k, v in p.limits.items() if v is not None]
    row("limits", "  ".join(limit_parts) if limit_parts else "—")

    row("solution", p.solution or "none", "" if p.solution else "muted")
    # Rivals are performance-comparison solutions; one may be the stress oracle.
    if p.rivals:
        labels = [r.name + (" (stress)" if r.stress else "") for r in p.rivals]
        row("rivals", ", ".join(labels))
    else:
        row("rivals", "—")
    row("runners", str(len(p.runners)))

    # --- case counts per group ---
    if p.cases:
        groups = list_groups(p.cases)
        for g in groups:
            count = sum(1 for c in p.cases if c.group == g)
            manual = sum(1 for c in p.cases if c.group == g and c.manual)
            detail = f"{count} case{'s' if count != 1 else ''}"
            if manual:
                detail += f"  ({manual} manual)"
            row(f"group:{g}", detail)
    else:
        row("cases", "none yet", "muted")

    panel = Panel(
        t,
        title=Text(f"morvix: {p.name}", style="accent"),
        title_align="left",
        border_style="muted",
        padding=(0, 1),
    )
    ctx.console.print(panel)

    # The directory isn't scanned for cases - morvix tracks them in its config.
    # Loose input files dropped under tests/ would otherwise be silently ignored,
    # which contradicts the "directory is the state" mental model, so flag them.
    orphans = _unregistered_inputs(p)
    if orphans:
        shown = ", ".join(orphans[:5]) + (" ..." if len(orphans) > 5 else "")
        ctx.messenger.warning(
            f"{len(orphans)} input file(s) under tests/ aren't registered as cases: {shown}",
            hint="Morvix tracks cases in its config, not by scanning folders. Bring loose "
            "inputs in with 'gen --import <dir> --keep-names' (inputs are .in/.txt; answers "
            "like .out/.ans are stripped).",
        )
    return 0


def _unregistered_inputs(project):
    """Input files sitting under the tests tree that no case references."""
    tests_dir = os.path.join(project.root, layout.TESTS_DIR)
    if not os.path.isdir(tests_dir):
        return []
    registered = set()
    for case in project.cases:
        for rel in case.inputs.values():
            registered.add(os.path.normpath(os.path.join(project.root, rel)))
    orphans = []
    for dirpath, _dirs, files in os.walk(tests_dir):
        for fn in files:
            if os.path.splitext(fn)[1].lower() in INPUT_EXTS:
                ap = os.path.normpath(os.path.join(dirpath, fn))
                if ap not in registered:
                    orphans.append(os.path.relpath(ap, project.root))
    return sorted(orphans)
