# Remove generated test cases from the project.
#
# Generated cases (manual=False) are disposable; manual cases are permanent.
# --group filters to a single group; --yes skips the confirmation prompt.

from morvix import generators
from morvix.cases import list_groups
from morvix.components.confirm import confirm

NAME = "clean"


def configure(parser):
    parser.add_argument("--group", "-g", metavar="G",
                        help="only remove generated cases in this group")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="skip confirmation prompt")


def run(ctx, args) -> int:
    project = ctx.require_project()

    # Count how many generated cases would be removed
    group = args.group
    count = sum(
        1 for c in project.cases
        if not c.manual and (group is None or c.group == group)
    )

    if count == 0:
        ctx.messenger.info("No generated cases to remove.")
        return 0

    # Ask unless --yes was passed
    if not args.yes:
        question = f"Remove {count} generated case{'s' if count != 1 else ''}? Manual cases are kept."
        if not confirm(ctx, question, default=False):
            ctx.messenger.info("Aborted.")
            return 0

    removed = generators.clean_generated(project, group)
    ctx.save_project()
    ctx.messenger.success(f"Removed {removed} generated case{'s' if removed != 1 else ''}.")
    return 0


def complete(ctx, prev_words, word):
    # Suggest known group names after --group
    if prev_words and prev_words[-1] in ("--group", "-g"):
        if ctx.project:
            groups = list_groups(ctx.project.cases)
            return [(g, "group") for g in groups if g.startswith(word)]
    return []
