# reference command: register the solution that defines expected answers.
#
# Sets project.reference to an absolute path, detects the language, and
# saves the project. The reference is not copied in - it is referenced in
# place so edits to it are immediately reflected when regenerating expected
# outputs.

import glob
import os

from morvix.adapters import detect_language
from morvix.errors import UserError

NAME = "reference"


def configure(parser):
    parser.add_argument("path", help="path to the reference solution file")


def run(ctx, args) -> int:
    project = ctx.require_project()

    path = os.path.abspath(args.path)
    if not os.path.isfile(path):
        raise UserError(
            f"File not found: {args.path}",
            hint="Check the path and try again.",
        )

    project.reference = path

    # Detect and note the language from the extension.
    lang = detect_language(path)
    if lang:
        ctx.messenger.info(f"Detected language: {lang}")

    ctx.save_project()

    ctx.messenger.success(
        f"Reference set to {os.path.relpath(path, project.root)}"
    )
    ctx.messenger.info(
        "The reference defines the expected answers - "
        "run 'gen --expected' to regenerate them from it."
    )
    return 0


def complete(ctx, prev_words, word):
    # Suggest files matching the current partial word.
    pattern = (word or "") + "*"
    matches = glob.glob(pattern)
    result = []
    for m in matches:
        if os.path.isdir(m):
            result.append((m + "/", "directory"))
        else:
            result.append((m, "file"))
    return result
