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
#   explain_missing_bruteforce(ctx, project) -> None

LARGE_OUTPUT_BYTES = 256 * 1024       # past this, suggest hashing a group
LARGE_PACKAGE_BYTES = 20 * 1024 * 1024  # past this, suggest stronger compression


def suggest_hashing(ctx, project, group, output_bytes):
    raise NotImplementedError


def suggest_compression(ctx, project, size_bytes):
    raise NotImplementedError


def warn_backend_metrics(ctx, runner):
    raise NotImplementedError


def suggest_exit_status(ctx, project, crashing_case_ids):
    raise NotImplementedError


def confirm_locale(ctx, project):
    raise NotImplementedError


def explain_missing_bruteforce(ctx, project):
    raise NotImplementedError
