# The auto-generated package README (Section 17.4, 17.5).
#
# README assembly is string templates keyed to the choices made: each runner
# option, comparison strategy and execution model contributes one or more
# pre-written sentences. It is deliberately not a content system - one fragment
# per feature, assembled in order. It always ends with the honesty clause.
#
# API (implement in Workflow B):
#   generate_readme(project) -> str   # Markdown

from morvix.cases import list_groups

# Descriptions for each comparison strategy (must match morvix.compare.list_strategies())
_STRATEGY_DESC = {
    "exact": "Outputs are compared byte-for-byte (exact match required).",
    "whitespace": "Outputs are compared after normalising whitespace (extra spaces and blank lines are ignored).",
    "float": "Outputs are compared numerically, allowing small floating-point differences.",
    "hash": "The expected output stores a hash; the actual output is hashed and compared.",
    "checker": "A custom checker program decides whether the output is accepted.",
}

# Descriptions for execution models (must match morvix.models.list_models())
_MODEL_DESC = {
    "stdio": "The program reads from **stdin** and writes to **stdout**.",
    "args": "The program receives its input as **command-line arguments**.",
    "file": "The program reads from and writes to **files** on disk.",
    "library": "The program is tested as a **library** — functions are called directly.",
    "interactive": "The program runs **interactively**, exchanging multiple lines of input and output.",
}

_DISCLAIMER = """\
## Disclaimer

These tests come from one student's own solution and one interpretation of the assignment.
There is no official answer key.
Passing all tests **does not prove correctness**.
Widespread disagreement across many independent solutions is the real signal that a test may be wrong.
"""


def generate_readme(project) -> str:
    """Build a Markdown README for a Morvix test package."""
    parts = []

    # --- Title and intro ---
    parts.append(f"# {project.name}\n")
    parts.append(
        f"Automated test package for **{project.name}**, "
        "generated with [Morvix](https://github.com/morvix/morvix).\n"
    )

    # --- How to run WITHOUT Morvix ---
    parts.append("## How to run (without Morvix)\n")
    parts.append(
        "Only Python 3 is required. Run your solution against the tests with:\n"
        "\n"
        "```bash\n"
        "./run.sh <your-solution>\n"
        "```\n"
        "\n"
        "Useful flags:\n"
        "\n"
        "- `--group <name>` — run only cases from a specific group\n"
        "- `--case <id>` — run a single case by id\n"
        "- `--no-valgrind` — skip the memory checker even if it is installed\n"
        "- `--diff` — show a side-by-side diff on failure\n"
    )

    # --- How to run WITH Morvix ---
    parts.append("## How to run (with Morvix)\n")
    parts.append(
        "If you have [Morvix](https://github.com/morvix/morvix) installed, "
        "open it in this directory for the full interactive view:\n"
        "\n"
        "```bash\n"
        "morvix\n"
        "```\n"
    )

    # --- What the tests cover ---
    parts.append("## What the tests cover\n")
    groups = list_groups(project.cases)
    if groups:
        # Count cases per group
        group_counts: dict[str, int] = {}
        for case in project.cases:
            group_counts[case.group] = group_counts.get(case.group, 0) + 1

        rows = []
        for g in groups:
            count = group_counts.get(g, 0)
            noun = "case" if count == 1 else "cases"
            rows.append(f"- **{g}** — {count} {noun}")
        parts.append("\n".join(rows) + "\n")
    else:
        parts.append("No test cases are included in this package yet.\n")

    # --- How answers are judged ---
    parts.append("## How answers are judged\n")

    # Comparison strategy
    strategy = project.compare.get("strategy", "whitespace")
    strategy_text = _STRATEGY_DESC.get(strategy, f"Comparison strategy: `{strategy}`.")
    parts.append(strategy_text + "\n")

    # Float epsilon note
    if strategy == "float":
        eps_abs = project.compare.get("epsilon_abs", 1e-6)
        eps_rel = project.compare.get("epsilon_rel", 1e-9)
        parts.append(f"Absolute epsilon: `{eps_abs}`. Relative epsilon: `{eps_rel}`.\n")

    # Execution model
    model = project.model
    model_text = _MODEL_DESC.get(model, f"Execution model: `{model}`.")
    parts.append(model_text + "\n")

    # Limits
    limits = project.limits
    limit_lines = []
    if limits.get("wall") is not None:
        limit_lines.append(f"wall-clock time: **{limits['wall']}s**")
    if limits.get("cpu") is not None:
        limit_lines.append(f"CPU time: **{limits['cpu']}s**")
    if limits.get("mem_kb") is not None:
        limit_lines.append(f"memory: **{limits['mem_kb']} KB**")
    if limits.get("output_kb") is not None:
        limit_lines.append(f"output: **{limits['output_kb']} KB**")
    if limit_lines:
        parts.append("Limits in force: " + ", ".join(limit_lines) + ".\n")

    # Memory checker
    # Check if any runner has memcheck enabled, or note the flag
    any_memcheck = any(r.memcheck for r in project.runners.values())
    if any_memcheck:
        parts.append(
            "The memory checker (valgrind) **is enabled** for at least one runner profile. "
            "Use `--no-valgrind` to skip it.\n"
        )
    else:
        parts.append(
            "The memory checker (valgrind) is **not enabled** for any runner profile. "
            "Valgrind runs automatically when the runner is configured with `memcheck: true`.\n"
        )

    # --- Standard correctness disclaimer ---
    parts.append(_DISCLAIMER)

    return "\n".join(parts)
