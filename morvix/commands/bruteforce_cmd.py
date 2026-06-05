# Deprecated: add a stress-oracle rival.
#
# Kept for compatibility. 'bruteforce <path>' now adds the file as a rival
# tagged as the stress oracle - identical to 'rival add <path> --stress'.

import os

from morvix.errors import UserError
from morvix.project import Rival

NAME = "bruteforce"


def configure(parser):
    parser.add_argument("path", help="Path to the brute-force solution file.")


def run(ctx, args) -> int:
    project = ctx.require_project()

    path = os.path.abspath(args.path)
    if not os.path.isfile(path):
        raise UserError(f"File not found: {args.path}", hint="Check the path and try again.")

    name = os.path.splitext(os.path.basename(path))[0]
    for r in project.rivals:
        r.stress = False
    project.add_rival(Rival(name=name, path=path, stress=True))
    ctx.save_project()

    ctx.messenger.warning("'bruteforce' is deprecated - use 'rival add <path> --stress'.")
    ctx.messenger.success(f"Added stress-oracle rival '{name}'.")
    ctx.messenger.info("It powers stress testing (gen --stress) and is never packaged unless "
                       "you opt to ship rival code.")
    return 0


def complete(ctx, prev_words, word):
    # Suggest files matching the current prefix.
    import glob

    pattern = (word or "") + "*"
    matches = glob.glob(pattern)
    return [(m, "file") for m in matches]
