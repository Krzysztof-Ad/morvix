# The user manual, generated from the single sources of truth (Section 5.5).
#
# This is the anti-drift trick: the command reference and the capability tables
# are GENERATED from help_text + the registries (the same data that drives the
# REPL and autocomplete), so they cannot fall out of sync with the tool. Only
# the conceptual fragments below are hand-written, and they are kept short -
# documentation.md is the deep design doc; this is the practical guide.
#
# `morvix docs` renders this in the terminal; `morvix docs --out GUIDE.md`
# writes the whole thing as Markdown; `morvix docs --check` fails if a committed
# GUIDE.md has gone stale (CI uses this).

from morvix import help_text, registry
from morvix.adapters import list_languages
from morvix.compare import list_strategies
from morvix.models import list_models
from morvix.shapes import list_shapes

# Conceptual sections - the only hand-written prose here. Keep them concise and
# practical; point at documentation.md for the full reasoning.
CONCEPTS = [
    ("overview", "What Morvix is", """\
Morvix builds, runs, and shares the self-made test harnesses students already
create by hand for programming assignments. You import your solution, generate
test cases, decide how outputs are judged, run them, and package the result so a
classmate can check their own code - even without Morvix installed.

It is honest by design: the "expected" answers come from one student's own
solution, so passing every test does **not** prove correctness - it proves
agreement with that one reference on the cases tried."""),

    ("roles", "Author and Receiver", """\
- **Author** - builds tests from their own solution and shares them. Their
  solution is the de-facto reference that defines the expected answers.
- **Receiver** - drops their own code into a received package and runs it.
  Without Morvix they just run `./run.sh`; with Morvix they get the rich view
  and can diff their results against the Author's."""),

    ("stages", "The four stages", """\
Work flows through four stages, and most commands belong to exactly one:

1. **Define** - language build/run settings, the solution, the execution model
   (`config`, `import`, `reference`, `model`).
2. **Generate** - produce inputs and compute expected answers (`gen`, `clean`).
3. **Run** - build and judge under limits, report (`run`, `runner`).
4. **Share** - assemble a report and a package (`result`, `package`)."""),

    ("axes", "The three independent axes", """\
Everything is the product of three orthogonal choices that never multiply
against each other:

- **Language adapter** - how source becomes runnable (C, C++, NASM, Python,
  Java, Rust). Adding a language is one adapter.
- **Execution model** - how the program is driven and what is observed
  (stdio, library, args, file, interactive).
- **Comparison strategy** - how pass/fail is decided (exact, whitespace, float,
  hash, checker, expected exit/crash - combinable per case)."""),

    ("generators", "Generators and structured input", """\
Random shapes (`gen --random`) suit simple stdin formats. Most real assignments
read something structured, where random data produces meaningless tests - Morvix
warns you when `gen --expected` comes back all-empty. The fix is a custom
generator:

    gen --new-generator mygen          # writes a starter you edit
    gen --generator .morvix/generators/mygen.py --count 1000
    gen --expected

A generator just prints one input to stdout, parameterized by a seed. Stress
testing (`gen --stress`) pits your solution against a trusted brute force and
saves the first disagreement."""),

    ("layout", "Where things live, and packages", """\
A project keeps all its state under a single hidden `.morvix/` directory, so
your project root stays clean. A **package** is flat instead: `run.sh`,
`README.md`, `morvix.json`, `tests/`, `expected/` and `runner/` sit at the
archive root so a Receiver sees the harness directly. Unpack it into an empty
folder and run `./run.sh <your-solution>` - only Python 3 is needed. Opening a
package with Morvix re-adopts it into a `.morvix/` project."""),

    ("honesty", "The honesty principle", """\
Expected answers are produced by one peer's solution, not an authority. Passing
all tests proves agreement, not correctness; the real signal is many independent
solutions agreeing. Every generated package README says so. Morvix never invents
an answer it cannot derive from a reference, and its suggestions explain and ask
rather than changing behavior silently."""),
]


def _md_options(name):
    """A Markdown bullet list of a command's options, generated from the parser."""
    opts = registry.options_for(name)
    lines = []
    for flag, helptext, choices in opts:
        suffix = ""
        if choices:
            suffix = "  (choices: %s)" % ", ".join(str(c) for c in choices)
        lines.append("- `%s` - %s%s" % (flag, helptext or "", suffix))
    return lines


def command_reference_md():
    """The full per-command reference, grouped by stage - generated."""
    out = ["## Command reference", ""]
    for stage_key, stage_label in help_text.STAGES:
        cmds = help_text.commands_in_stage(stage_key)
        if not cmds:
            continue
        out.append("### %s" % stage_label)
        out.append("")
        for name, _summary in cmds:
            info = help_text.COMMANDS.get(name, {})
            out.append("#### `%s`" % name)
            out.append("")
            out.append(info.get("long") or info.get("summary", ""))
            out.append("")
            opt_lines = _md_options(name)
            if opt_lines:
                out.append("Options:")
                out.append("")
                out.extend(opt_lines)
                out.append("")
            examples = info.get("examples") or []
            if examples:
                out.append("Examples:")
                out.append("")
                out.append("```")
                out.extend(examples)
                out.append("```")
                out.append("")
    return "\n".join(out).rstrip() + "\n"


def capabilities_md():
    """Live tables of what's supported - generated from the registries."""
    out = ["## What's supported", ""]
    out.append("- **Languages:** %s" % ", ".join(list_languages()))
    out.append("- **Execution models:** %s" % ", ".join(list_models()))
    out.append("- **Comparison strategies:** %s" % ", ".join(list_strategies()))
    out.append("- **Random shapes:** %s" % ", ".join(list_shapes()))
    out.append("")
    return "\n".join(out)


def concepts_md():
    out = []
    for _key, title, body in CONCEPTS:
        out.append("## %s" % title)
        out.append("")
        out.append(body)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def topic_md(topic):
    """One section by name: a concept key or a command name. None if unknown."""
    topic = help_text.ALIASES.get(topic, topic)
    for key, title, body in CONCEPTS:
        if key == topic:
            return "## %s\n\n%s\n" % (title, body)
    if topic in help_text.COMMANDS:
        info = help_text.COMMANDS[topic]
        parts = ["## `%s`" % topic, "", info.get("long", ""), ""]
        opt_lines = _md_options(topic)
        if opt_lines:
            parts += ["Options:", ""] + opt_lines + [""]
        if info.get("examples"):
            parts += ["Examples:", "", "```"] + info["examples"] + ["```", ""]
        return "\n".join(parts)
    return None


def topic_names():
    """Everything `docs <topic>` accepts: concept keys plus command names."""
    return [c[0] for c in CONCEPTS] + list(help_text.COMMANDS)


def full_markdown():
    """The entire manual as one Markdown document."""
    head = [
        "# Morvix - User Guide",
        "",
        "_Generated by `morvix docs`. Do not edit by hand - run "
        "`morvix docs --out GUIDE.md` to regenerate. CI fails if it is stale._",
        "",
    ]
    return "\n".join(head) + "\n" + concepts_md() + "\n" + capabilities_md() + "\n" + command_reference_md()


def overview_markdown():
    """A shorter terminal overview: concepts + capabilities + a command index."""
    out = ["# Morvix\n"]
    out.append(concepts_md())
    out.append(capabilities_md())
    out.append("## Commands\n")
    for stage_key, stage_label in help_text.STAGES:
        cmds = help_text.commands_in_stage(stage_key)
        if not cmds:
            continue
        out.append("**%s**" % stage_label)
        out.append("")
        for name, summary in cmds:
            out.append("- `%s` - %s" % (name, summary))
        out.append("")
    out.append("Use `docs <topic>` for a section, or `help <command>` for one command.")
    return "\n".join(out)
