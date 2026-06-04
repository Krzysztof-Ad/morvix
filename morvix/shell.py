# Interactive shell (REPL).
#
# NOTE: this is the plain fallback loop. The rich prompt_toolkit shell - live
# autocomplete with inline descriptions, history, the status toolbar - is built
# on top of this contract: print the banner, then read lines and hand each to
# registry.safe_dispatch_line until the user exits.

from morvix import registry
from morvix.banner import print_banner
from morvix.context import Context


def run_shell(ctx: Context) -> int:
    print_banner(ctx.console)
    while True:
        try:
            line = input("morvix > ")
        except (EOFError, KeyboardInterrupt):
            ctx.console.print()
            return 0
        if line.strip() in ("exit", "quit"):
            return 0
        registry.safe_dispatch_line(ctx, line)
