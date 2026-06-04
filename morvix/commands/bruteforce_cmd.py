# Register a brute-force solution for stress testing.
#
# Sets project.bruteforce to the absolute path of the given file. This
# solution is never included in packages; it is used only during stress
# testing to compare outputs against the solution under test.

import os

from morvix.errors import UserError

NAME = "bruteforce"


def configure(parser):
    parser.add_argument("path", help="Path to the brute-force solution file.")


def run(ctx, args) -> int:
    project = ctx.require_project()

    path = os.path.abspath(args.path)
    if not os.path.isfile(path):
        raise UserError(
            f"File not found: {args.path}",
            hint="Check the path and try again.",
        )

    project.bruteforce = path
    ctx.save_project()

    ctx.messenger.success(f"Brute-force solution set to {path}")
    ctx.messenger.info(
        "This solution powers stress testing (gen --stress). "
        "It is never included in a package."
    )
    return 0


def complete(ctx, prev_words, word):
    # Suggest files matching the current prefix.
    import glob

    pattern = (word or "") + "*"
    matches = glob.glob(pattern)
    return [(m, "file") for m in matches]
