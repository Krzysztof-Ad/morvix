# import command: register a solution file as the code under test.
#
# --reference (default): point project.solution at the absolute path in place.
# --copy: copy the file into solutions/, freeze it inside the project tree.
# Auto-detects language from extension and updates project.language if unset.

import os
import shutil

from morvix.adapters import detect_language
from morvix.errors import UserError

NAME = "import"


def configure(parser):
    parser.add_argument("path", help="path to the solution file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--copy",
        action="store_true",
        default=False,
        help="copy the file into solutions/ (frozen snapshot)",
    )
    mode.add_argument(
        "--reference",
        action="store_true",
        default=False,
        help="keep the file in place and track its path (default)",
    )


def run(ctx, args) -> int:
    project = ctx.require_project()

    # Resolve path; must exist.
    src = os.path.abspath(args.path)
    if not os.path.isfile(src):
        raise UserError(
            f"File not found: {args.path}",
            hint="Check the path and try again.",
        )

    # Detect language from extension.
    lang = detect_language(src)
    if lang is None:
        ctx.messenger.warning(
            f"Could not detect language from '{os.path.basename(src)}'. "
            "Set it with 'config --language <lang>'."
        )
    elif lang != project.language:
        # - inform the user only when we're actually changing something
        if project.language:
            ctx.messenger.info(f"Language updated: {project.language} -> {lang}")
        project.language = lang

    if args.copy:
        # Copy into solutions/ inside the project tree.
        solutions_dir = os.path.join(project.root, "solutions")
        os.makedirs(solutions_dir, exist_ok=True)
        dest = os.path.join(solutions_dir, os.path.basename(src))
        shutil.copy2(src, dest)
        # Store relative path so the project stays portable.
        project.solution = os.path.relpath(dest, project.root)
        project.solution_copied = True
    else:
        # Reference in place.
        project.solution = src
        project.solution_copied = False

    ctx.save_project()

    lang_label = f" ({lang})" if lang else ""
    solution_label = os.path.basename(project.solution)
    mode_label = "copied to solutions/" if args.copy else "referenced"
    ctx.messenger.success(f"Solution set: {solution_label}{lang_label} — {mode_label}")
    return 0


def complete(ctx, prev_words, word):
    # Suggest filesystem paths near the partial word being typed.
    import glob

    pattern = (word or ".") + "*"
    matches = glob.glob(os.path.expanduser(pattern))
    results = []
    for m in sorted(matches):
        label = "dir" if os.path.isdir(m) else os.path.splitext(m)[1].lstrip(".") or "file"
        results.append((m + ("/" if os.path.isdir(m) else ""), label))
    return results
