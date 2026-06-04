# Help command: list all commands grouped by stage, or explain one in detail.
#
# With no topic, prints every command grouped by pipeline stage.
# With a topic, prints the long description, stage, examples, and options.

from rich.text import Text

from morvix import help_text, registry
from morvix.errors import UserError

NAME = "help"


def configure(parser):
    parser.add_argument("topic", nargs="?", default=None, help="command name to explain")


def run(ctx, args) -> int:
    topic = args.topic

    if topic is None:
        _print_all(ctx)
    else:
        # Resolve alias (quit -> exit), then look up.
        resolved = help_text.ALIASES.get(topic, topic)
        info = help_text.COMMANDS.get(resolved)
        if info is None:
            raise UserError(
                f"Unknown command: {topic!r}",
                hint="Type 'help' for a list of all commands.",
            )
        _print_topic(ctx, resolved, info)

    return 0


def _print_all(ctx):
    # Find the longest command name for alignment.
    all_names = list(help_text.COMMANDS.keys())
    width = max(len(n) for n in all_names)

    for stage_key, stage_label in help_text.STAGES:
        cmds = help_text.commands_in_stage(stage_key)
        if not cmds:
            continue
        ctx.console.print()
        ctx.console.print(Text(stage_label, style="accent"))
        for name, summary in cmds:
            # "  name   summary" — name padded, muted summary
            line = Text()
            line.append(f"  {name:<{width}}  ", style="heading")
            line.append(summary, style="muted")
            ctx.console.print(line)

    ctx.console.print()
    ctx.console.print(Text("  Type 'help <command>' for details.", style="muted"))


def _print_topic(ctx, name, info):
    stage_key = info.get("stage", "")
    # Find stage label for this key.
    stage_label = next((lbl for k, lbl in help_text.STAGES if k == stage_key), stage_key)

    ctx.console.print()
    ctx.console.print(Text(name, style="accent"))
    ctx.console.print(Text(f"  Stage: {stage_label}", style="muted"))
    ctx.console.print()

    long_desc = info.get("long", "")
    if long_desc:
        ctx.console.print(Text(f"  {long_desc}"))
        ctx.console.print()

    examples = info.get("examples", [])
    if examples:
        ctx.console.print(Text("  Examples:", style="heading"))
        for ex in examples:
            ctx.console.print(Text(f"    morvix {ex}", style="info"))
        ctx.console.print()

    options = registry.options_for(name)
    if options:
        ctx.console.print(Text("  Options:", style="heading"))
        # Pad flags to align help text.
        flag_width = max(len(flag) for flag, _, _ in options)
        for flag, help_str, choices in options:
            line = Text()
            line.append(f"    {flag:<{flag_width}}  ", style="success")
            line.append(help_str or "", style="muted")
            if choices:
                line.append(f"  [{', '.join(str(c) for c in choices)}]", style="muted")
            ctx.console.print(line)
        ctx.console.print()


def complete(ctx, prev_words, word):
    # Suggest command names (and aliases) filtered by the partial word.
    names = registry.command_names()
    return [(n, help_text.summary(n)) for n in names if n.startswith(word)]
