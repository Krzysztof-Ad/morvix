# Smart suggestions - the "Morvix noticed..." behaviors (Section 22).
#
# Morvix notices when a better option exists and offers it - it never changes
# behavior silently. Each suggestion is detect -> explain -> suggest -> let the
# user decide, delivered as a warning paired with a confirmation. They are
# advisory; the user always decides.
#
# API (implement in Workflow B):
#   suggest_hashing(ctx, project, group, output_bytes) -> bool   # did we switch
#   suggest_compression(ctx, project, size_bytes) -> str | None  # suggested format
#   warn_backend_metrics(ctx, runner) -> None
#   suggest_exit_status(ctx, project, crashing_case_ids) -> None
#   confirm_locale(ctx, project) -> None
#   explain_missing_stress_oracle(ctx, project) -> None

from morvix.components.confirm import confirm

LARGE_OUTPUT_BYTES = 256 * 1024  # past this, suggest hashing a group
LARGE_PACKAGE_BYTES = 20 * 1024 * 1024  # past this, suggest stronger compression
DEGENERATE_MIN = 5  # need a few answers before judging them


def warn_degenerate_expected(ctx, outputs):
    """Warn when computed answers look meaningless: nearly all empty, or all the
    same. Almost always this means the generated inputs don't match the program's
    input format - so a custom generator is the fix (Section 13.6, 22).
    """
    if len(outputs) < DEGENERATE_MIN:
        return
    stripped = [o.strip() for o in outputs]
    empty = sum(1 for s in stripped if not s)
    total = len(outputs)
    if empty >= total * 0.8:
        ctx.messenger.warning(
            f"{empty} of {total} expected outputs are empty.",
            hint="Your inputs probably don't match what the program reads. Write a "
            "custom generator that produces valid inputs: gen --new-generator.",
        )
    elif len(set(stripped)) == 1:
        ctx.messenger.warning(
            f"All {total} expected outputs are identical.",
            hint="The inputs may not be exercising the program. A richer generator "
            "(gen --new-generator) usually helps.",
        )


def suggest_hashing(ctx, project, group, output_bytes):
    # If the combined expected output for a group is large, hashing saves disk
    # space but loses per-failure diffs (Section 22).
    if output_bytes <= LARGE_OUTPUT_BYTES:
        return False

    size_mb = output_bytes / (1024 * 1024)
    ctx.messenger.warning(
        f"Group '{group}' has {size_mb:.1f} MB of expected output.",
        hint="Switching to hash comparison saves space but you won't see diffs on failure.",
    )
    accepted = confirm(ctx, f"Switch group '{group}' to hash comparison?", default=False)
    if not accepted:
        return False

    # Apply in-memory; the caller is responsible for saving the project.
    for case in project.cases:
        if case.group == group:
            case.compare = "hash"
    return True


def suggest_compression(ctx, project, size_bytes):
    # If a package is very large, offer stronger compression (Section 22).
    if size_bytes <= LARGE_PACKAGE_BYTES:
        return None

    size_mb = size_bytes / (1024 * 1024)
    ctx.messenger.warning(
        f"Package is {size_mb:.1f} MB - that's large for distribution.",
        hint="tar.xz compresses significantly better than the default format.",
    )
    accepted = confirm(ctx, "Repack with tar.xz for smaller output?", default=False)
    return "tar.xz" if accepted else None


def warn_backend_metrics(ctx, runner):
    # The bash backend measures time and memory through the shell, which is
    # imprecise and may not capture memory at all (Section 22).
    if runner.backend != "bash":
        return
    if not (runner.time or runner.measure_mem):
        return

    issues = []
    if runner.time:
        issues.append("timing will be imprecise")
    if runner.measure_mem:
        issues.append("memory measurement may be unavailable")

    ctx.messenger.warning(
        f"Runner '{runner.name}' uses the bash backend: {', '.join(issues)}.",
        hint="Use backend='python' for accurate metrics.",
    )


def suggest_exit_status(ctx, project, crashing_case_ids):
    # If some cases crashed, offer to record the expected exit status or signal
    # so future runs can treat that outcome as correct (Section 22).
    if not crashing_case_ids:
        return

    ids_str = ", ".join(crashing_case_ids)
    ctx.messenger.warning(
        f"These cases exited unexpectedly: {ids_str}",
        hint="If a non-zero exit or signal is the correct behaviour, record it.",
    )
    confirm(
        ctx,
        "Would you like to record the expected exit status / signal for these cases?",
        default=False,
    )


def confirm_locale(ctx, project):
    # Morvix always sets LC_ALL=C for deterministic output. Mention it so
    # projects that depend on locale-sensitive sorting are not surprised
    # (Section 21.3).
    ctx.messenger.info(
        f"Locale: LC_ALL=C is in force for all runs (project locale='{project.locale}')."
        " This keeps output deterministic across machines."
    )


def explain_missing_stress_oracle(ctx, project):
    # Stress testing compares the solution under test against a trusted oracle -
    # a rival tagged --stress. Without one registered, stress mode can't run
    # (Section 22).
    ctx.messenger.warning(
        "Stress testing needs a trusted oracle to compare against.",
        hint="Register one with:  rival add <path> --stress",
    )


def warn_unstable_answers(ctx, case_ids):
    # gen --expected --check-stable refuses to freeze an answer that varies
    # between runs: a nondeterministic solution would poison the whole expected
    # set. Tell the user which cases were skipped and why.
    if not case_ids:
        return
    shown = ", ".join(case_ids[:5]) + (" ..." if len(case_ids) > 5 else "")
    ctx.messenger.warning(
        f"{len(case_ids)} case(s) gave different output across runs - answer NOT frozen: {shown}",
        hint="Your solution looks nondeterministic (unseeded RNG, dict/set order, time). "
        "Make it deterministic, then rerun 'gen --expected'.",
    )


def suggest_invalid_inputs(ctx, invalid_ids):
    # --require-valid dropped inputs the validator rejected; surface it so a
    # broken generator isn't silently producing malformed cases.
    if not invalid_ids:
        return
    ctx.messenger.warning(
        f"{len(invalid_ids)} generated input(s) failed the validator and were dropped.",
        hint="Fix the generator (or the validator) so generated inputs are well-formed.",
    )
