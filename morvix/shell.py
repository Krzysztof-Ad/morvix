# Interactive shell (REPL) - Sections 5 and 6.
#
# A prompt_toolkit shell on top of the registry contract: print the banner, then
# read lines and hand each to registry.safe_dispatch_line until the user exits.
# What makes it feel polished:
#   - live, context-aware autocomplete with inline descriptions (command/option
#     on the left, summary on the right)
#   - persistent history across sessions
#   - a bottom toolbar showing the project, the solution under test and counts
# If prompt_toolkit cannot start (no real terminal, piped input) we fall back to
# a plain input() loop that still dispatches every line.

import os
import shlex
import sys

from prompt_toolkit.completion import Completer, Completion

from morvix import registry
from morvix import theme
from morvix.banner import print_banner
from morvix.context import Context

HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".morvix_history")


def run_shell(ctx: Context) -> int:
    print_banner(ctx.console)
    # Only drive a full prompt_toolkit session on a real terminal; piped or dumb
    # input goes straight to the plain loop (no toolbar warnings, clean output).
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return _fallback_loop(ctx)
    try:
        session = _build_session(ctx)
    except Exception:
        return _fallback_loop(ctx)
    return _prompt_loop(ctx, session)


def _build_session(ctx: Context):
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style

    session = PromptSession(
        completer=MorvixCompleter(ctx),
        complete_while_typing=True,
        history=FileHistory(HISTORY_PATH),
        style=Style.from_dict(theme.PROMPT_TOOLKIT_STYLE),
        bottom_toolbar=lambda: _toolbar(ctx),
    )
    # A small debounce keeps live typing snappy without redrawing on every key.
    try:
        session.app.min_redraw_interval = 0.05
    except Exception:
        pass
    return session


def _prompt_loop(ctx: Context, session) -> int:
    while True:
        try:
            line = session.prompt(theme.PROMPT)
        except EOFError:
            # Ctrl-D at the prompt: exit cleanly.
            ctx.console.print()
            return 0
        except KeyboardInterrupt:
            # Ctrl-C cancels the current line and keeps going.
            continue
        if not line.strip():
            continue
        registry.safe_dispatch_line(ctx, line)
        if ctx.should_exit:
            return 0


def _fallback_loop(ctx: Context) -> int:
    """Plain loop for when prompt_toolkit is unavailable (pipes, dumb terminals)."""
    while True:
        try:
            line = input(theme.PROMPT)
        except EOFError:
            ctx.console.print()
            return 0
        except KeyboardInterrupt:
            ctx.console.print()
            continue
        if not line.strip():
            continue
        registry.safe_dispatch_line(ctx, line)
        if ctx.should_exit:
            return 0


def _toolbar(ctx: Context) -> str:
    """Live status line (Section 5.6): project, solution and case/runner counts.

    Re-read from ctx.project on every render so it tracks the session state.
    """
    project = ctx.project
    if project is None:
        return " no project   type 'init' to create one "
    name = project.name or "project"
    solution = project.solution or "no solution"
    cases = len(project.cases)
    runners = len(project.runners)
    bits = [f" {name}", f"solution: {solution}", f"{cases} cases", f"{runners} runners"]
    if ctx.recorder is not None:
        bits.append("(recording)")
    return "   ".join(bits) + " "


class MorvixCompleter(Completer):
    """Context-aware completer (Section 5.4).

    The left column is the command or flag; the right column (display_meta) is
    its short description. We parse the text before the cursor with shlex and
    only suggest items that match the word currently under the cursor.
    """

    def __init__(self, ctx: Context):
        self.ctx = ctx

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words, word = _split(text)

        # Completing the first word: suggest commands, summary on the right.
        if not words:
            for name, summary in registry.all_commands():
                if name.startswith(word):
                    yield Completion(
                        name,
                        start_position=-len(word),
                        display=name,
                        display_meta=_short(summary),
                    )
            return

        name = words[0]
        prev_words = words[1:]

        # Completing a flag: suggest this command's options, help on the right.
        if word.startswith("-"):
            for flag, help_str, _choices in registry.options_for(name):
                if flag.startswith(word):
                    yield Completion(
                        flag,
                        start_position=-len(word),
                        display=flag,
                        display_meta=_short(help_str),
                    )
            return

        # Otherwise ask the command for value suggestions (files, names, enums).
        for item in registry.complete_values(self.ctx, name, prev_words, word):
            value, meta = item if isinstance(item, tuple) else (item, "")
            value = str(value)
            if value.startswith(word):
                yield Completion(
                    value,
                    start_position=-len(word),
                    display=value,
                    display_meta=_short(meta),
                )


def _split(text):
    """Tokenize the text before the cursor, tolerant of unbalanced quotes.

    Returns (completed_words, current_word). The current word is whatever is
    being typed after the last space; an empty string means a fresh token.
    """
    ends_in_space = text[-1:].isspace()
    try:
        tokens = shlex.split(text)
    except ValueError:
        # Unbalanced quote: close it and retry so we can still complete the tail.
        try:
            tokens = shlex.split(text + '"')
        except ValueError:
            tokens = text.split()
    if not tokens:
        return [], ""
    if ends_in_space:
        return tokens, ""
    return tokens[:-1], tokens[-1]


def _short(s, limit=60):
    """Keep menu descriptions to one short line."""
    if not s:
        return ""
    s = s.strip().splitlines()[0] if s.strip() else ""
    return (s[: limit - 1] + "…") if len(s) > limit else s
