# The launch banner (Section 5.2).
#
# An ASCII identity block with the name, the attribution, the version and a
# one-line hint - the first thing a user sees in the interactive shell.

from rich.console import Console

from morvix.version import AUTHOR, __version__

ART = r"""
 __  __  ___  ____ __     __ ___ __  __
|  \/  |/ _ \|  _ \\ \   / /|_ _|\ \/ /
| |\/| | | | | |_) |\ \ / /  | |  \  /
| |  | | |_| |  _ <  \ V /   | |  /  \
|_|  |_|\___/|_| \_\  \_/   |___|/_/\_\
"""


def print_banner(console: Console) -> None:
    console.print(ART, style="accent")
    console.print(f"  by {AUTHOR}    v{__version__}", style="muted")
    console.print("  type [accent]help[/accent] to begin\n", style="muted")
