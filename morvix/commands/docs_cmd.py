# docs command - the full user guide, generated from the single sources.
#
#   docs                 render the overview in the terminal
#   docs <topic|command> render one section
#   docs --out FILE      write the whole manual as Markdown
#   docs --markdown      print the whole manual as Markdown to stdout
#   docs --check [FILE]  regenerate and fail if FILE (default GUIDE.md) is stale
#
# Because the content is generated from help_text and the registries, it cannot
# drift from what the tool actually does. CI runs `docs --check` to keep the
# committed GUIDE.md fresh.

import os

from morvix import docs
from morvix.errors import UserError

NAME = "docs"

DEFAULT_GUIDE = "GUIDE.md"


def configure(parser):
    parser.add_argument(
        "topic", nargs="?", help="a topic or command name to show (omit for the overview)"
    )
    parser.add_argument("--out", metavar="FILE", help="write the full manual as Markdown to FILE")
    parser.add_argument(
        "--markdown", action="store_true", help="print the full manual as Markdown to stdout"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the Markdown manual (default GUIDE.md) is out of date",
    )


def run(ctx, args) -> int:
    if args.check:
        return _check(ctx, args.out or DEFAULT_GUIDE)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(docs.full_markdown())
        ctx.messenger.success(f"Wrote the user guide to {args.out}.")
        return 0

    if args.markdown:
        ctx.console.print(docs.full_markdown(), markup=False, highlight=False)
        return 0

    if args.topic:
        section = docs.topic_md(args.topic)
        if section is None:
            known = ", ".join(sorted(docs.topic_names()))
            raise UserError(f"No docs topic '{args.topic}'.", hint=f"Try one of: {known}")
        _render(ctx, section)
        return 0

    _render(ctx, docs.overview_markdown())
    return 0


def _check(ctx, path):
    generated = docs.full_markdown()
    if not os.path.exists(path):
        raise UserError(
            f"{path} does not exist.", hint=f"Generate it with: morvix docs --out {path}"
        )
    with open(path, "r", encoding="utf-8") as f:
        current = f.read()
    if current == generated:
        ctx.messenger.success(f"{path} is up to date.")
        return 0
    ctx.messenger.error(
        f"{path} is out of date.", hint=f"Regenerate it with: morvix docs --out {path}"
    )
    return 1


def _render(ctx, markdown_text):
    # Render Markdown nicely when we have a real terminal; otherwise print plain.
    if ctx.interactive:
        try:
            from rich.markdown import Markdown

            ctx.console.print(Markdown(markdown_text))
            return
        except Exception:
            pass
    ctx.console.print(markdown_text, markup=False, highlight=False)


def complete(ctx, prev_words, word):
    return [(t, "topic") for t in docs.topic_names() if t.startswith(word or "")]
