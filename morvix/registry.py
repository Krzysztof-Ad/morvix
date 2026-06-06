# The command registry: one parser, two entry points (Section 5.1).
#
# Every command is a small module under morvix/commands/. Each exposes:
#   NAME              the verb, e.g. "gen"
#   configure(parser) add its arguments to an argparse subparser
#   run(ctx, args)    do the work, return an exit code
#   complete(ctx, prev_words, word)   (optional) suggest values for autocomplete
#
# The same parser serves the REPL (parse a typed line) and one-shot mode (parse
# sys.argv), so there is no separate "REPL language" to maintain. Parse errors
# raise instead of killing the process, so the shell can show them cleanly and
# keep going.

import argparse
import importlib
import shlex
from typing import Dict, List, Optional, Tuple

from morvix import help_text
from morvix.context import Context
from morvix.errors import MorvixError, UserError

# The command modules, in the order help should list them within each stage.
COMMAND_MODULES = [
    "init_cmd", "open_cmd", "status_cmd", "help_cmd", "docs_cmd", "exit_cmd",
    "config_cmd", "import_cmd", "rival_cmd", "model_cmd",
    "gen_cmd", "clean_cmd",
    "run_cmd", "runner_cmd",
    "result_cmd", "package_cmd",
    "workflow_cmd",
]


class _Exit(Exception):
    """Raised instead of sys.exit so the REPL survives -h and parse errors."""

    def __init__(self, code: int):
        self.code = code


class ShellArgumentParser(argparse.ArgumentParser):
    """An argparse parser that reports errors as messages, never exits."""

    def error(self, message):
        # self.prog is "morvix" at the top level and "morvix <cmd>" for a
        # subparser; only point at a real subcommand.
        parts = self.prog.split()
        sub = parts[1] if len(parts) > 1 else None
        hint = f"Try 'help {sub}'." if sub else "Type 'help' to see commands."
        raise UserError(message, hint=hint)

    def exit(self, status=0, message=None):
        if message:
            # -h prints help to stdout via print_help, not here; this is rare.
            pass
        raise _Exit(status)


_parser: Optional[ShellArgumentParser] = None
_modules: Dict[str, object] = {}
_subparsers: Dict[str, argparse.ArgumentParser] = {}


def _build() -> None:
    global _parser
    if _parser is not None:
        return
    _parser = ShellArgumentParser(prog="morvix", add_help=False)
    sub = _parser.add_subparsers(dest="_command", metavar="command")
    for mod_name in COMMAND_MODULES:
        mod = importlib.import_module(f"morvix.commands.{mod_name}")
        info = help_text.COMMANDS.get(mod.NAME, {})
        p = sub.add_parser(
            mod.NAME,
            help=info.get("summary", ""),
            description=info.get("long", ""),
            add_help=True,
        )
        mod.configure(p)
        _modules[mod.NAME] = mod
        _subparsers[mod.NAME] = p


def dispatch(ctx: Context, argv: List[str]) -> int:
    """Parse one command line and run it. Returns an exit code."""
    _build()
    if not argv:
        return 0
    # Resolve aliases (quit -> exit) on the leading verb.
    if argv[0] in help_text.ALIASES:
        argv = [help_text.ALIASES[argv[0]]] + argv[1:]
    try:
        args = _parser.parse_args(argv)
    except _Exit as e:
        return e.code
    name = getattr(args, "_command", None)
    if not name:
        ctx.messenger.error("No command given.", hint="Type 'help' to see commands.")
        return 2
    # Record into a workflow if one is being captured (Section 18.3).
    if name not in ("workflow", "help", "status", "exit", "open"):
        ctx.record(" ".join(shlex.quote(a) for a in argv))
    return _modules[name].run(ctx, args) or 0


def safe_dispatch(ctx: Context, argv: List[str]) -> int:
    """Dispatch with the top-level error handling from Section 7.

    Known errors become clean messages; only --debug shows a traceback. This is
    used by both the one-shot path and the REPL so they behave identically.
    """
    try:
        return dispatch(ctx, argv)
    except MorvixError as e:
        ctx.messenger.error(e.message, e.hint)
        return 1
    except KeyboardInterrupt:
        ctx.messenger.warning("Interrupted.")
        return 130
    except Exception as e:  # noqa: BLE001 - last line of defence, never dump a traceback
        if ctx.debug:
            raise
        ctx.messenger.error(f"internal error: {e}", hint="Run with --debug for the traceback.")
        return 1


def safe_dispatch_line(ctx: Context, line: str) -> int:
    try:
        argv = shlex.split(line.strip())
    except ValueError as e:
        ctx.messenger.error(f"Could not parse the line: {e}")
        return 2
    return safe_dispatch(ctx, argv)


# --- introspection for help and autocomplete ---

def all_commands() -> List[Tuple[str, str]]:
    _build()
    return [(name, help_text.summary(name)) for name in _modules]


def command_names() -> List[str]:
    _build()
    return list(_modules) + list(help_text.ALIASES)


def get_module(name: str):
    _build()
    name = help_text.ALIASES.get(name, name)
    return _modules.get(name)


def options_for(name: str) -> List[Tuple[str, str, Optional[list]]]:
    """The (flag, help, choices) of a command's options, for autocomplete."""
    _build()
    name = help_text.ALIASES.get(name, name)
    parser = _subparsers.get(name)
    if parser is None:
        return []
    out = []
    for action in parser._actions:
        for flag in action.option_strings:
            if flag in ("-h", "--help"):
                continue
            out.append((flag, action.help or "", list(action.choices) if action.choices else None))
    return out


def arguments(name: str):
    """Structured argument info for the docs, introspected from the parser.

    Returns (positionals, options):
      positionals: [{name, choices, help}]
      options:     [{names, metavar, choices, help, takes_value}]
    """
    _build()
    name = help_text.ALIASES.get(name, name)
    parser = _subparsers.get(name)
    if parser is None:
        return [], []
    positionals, options = [], []
    for action in parser._actions:
        if action.dest == "help":
            continue
        choices = list(action.choices) if action.choices else None
        if action.option_strings:
            # store_true/false/const and count take no value; everything else does.
            takes_value = not isinstance(
                action, (argparse._StoreConstAction, argparse._CountAction))
            metavar = action.metavar or (action.dest.upper() if takes_value else None)
            options.append({"names": list(action.option_strings), "metavar": metavar,
                            "choices": choices, "help": action.help or "",
                            "takes_value": takes_value})
        else:
            positionals.append({"name": action.metavar or action.dest,
                                "choices": choices, "help": action.help or ""})
    return positionals, options


def complete_values(ctx: Context, name: str, prev_words: List[str], word: str):
    """Ask a command for value suggestions, if it offers any."""
    mod = get_module(name)
    if mod is not None and hasattr(mod, "complete"):
        try:
            return mod.complete(ctx, prev_words, word)
        except Exception:
            return []
    return []
