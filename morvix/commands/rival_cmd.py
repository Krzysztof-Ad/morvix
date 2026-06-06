# rival command - manage performance-comparison solutions (Section: rivals).
#
# A rival is an alternative implementation kept only to compare performance
# against; it never affects the tests or the expected answers. One rival can be
# tagged as the stress-test oracle (replacing the old 'bruteforce').
#
#   rival add <path> [--name N] [--stress]
#   rival list
#   rival remove <name>
#   rival precompute            run rivals here and store their numbers (to ship)

import glob
import os

from morvix import comparison
from morvix.errors import UserError
from morvix.judge import select_cases
from morvix.project import Rival

NAME = "rival"
_ACTIONS = ["add", "list", "remove", "precompute"]


def configure(parser):
    parser.add_argument("action", choices=_ACTIONS, help="what to do")
    parser.add_argument("target", nargs="?", help="path (add) or rival name (remove)")
    parser.add_argument("--name", help="name for the rival (default: the file stem)")
    parser.add_argument(
        "--stress", action="store_true", help="use this rival as the stress-test oracle"
    )


def run(ctx, args) -> int:
    project = ctx.require_project()
    if args.action == "add":
        return _add(ctx, project, args)
    if args.action == "list":
        return _list(ctx, project)
    if args.action == "remove":
        return _remove(ctx, project, args)
    if args.action == "precompute":
        return _precompute(ctx, project)
    return 2


def _add(ctx, project, args):
    if not args.target:
        raise UserError("rival add needs a path.", hint="rival add path/to/other.c")
    path = os.path.abspath(args.target)
    if not os.path.exists(path):
        raise UserError(f"No such file: {args.target}")
    name = args.name or os.path.splitext(os.path.basename(path))[0]
    if args.stress:
        # Only one stress oracle; clear the flag on any others.
        for r in project.rivals:
            r.stress = False
    project.add_rival(Rival(name=name, path=path, stress=args.stress))
    ctx.save_project()
    extra = " (stress oracle)" if args.stress else ""
    ctx.messenger.success(f"Added rival '{name}'{extra}.")
    ctx.messenger.info(
        "It is used for performance comparison only - never for correctness, "
        "and not shipped unless you choose to."
    )
    return 0


def _list(ctx, project):
    if not project.rivals:
        ctx.messenger.info("No rivals registered. Add one with: rival add <path>")
        return 0
    for r in project.rivals:
        pre = comparison.load_precomputed(project.root, r.name) is not None
        flags = []
        if r.stress:
            flags.append("stress oracle")
        if pre:
            flags.append("precomputed")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        ctx.messenger.plain(f"  {r.name}  -  {r.path}{suffix}")
    return 0


def _remove(ctx, project, args):
    if not args.target or project.get_rival(args.target) is None:
        raise UserError(f"No rival named '{args.target}'.", hint="See 'rival list'.")
    project.remove_rival(args.target)
    ctx.save_project()
    ctx.messenger.success(f"Removed rival '{args.target}'.")
    return 0


def _precompute(ctx, project):
    if not project.rivals:
        raise UserError("No rivals to precompute.", hint="Add one with: rival add <path>")
    cases = select_cases(project)
    if not cases:
        raise UserError("No cases to run.", hint="Generate cases first (gen).")
    ctx.messenger.info(
        f"Running {len(project.rivals)} rival(s) over {len(cases)} case(s) on this machine..."
    )
    done = comparison.precompute_rivals(project, cases)
    for name, run in done.items():
        ctx.messenger.success(f"{name}: {run.passed}/{run.total} passed, recorded time/memory")
    ctx.messenger.info(
        "These numbers will ship with the package (code-free) so a Receiver on "
        "a comparable machine sees the comparison."
    )
    return 0


def complete(ctx, prev_words, word):
    if not prev_words or (len(prev_words) == 1 and prev_words[0] == NAME):
        return [(a, "action") for a in _ACTIONS if a.startswith(word or "")]
    action = prev_words[1] if len(prev_words) > 1 else ""
    if action == "add":
        return [(m, "file") for m in sorted(glob.glob((word or ".") + "*"))]
    if action == "remove" and ctx.project:
        return [(r.name, "rival") for r in ctx.project.rivals if r.name.startswith(word or "")]
    return []
