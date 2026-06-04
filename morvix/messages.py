# The one path all messages flow through (Section 6.7, Section 7).
#
# Errors, warnings, successes and info all render here, so a warning always
# looks like a warning everywhere and there is one place to change how any of
# them look. Commands never print colored text by hand; they call a Messenger.

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from morvix.theme import GLYPHS


class Messenger:
    """Thin wrapper over a rich Console with the four message kinds."""

    def __init__(self, console: Console):
        self.console = console

    def _line(self, role: str, text: str):
        marker = GLYPHS.get(role, "-")
        self.console.print(Text.assemble((f"{marker} ", role), (text, role if role in ("error", "success") else "")))

    def error(self, message: str, hint: Optional[str] = None):
        # What failed, then (when we have one) the fix, on its own indented line.
        self.console.print(Text.assemble((f"{GLYPHS['error']} ", "error"), (message, "error")))
        if hint:
            self.console.print(Text(f"  {hint}", style="muted"))

    def warning(self, message: str, hint: Optional[str] = None):
        self.console.print(Text.assemble((f"{GLYPHS['warning']} ", "warning"), (message, "warning")))
        if hint:
            self.console.print(Text(f"  {hint}", style="muted"))

    def success(self, message: str):
        self.console.print(Text.assemble((f"{GLYPHS['success']} ", "success"), (message, "success")))

    def info(self, message: str):
        self.console.print(Text.assemble((f"{GLYPHS['info']} ", "muted"), (message,)))

    def plain(self, message: str = ""):
        self.console.print(message)

    def heading(self, message: str):
        self.console.print(Text(message, style="heading"))

    def diagnostics(self, build_command: str, output: str):
        """Show a toolchain's own output verbatim (Section 7.1).

        The compiler/assembler/linker message is exactly what the student needs,
        so we show it unmodified, just framed by which command produced it.
        """
        body = Text(output.rstrip("\n") or "(no output)")
        title = Text(f"build failed: {build_command}", style="error")
        self.console.print(Panel(body, title=title, border_style="error", title_align="left"))
