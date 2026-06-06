# Build the shareable archive (Section 19).
#
# Bundles tests, expected answers, the runner, README and manifest into one
# archive - and deliberately leaves out the solution source and brute-force
# reference. The author picks the format and, optionally, which runners and
# groups to include; before building we estimate the size and may suggest
# stronger compression.


from morvix import packaging, suggestions
from morvix.components.choice import choose
from morvix.components.selection import select

NAME = "package"

# Format flag -> internal format name understood by packaging.build_package.
_FORMATS = [
    ("--zip", "zip"),
    ("--tar", "tar"),
    ("--tar.gz", "tar.gz"),
    ("--tar.xz", "tar.xz"),
]


def configure(parser):
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--zip", action="store_true", help="ZIP archive (default)")
    fmt.add_argument("--tar", action="store_true", help="uncompressed tar archive")
    fmt.add_argument("--tar.gz", dest="tar_gz", action="store_true", help="gzip-compressed tar")
    fmt.add_argument(
        "--tar.xz", dest="tar_xz", action="store_true", help="xz-compressed tar (smallest)"
    )

    parser.add_argument(
        "--include-generators", action="store_true", help="also bundle the generators/ directory"
    )
    parser.add_argument(
        "--runner", action="append", metavar="NAME", help="only include this runner (repeatable)"
    )
    parser.add_argument(
        "--rivals",
        choices=["precomputed", "code", "none"],
        default="precomputed",
        help="ship rival comparison data: precomputed numbers (default, code-free), "
        "the rival code (leaks code), or nothing",
    )
    parser.add_argument("--out", metavar="PATH", help="output archive path")


# Map the parsed flags back to a format name; defaults to zip.
def _fmt_from_args(args):
    if getattr(args, "tar_gz", False):
        return "tar.gz"
    if getattr(args, "tar_xz", False):
        return "tar.xz"
    if args.tar:
        return "tar"
    return "zip"


def run(ctx, args):
    project = ctx.require_project()

    fmt = _fmt_from_args(args)
    runners = args.runner or None

    # In interactive mode let the author pick the format and narrow contents.
    if ctx.interactive and not _any_format_flag(args) and not runners:
        fmt = choose(
            ctx,
            "Archive format",
            [
                ("zip", "zip - widely supported (default)"),
                ("tar.gz", "tar.gz - smaller"),
                ("tar.xz", "tar.xz - smallest"),
                ("tar", "tar - uncompressed"),
            ],
            default=0,
        )

        # Offer to restrict which runners go in the package.
        if project.runners:
            items = [(n, n, "runners") for n in sorted(project.runners)]
            picked = select(ctx, "Runners to include (all selected = include every runner)", items)
            # Only narrow if the author actually deselected something.
            if picked and len(picked) < len(items):
                runners = picked

    # Suggest stronger compression only when the chosen format is weaker than
    # tar.xz and we are in an interactive session (non-interactive runs cannot
    # answer a confirmation prompt, and tar.xz is already the strongest).
    if ctx.interactive and fmt != "tar.xz":
        size = packaging.estimate_size(project)
        suggested = suggestions.suggest_compression(ctx, project, size)
        if suggested:
            fmt = suggested

    # Shipping rival CODE leaks working solutions, so confirm it explicitly.
    rivals_mode = args.rivals
    if rivals_mode == "code" and project.rivals:
        from morvix.components.confirm import confirm

        ctx.messenger.warning(
            "Shipping rival CODE includes those solution files in the package.",
            hint="That can hand classmates working solutions. Precomputed numbers stay code-free.",
        )
        if not confirm(ctx, "Ship the rival source code anyway?", default=False):
            rivals_mode = "precomputed"

    out = packaging.build_package(
        ctx,
        project,
        fmt=fmt,
        runners=runners,
        include_generators=args.include_generators,
        out=args.out,
        rivals_mode=rivals_mode,
    )

    ctx.messenger.success(f"Package written to {out}")
    ctx.messenger.info("It contains tests, expected answers, the runner, README and manifest.")
    ctx.messenger.info("Your solution source is NOT included - share it separately if you want to.")
    return 0


def _any_format_flag(args):
    return bool(
        args.zip or args.tar or getattr(args, "tar_gz", False) or getattr(args, "tar_xz", False)
    )


# --runner suggests the project's runner names.
def complete(ctx, prev_words, word):
    if prev_words and prev_words[-1] == "--runner":
        project = ctx.project
        if not project:
            return []
        return [(name, "runner") for name in sorted(project.runners) if name.startswith(word)]
    return []
