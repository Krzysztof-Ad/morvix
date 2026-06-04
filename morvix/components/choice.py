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
    # Non-interactive: skip the dialog and return the default immediately.
    if not ctx.interactive:
        return options[default][0]

    from prompt_toolkit.shortcuts import radiolist_dialog

    # Build (value, label) pairs that prompt_toolkit expects.
    pt_values = [(value, label) for value, label in options]

    result = radiolist_dialog(
        title=title,
        text="Use arrow keys to select, then press Enter.",
        values=pt_values,
        default=pt_values[default][0],
    ).run()

    # Cancel (Ctrl-C / Escape) returns None; fall back to default.
    if result is None:
        return options[default][0]
    return result
