# model command - set the execution model for the current project.
#
# Models: stdio (stdin->stdout), library (link & assert), args (argv),
#         file (file in/out), interactive (converses with a judge).

from morvix.components.choice import choose
from morvix.errors import UserError
from morvix.models import list_models

NAME = "model"

# Short descriptions shown in the interactive picker
_DESCRIPTIONS = {
    "stdio": "stdin -> stdout",
    "library": "link & assert",
    "args": "argv in / stdout out",
    "file": "file in / file out",
    "interactive": "converses with a judge",
}


def configure(parser):
    models = list_models()
    parser.add_argument(
        "model",
        nargs="?",
        choices=models,
        help="execution model to use: " + ", ".join(models),
    )


def run(ctx, args) -> int:
    project = ctx.require_project()
    models = list_models()

    model = getattr(args, "model", None)

    if model is None:
        if not ctx.interactive:
            raise UserError(
                "No model specified.",
                hint="Pass one of: " + ", ".join(models),
            )
        choices = [(m, m + " - " + _DESCRIPTIONS.get(m, "")) for m in models]
        default_idx = models.index(project.model) if project.model in models else 0
        model = choose(ctx, "Execution model", choices, default=default_idx)

    project.model = model
    ctx.save_project()
    ctx.messenger.success(f"Execution model set to '{model}'.")
    return 0


def complete(ctx, prev_words, word):
    # - suggest model names
    return [(m, _DESCRIPTIONS.get(m, "")) for m in list_models()]
