# Command descriptions, in one place (Section 5.5).
#
# This is the single source of truth for what each command does. The help
# command reads it, and so does the autocomplete meta column - so the two can
# never drift apart. Each entry has a one-line summary (used in the completion
# menu and the help list), the pipeline stage it belongs to, a longer
# description, and a few examples.

# The four pipeline stages, in order, with a label for the help screen.
STAGES = [
    ("project", "Project & session"),
    ("define", "Define"),
    ("generate", "Generate"),
    ("run", "Run"),
    ("share", "Share"),
    ("automation", "Automation"),
]

COMMANDS = {
    # --- Project & session ---
    "init": {
        "stage": "project",
        "summary": "Create a new Morvix project in this directory.",
        "long": "Lays out a fresh project (config, tests, runner, ...) here. "
        "Opens a guided form to pick the language, execution model and defaults.",
        "examples": ["init", "init --name week3 --model stdio"],
    },
    "open": {
        "stage": "project",
        "summary": "Load the project or package in this directory.",
        "long": "Loads an existing project, or adopts a received package (one with a "
        "morvix.json manifest) so you can work with it. Usually automatic on launch.",
        "examples": ["open"],
    },
    "status": {
        "stage": "project",
        "summary": "Show the project, solution under test, runner and counts.",
        "long": "A quick snapshot: current project, language, execution model, the solution "
        "currently imported, the registered rivals, and test counts.",
        "examples": ["status"],
    },
    "help": {
        "stage": "project",
        "summary": "List commands, or explain one in detail.",
        "long": "With no argument, lists every command grouped by pipeline stage. "
        "With a command name, shows that command's options and examples.",
        "examples": ["help", "help gen"],
    },
    "docs": {
        "stage": "project",
        "summary": "Open the full user guide (generated, always current).",
        "long": "Show the complete guide - concepts, every command, and what's supported - "
        "generated from the tool itself so it never drifts. 'docs <topic>' shows one "
        "section; 'docs --out GUIDE.md' writes the whole manual as Markdown.",
        "examples": ["docs", "docs generators", "docs run", "docs --out GUIDE.md"],
    },
    "exit": {
        "stage": "project",
        "summary": "Leave the interactive shell.",
        "long": "Quit the Morvix shell. 'quit' does the same thing.",
        "examples": ["exit"],
    },
    # --- Define ---
    "config": {
        "stage": "define",
        "summary": "Set build/run settings for a language.",
        "long": "Configure how a language is built and run (compiler, standard, flags, "
        "interpreter, classpath, link mode, ...). Opens a guided form, or takes flags. "
        "Includes the raw build/run command escape hatch for builds no preset captures.",
        "examples": [
            "config cpp",
            "config c --std gnu23 --opt O2",
            "config --raw-build 'make tester' --raw-run './tester'",
        ],
    },
    "import": {
        "stage": "define",
        "summary": "Set the solution currently under test.",
        "long": "Registers a solution as the code under test. --reference keeps it in place "
        "(good while editing); --copy copies it into the project (good for a frozen one, "
        "or for a Receiver dropping in their own code).",
        "examples": ["import solution.c", "import mysol.py --copy"],
    },
    "rival": {
        "stage": "define",
        "summary": "Manage performance-comparison solutions (not correctness).",
        "long": "A rival is an alternative implementation kept only to compare performance "
        "(time/memory) against - it never changes the tests or expected answers. Add as "
        "many as you like; tag one --stress to use it as the stress-test oracle. "
        "'rival precompute' records their numbers on this machine so they can ship "
        "code-free for a same-machine comparison.",
        "examples": [
            "rival add brute.c --stress",
            "rival add fast.c --name fast",
            "rival list",
            "rival precompute",
            "rival remove brute",
        ],
    },
    "model": {
        "stage": "define",
        "summary": "Choose the execution model (how a program is driven).",
        "long": "stdio (stdin->stdout), library (link & assert), args (argv), file (file in/out), "
        "or interactive (converses with a judge). Picks how cases are run.",
        "examples": ["model stdio", "model library"],
    },
    # --- Generate ---
    "gen": {
        "stage": "generate",
        "summary": "Generate or register test cases.",
        "long": "Make test cases and compute their answers. Inputs come from many sources - by "
        "hand (--manual), built-in random shapes (--random, tuned with --dist/--difficulty), a "
        "custom generator (--generator), a declarative grammar (--grammar, correct-by-construction "
        "for structured input), or the vetted catalog (--lib, browse with --list-lib). Cover the "
        "input space deliberately with --boundary/--exhaustive/--pairwise (declare ranges with "
        "--axis), wrap many sub-inputs with --multi, or sweep sizes with --ladder. Find bugs with "
        "--stress (vs a --stress rival, auto-minimised), --crash (keeps only real crashers), "
        "--fuzz, --metamorphic (a relation between your solution's own outputs), or --property (a "
        "bound on one output); reduce any failure with --shrink. Bring in real inputs with "
        "--import (bundled answers are stripped), learn their shape with --infer, and derive more "
        "with --mutate. Keep answers honest and reproducible with --expected (--check-stable, "
        "--changed), gate inputs with --validate, and track drift with --pin/--diff-pin. Every "
        "mode produces INPUTS only; expected answers always come from 'gen --expected' running "
        "your own solution. See 'docs grammar' for the grammar mini-language and the per-shape "
        "--param keys.",
        "examples": [
            "gen --random --count 100 --shape ints --dist zipf",
            "gen --new-grammar mygram",
            "gen --grammar .morvix/generators/mygram.gram --count 1000",
            "gen --lib tree.binary --param n=5000 --count 50",
            "gen --boundary --axis count=1..100000 --axis hi=-1000000..1000000 --shape ints",
            "gen --pairwise --axis layout=sorted,reverse --axis count=1,100,10000",
            "gen --ladder --shape ints --steps 8 --hi-n 100000",
            "gen --stress --shape array --count 5000 --keep 3",
            "gen --metamorphic --relation permute-invariant --shape array --count 200",
            "gen --property 'out_int <= n' --ladder-spec count=1..100000:8",
            "gen --shrink regression/stress_42",
            "gen --import ./cf_tests --split",
            "gen --infer sample1.txt sample2.txt",
            "gen --expected --check-stable",
            "gen --expected --changed",
            "gen --validate",
            "gen --pin before-refactor",
        ],
    },
    "clean": {
        "stage": "generate",
        "summary": "Remove generated cases (manual ones are kept).",
        "long": "Deletes disposable generated cases so they can be regenerated from a seed, "
        "while preserving hand-written manual cases. Asks for confirmation.",
        "examples": ["clean", "clean --group tricky"],
    },
    # --- Run ---
    "run": {
        "stage": "run",
        "summary": "Run the solution under test and report.",
        "long": "Builds the solution and runs it against the cases under the chosen limits and "
        "comparison, then shows a live results table. Pick scope with --all/--group/--case "
        "and toggle --time/--mem/--valgrind/--compare.",
        "examples": [
            "run --all",
            "run --group bad-input --time",
            "run --case edge1 --compare exact",
        ],
    },
    "runner": {
        "stage": "run",
        "summary": "Create, edit, inspect or list runner profiles.",
        "long": "A runner is the shareable thing that executes the tests - a named profile of "
        "which cases, comparison, limits, backend and toggles. 'runner new' opens a "
        "guided form; 'runner build' writes the portable run.sh + Python core.",
        "examples": ["runner new full", "runner list", "runner show quick", "runner build full"],
    },
    # --- Share ---
    "result": {
        "stage": "share",
        "summary": "Produce or export a results report.",
        "long": "Export the last run as JSON (machine-readable), Markdown (the human report) or "
        "plain text. 'result diff' compares your results against another run or the "
        "Author's.",
        "examples": [
            "result --md --out report.md",
            "result --json",
            "result diff their_results.json",
        ],
    },
    "package": {
        "stage": "share",
        "summary": "Build the shareable archive (without your source).",
        "long": "Bundles tests, expected answers, the runner, README and manifest into one "
        "archive - and deliberately leaves out your solution source. Choose contents and "
        "the archive format (zip / tar / tar.gz / tar.xz).",
        "examples": [
            "package --zip",
            "package --tar.xz --include-generators",
            "package --runner full",
        ],
    },
    # --- Automation ---
    "workflow": {
        "stage": "automation",
        "summary": "Record and replay sequences of commands.",
        "long": "A workflow is a recorded list of Morvix commands stored as JSON - a Makefile "
        "for your tests. Record what you do, then replay it (optionally against another "
        "solution) on the next assignment.",
        "examples": [
            "workflow record setup",
            "workflow stop",
            "workflow run setup --on other.c",
            "workflow list",
        ],
    },
}

# 'quit' is an alias for 'exit'.
ALIASES = {"quit": "exit"}


def summary(name: str) -> str:
    name = ALIASES.get(name, name)
    val = COMMANDS.get(name, {}).get("summary", "")
    return val if isinstance(val, str) else ""


def commands_in_stage(stage: str):
    return [(n, c["summary"]) for n, c in COMMANDS.items() if c["stage"] == stage]
