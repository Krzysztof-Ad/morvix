# Confirmation prompt (Section 6.4).
#
# A clear yes/no used for destructive actions and the smart suggestions of
# Section 22. The default is shown explicitly and chosen safely. In a
# non-interactive run there is no one to ask, so it returns the default.
#
# API (implement in Workflow B):
#   confirm(ctx, question: str, default: bool = False) -> bool


def confirm(ctx, question, default=False):
    raise NotImplementedError
