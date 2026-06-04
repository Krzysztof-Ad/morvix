# Single-choice list (Section 6.2).
#
# Pick exactly one option. Used for archive format, comparison strategy, runner
# backend, execution model. Visually consistent with the selection list, minus
# the multi-toggle.
#
# API (implement in Workflow B):
#   choose(ctx, title: str, options: list[tuple[value, label]], default: int = 0) -> value
#       Returns the chosen value (the first element of the chosen tuple).
#       Non-interactive: returns options[default][0].


def choose(ctx, title, options, default=0):
    raise NotImplementedError
