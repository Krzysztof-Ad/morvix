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
                "currently imported, the reference and brute-force solutions, and test counts.",
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
        "examples": ["config cpp", "config c --std gnu23 --opt O2",
                     "config --raw-build 'make tester' --raw-run './tester'"],
    },
    "import": {
        "stage": "define",
        "summary": "Set the solution currently under test.",
        "long": "Registers a solution as the code under test. --reference keeps it in place "
                "(good while editing); --copy copies it into the project (good for a frozen one, "
                "or for a Receiver dropping in their own code).",
        "examples": ["import solution.c", "import mysol.py --copy"],
    },
    "reference": {
        "stage": "define",
        "summary": "Set the solution that defines the expected answers.",
        "long": "The reference is whatever you trust to produce the 'right' answers - in "
                "practice your own solution. Its outputs become the frozen expected answers.",
        "examples": ["reference solution.c"],
    },
    "bruteforce": {
        "stage": "define",
        "summary": "Register a slow, trusted solution for stress testing.",
        "long": "A simple brute-force solution, trusted because it is simple. Stress testing "
                "compares the real solution against it to find bugs. Never shipped in a package.",
        "examples": ["bruteforce brute.py"],
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
        "long": "Make test cases: by hand (--manual), from the built-in random shapes "
                "(--random), from a custom generator (--generator), or recompute expected "
                "answers (--expected). Also stress testing (--stress) and crash candidates "
                "(--crash). For structured input, 'gen --new-generator' writes a starter "
                "generator you edit - usually the right tool when random shapes don't fit.",
        "examples": ["gen --random --count 100 --seed 1 --shape ints",
                     "gen --new-generator mygen", "gen --generator generators/mygen.py --count 1000",
                     "gen --manual edge1", "gen --expected", "gen --expected --hash",
                     "gen --stress --count 5000", "gen --crash"],
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
        "examples": ["run --all", "run --group bad-input --time",
                     "run --case edge1 --compare exact"],
    },
    "runner": {
        "stage": "run",
        "summary": "Create, edit, inspect or list runner profiles.",
        "long": "A runner is the shareable thing that executes the tests - a named profile of "
                "which cases, comparison, limits, backend and toggles. 'runner new' opens a "
                "guided form; 'runner build' writes the portable run.sh + Python core.",
        "examples": ["runner new full", "runner list", "runner show quick",
                     "runner build full"],
    },

    # --- Share ---
    "result": {
        "stage": "share",
        "summary": "Produce or export a results report.",
        "long": "Export the last run as JSON (machine-readable), Markdown (the human report) or "
                "plain text. 'result diff' compares your results against another run or the "
                "Author's.",
        "examples": ["result --md --out report.md", "result --json",
                     "result diff their_results.json"],
    },
    "package": {
        "stage": "share",
        "summary": "Build the shareable archive (without your source).",
        "long": "Bundles tests, expected answers, the runner, README and manifest into one "
                "archive - and deliberately leaves out your solution source. Choose contents and "
                "the archive format (zip / tar / tar.gz / tar.xz).",
        "examples": ["package --zip", "package --tar.xz --include-generators",
                     "package --runner full"],
    },

    # --- Automation ---
    "workflow": {
        "stage": "automation",
        "summary": "Record and replay sequences of commands.",
        "long": "A workflow is a recorded list of Morvix commands stored as JSON - a Makefile "
                "for your tests. Record what you do, then replay it (optionally against another "
                "solution) on the next assignment.",
        "examples": ["workflow record setup", "workflow stop",
                     "workflow run setup --on other.c", "workflow list"],
    },
}

# 'quit' is an alias for 'exit'.
ALIASES = {"quit": "exit"}


def summary(name: str) -> str:
    name = ALIASES.get(name, name)
    return COMMANDS.get(name, {}).get("summary", "")


def commands_in_stage(stage: str):
    return [(n, c["summary"]) for n, c in COMMANDS.items() if c["stage"] == stage]
