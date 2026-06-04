# init command - create a new Morvix project in this directory (Section 24).
#
# A project IS its directory, so init just lays out the skeleton and writes the
# config. Interactively it opens a guided form (pre-filled from your global
# defaults); one-shot it takes the flags and falls back to built-in defaults.
# If a project already lives here it refuses to clobber it.

import os

from morvix import layout
from morvix.adapters import list_languages
from morvix.components.form import Field, run_form
from morvix.compare import list_strategies
from morvix.models import list_models
from morvix.project import DEFAULT_COMPARE, DEFAULT_LIMITS, Project

NAME = "init"


def configure(parser):
    parser.add_argument("--name", help="project name (defaults to this directory's name)")
    parser.add_argument("--model", choices=list_models(), help="execution model")
    parser.add_argument("--language", choices=list_languages(), help="default language")
    parser.add_argument("--compare", choices=list_strategies(), help="default comparison strategy")
    parser.add_argument("--wall", type=float, help="default wall-clock limit in seconds")


def run(ctx, args) -> int:
    # A project here already - don't overwrite it.
    if layout.is_project(ctx.root):
        ctx.messenger.warning(
            "A Morvix project already exists here.",
            hint="Use 'config' or 'model' to change its settings.",
        )
        return 0

    g = ctx.global_config

    # Defaults: flag > global default > built-in.
    name = args.name or os.path.basename(os.path.abspath(ctx.root))
    languages = list_languages()
    models = list_models()
    strategies = list_strategies()

    language = args.language or g.get("language")
    model = args.model or g.get("model") or "stdio"
    compare = args.compare or g.get("compare") or DEFAULT_COMPARE["strategy"]
    wall = args.wall if args.wall is not None else g.get("wall", DEFAULT_LIMITS["wall"])

    if ctx.interactive:
        # Language choices include a blank "decide later" option.
        lang_choices = [("", "(decide later)")] + [(l, l) for l in languages]
        fields = [
            Field("name", "Project name", "text", default=name, required=True,
                  help="A short label for this assignment."),
            Field("language", "Language", "choice", choices=lang_choices,
                  default=language or "", help="Default language for build/run."),
            Field("model", "Execution model", "choice",
                  choices=[(m, m) for m in models], default=model,
                  help="How the solution is invoked and what is judged."),
            Field("compare", "Comparison", "choice",
                  choices=[(s, s) for s in strategies], default=compare,
                  help="How output is checked for correctness."),
            Field("wall", "Wall-clock limit (s)", "int", default=int(wall),
                  help="Default per-case time limit in seconds."),
        ]
        answers = run_form(ctx, "New Morvix project", fields)
        if answers is None:
            ctx.messenger.info("Cancelled.")
            return 0
        name = answers["name"]
        language = answers["language"] or None
        model = answers["model"]
        compare = answers["compare"]
        wall = answers["wall"]

    # Lay down the directory and apply the chosen settings.
    project = Project.create(ctx.root, name)
    project.model = model
    project.language = language
    project.compare["strategy"] = compare
    project.limits["wall"] = float(wall)

    ctx.project = project
    ctx.save_project()

    ctx.messenger.success(f"Created project '{name}'.")
    _next_steps(ctx, language)
    return 0


# Print a short, friendly hint of what to do next.
def _next_steps(ctx, language):
    lang_hint = language or "<language>"
    ctx.messenger.plain()
    ctx.messenger.heading("Next steps")
    ctx.messenger.info(f"config {lang_hint}   configure how the language builds and runs")
    ctx.messenger.info("import <solution>   bring in the solution to test")
    ctx.messenger.info("gen                 create test cases")
    ctx.messenger.info("run                 judge the solution")


def complete(ctx, prev_words, word):
    prev = prev_words[-1] if prev_words else ""
    if prev == "--language":
        return [(l, "language") for l in list_languages()]
    if prev == "--model":
        return [(m, "model") for m in list_models()]
    if prev == "--compare":
        return [(s, "compare strategy") for s in list_strategies()]
    return []
