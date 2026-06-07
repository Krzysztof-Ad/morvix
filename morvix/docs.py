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
    (
        "overview",
        "What Morvix is",
        """\
Morvix builds, runs, and shares the self-made test harnesses students already
create by hand for programming assignments. You import your solution, generate
test cases, decide how outputs are judged, run them, and package the result so a
classmate can check their own code - even without Morvix installed.

It is honest by design: the "expected" answers come from one student's own
solution, so passing every test does **not** prove correctness - it proves
agreement with that one solution on the cases tried.""",
    ),
    (
        "roles",
        "Author and Receiver",
        """\
- **Author** - builds tests from their own solution and shares them. Their
  solution is the de-facto reference that defines the expected answers.
- **Receiver** - drops their own code into a received package and runs it.
  Without Morvix they just run `./run.sh`; with Morvix they get the rich view
  and can diff their results against the Author's.""",
    ),
    (
        "stages",
        "The four stages",
        """\
Work flows through four stages, and most commands belong to exactly one:

1. **Define** - language build/run settings, the solution, the execution model
   (`config`, `import`, `model`).
2. **Generate** - produce inputs and compute expected answers (`gen`, `clean`).
3. **Run** - build and judge under limits, report (`run`, `runner`).
4. **Share** - assemble a report and a package (`result`, `package`).""",
    ),
    (
        "axes",
        "The three independent axes",
        """\
Everything is the product of three orthogonal choices that never multiply
against each other:

- **Language adapter** - how source becomes runnable (C, C++, NASM, Python,
  Java, Rust). Adding a language is one adapter.
- **Execution model** - how the program is driven and what is observed
  (stdio, library, args, file, interactive).
- **Comparison strategy** - how pass/fail is decided (exact, whitespace, float,
  hash, checker, expected exit/crash - combinable per case).""",
    ),
    (
        "generators",
        "Generators and structured input",
        """\
Random shapes (`gen --random`) suit simple stdin formats, and you can shape the
values with `--dist` (uniform/zipf/clustered/...) and a `--difficulty` dial, or
reach for a worst-case shape like `anti_quicksort`. Most real assignments read
something structured, where random data produces meaningless tests - Morvix warns
you when `gen --expected` comes back all-empty.

For structured input the best tool is a grammar: you describe the format once and
sample inputs that are correct by construction, including counts that drive how
much follows ("read N, then N numbers"; "read R C, then an R x C grid"):

    gen --new-grammar mygram           # writes a starter you edit
    gen --grammar .morvix/generators/mygram.gram --count 1000
    gen --expected

A custom generator program (`gen --new-generator`) is the imperative alternative,
and the vetted catalog (`gen --lib`, browse `gen --list-lib`) gives ready-made
trees/graphs/etc. with no code. To cover the space on purpose, declare ranges with
`--axis` and use `--boundary` (min/max/zero), `--exhaustive` (every small input),
or `--pairwise` (every pair of choices); `--multi` wraps T sub-inputs into one
file and `--ladder` sweeps sizes so you can read complexity off the timings.

A grammar asserts the input's *shape*, never an answer - expected answers still
come only from `gen --expected` running your own solution. If you have real inputs
already, `gen --import` ingests them (bundled answers are stripped), `gen --infer`
drafts a generator from samples, and `gen --mutate` derives more from a corpus.""",
    ),
    (
        "oracles",
        "Finding bugs without a reference answer",
        """\
Some checks find bugs with no "correct answer" at all - they only need your own
solution:

- **Stress** (`gen --stress`) runs your solution against a trusted rival (a rival
  tagged `--stress`) on generated inputs, keeps the disagreements, and shrinks
  each to a small reproducer. `gen --shrink <case>` minimises any failing case.
- **Crash** (`gen --crash`) feeds malformed inputs and keeps only the ones that
  actually crash, hang, or error.
- **Metamorphic** (`gen --metamorphic --relation ...`) transforms an input in a
  way whose effect on the output is known - e.g. for an order-independent problem,
  permuting the input must leave the output unchanged - and saves any violation.
  It compares two of *your* solution's outputs; it never asserts a right answer.
- **Property** (`gen --property 'out_int <= n'`) checks a bound on one output.
- **Fuzz** (`gen --fuzz`) mutates a corpus and keeps inputs that make the solution
  behave a new observable way.

All of these save inputs only; an unparseable or crashing run is inconclusive,
never a verdict.""",
    ),
    (
        "integrity",
        "Honest, reproducible answers",
        """\
Because the expected answers come from one solution, Morvix guards that boundary:

- Every generated case records *how it was made* (seed, shape, params) and which
  solution fingerprint froze its answer, so cases can be re-derived and drift is
  visible (`gen --pin` / `gen --diff-pin`).
- `gen --expected --check-stable` runs each case several times and refuses to
  freeze an answer that varies - a nondeterministic solution would poison the
  whole set.
- `gen --expected --changed` only recomputes cases whose input or the solution
  changed.
- `gen --validate` (scaffold with `gen --new-validator`) gates that generated
  inputs are well-formed before answers are frozen - the input-side counterpart of
  the output checker.""",
    ),
    (
        "assist",
        "Model-assisted scaffolds (off by default)",
        """\
Morvix never calls a model or the network. If you opt in, `gen --suggest` runs
*your* own executable hook (`--hook`) - which is where any model call happens - to
draft a generator or candidate inputs. The model's output is treated as unverified
INPUT or generator code only: a strict allow-list strips anything answer-shaped,
suggested inputs are inert until `gen --expected`, and a drafted generator is never
run for you. Expected answers still come only from your solution.""",
    ),
    (
        "layout",
        "Where things live, and packages",
        """\
A project keeps all its state under a single hidden `.morvix/` directory, so
your project root stays clean. A **package** is flat instead: `run.sh`,
`README.md`, `morvix.json`, `tests/`, `expected/` and `runner/` sit at the
archive root so a Receiver sees the harness directly. Unpack it into an empty
folder and run `./run.sh <your-solution>` - only Python 3 is needed. Opening a
package with Morvix re-adopts it into a `.morvix/` project.""",
    ),
    (
        "honesty",
        "The honesty principle",
        """\
Expected answers are produced by one peer's solution, not an authority. Passing
all tests proves agreement, not correctness; the real signal is many independent
solutions agreeing. Every generated package README says so. Morvix never invents
an answer it cannot derive by running a solution, and its suggestions explain and
ask rather than changing behavior silently.""",
    ),
]


def _md_arguments(name):
    """Markdown for a command's positional arguments and options, from the parser.

    Returns the full block (with its own 'Arguments:'/'Options:' headers), so a
    command with no arguments contributes nothing.
    """
    positionals, options = registry.arguments(name)
    lines = []
    if positionals:
        lines += ["Arguments:", ""]
        for p in positionals:
            choices = (
                "  (one of: %s)" % ", ".join(str(c) for c in p["choices"]) if p["choices"] else ""
            )
            lines.append("- `<%s>` - %s%s" % (p["name"].lower(), p["help"], choices))
        lines.append("")
    if options:
        lines += ["Options:", ""]
        for o in options:
            flag = o["names"][0]
            shown = flag + (" " + o["metavar"] if o["takes_value"] and o["metavar"] else "")
            alias = " (or `%s`)" % o["names"][1] if len(o["names"]) > 1 else ""
            choices = (
                "  (one of: %s)" % ", ".join(str(c) for c in o["choices"]) if o["choices"] else ""
            )
            lines.append("- `%s`%s - %s%s" % (shown, alias, o["help"], choices))
        lines.append("")
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
            out.extend(_md_arguments(name))
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
        parts += _md_arguments(topic)
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
    return (
        "\n".join(head)
        + "\n"
        + concepts_md()
        + "\n"
        + capabilities_md()
        + "\n"
        + command_reference_md()
    )


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
