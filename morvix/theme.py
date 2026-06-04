# Colors, glyphs and styles, in one place.
#
# Every bit of output - messages, tables, the prompt, the banner - pulls its
# look from here, so the tool feels like one thing and there is a single place
# to retune the palette. rich and prompt_toolkit each want their own format, so
# we expose both from the same definitions.

import os
import sys

from rich.console import Console
from rich.theme import Theme

# Named roles used across the whole UI. Keeping them named (rather than raw
# colors at call sites) means a command says style="error", not style="red".
ROLE_COLORS = {
    "error": "bold red",
    "warning": "yellow",
    "success": "bold green",
    "info": "cyan",
    "muted": "dim",
    "accent": "bold magenta",
    "heading": "bold",
    "pass": "green",
    "fail": "red",
    "skip": "dim",
}

# Single-character markers that lead a line so its kind is obvious at a glance.
GLYPHS = {
    "error": "x",
    "warning": "!",
    "success": "+",
    "info": "-",
    "pass": "+",
    "fail": "x",
    "prompt": "❯",  # the heavy right angle: morvix >
    "bullet": "•",
}

PROMPT = f"morvix {GLYPHS['prompt']} "

_RICH_THEME = Theme(ROLE_COLORS)


def color_enabled() -> bool:
    """Color on for a real terminal, off when piped or NO_COLOR is set."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("MORVIX_NO_COLOR"):
        return False
    return sys.stdout.isatty()


def make_console(force_plain: bool = False) -> Console:
    """Build the shared rich Console used for all output."""
    plain = force_plain or not color_enabled()
    return Console(theme=_RICH_THEME, no_color=plain, highlight=False, soft_wrap=False)


# prompt_toolkit wants its own style table; mirror the roles that the shell and
# its components use.
PROMPT_TOOLKIT_STYLE = {
    "prompt": "bold",
    "completion-menu.completion": "bg:#1c1c1c #d0d0d0",
    "completion-menu.completion.current": "bg:#5f00af #ffffff",
    "completion-menu.meta.completion": "bg:#1c1c1c #808080",
    "completion-menu.meta.completion.current": "bg:#5f00af #d7d7d7",
    "bottom-toolbar": "bg:#222222 #aaaaaa",
    "error": "fg:red bold",
    "warning": "fg:yellow",
    "success": "fg:green bold",
    "selected": "reverse",
    "cursor": "reverse",
}
