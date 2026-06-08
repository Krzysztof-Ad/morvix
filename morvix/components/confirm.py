# Confirmation prompt (Section 6.4).
#
# A clear yes/no used for destructive actions and the smart suggestions of
# Section 22. The default is shown explicitly and chosen safely. In a
# non-interactive run there is no one to ask, so it returns the default.


def confirm(ctx, question, default=False):
    # Non-interactive: nobody is watching, just use the default.
    if not ctx.interactive:
        ctx.messenger.info(question)
        return default

    # Build the [Y/n] / [y/N] hint so the user sees which way the default falls.
    hint = "[Y/n]" if default else "[y/N]"
    prompt_text = f"{question} {hint} "

    while True:
        try:
            try:
                from prompt_toolkit import prompt as pt_prompt

                raw = pt_prompt(prompt_text)
            except ImportError:
                raw = input(prompt_text)
        except (EOFError, KeyboardInterrupt):
            return default

        answer = raw.strip().lower()

        if answer == "":
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False

        # Unrecognised input — ask again.
        ctx.messenger.warning("Please answer y or n.")
