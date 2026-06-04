# The entry point: decide between the shell and one-shot mode (Section 5).
#
# With no command, Morvix drops into the interactive shell. With a command, it
# runs that one thing and exits - the path scripts, Makefiles and muscle-memory
# use. A handful of global flags (--debug, --no-color, -C dir, --version) may
# come before the command.

import os
import sys

from morvix import registry
from morvix.context import Context
from morvix.theme import make_console
from morvix.version import __version__

GLOBAL_HELP = """morvix - test-authoring, running and sharing for assignments

Usage:
  morvix                 start the interactive shell
  morvix <command> ...   run one command and exit

Global options:
  --debug                show tracebacks on internal errors
  --no-color, --plain    disable colored output
  -C, --dir DIR          act on DIR instead of the current directory
  --version, -V          print the version and exit

Type 'morvix help' for the full command list.
"""


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)

    debug = False
    plain = False
    root = os.getcwd()
    rest = []

    i = 0
    while i < len(raw):
        a = raw[i]
        if a == "--debug":
            debug = True
        elif a in ("--no-color", "--plain"):
            plain = True
        elif a in ("--version", "-V"):
            print(f"morvix {__version__}")
            return 0
        elif a in ("-C", "--dir"):
            i += 1
            if i >= len(raw):
                print("error: -C/--dir needs a directory", file=sys.stderr)
                return 2
            root = raw[i]
        elif a in ("-h", "--help") and not rest:
            print(GLOBAL_HELP)
            return 0
        else:
            rest = raw[i:]
            break
        i += 1

    console = make_console(force_plain=plain)
    interactive = (not rest) and sys.stdin.isatty() and sys.stdout.isatty()
    ctx = Context.create(os.path.abspath(root), interactive, console, debug)

    if not rest:
        from morvix.shell import run_shell
        return run_shell(ctx)
    return registry.safe_dispatch(ctx, rest)


if __name__ == "__main__":
    sys.exit(main())
