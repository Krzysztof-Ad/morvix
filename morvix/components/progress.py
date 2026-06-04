# Progress indicator (Section 6.6).
#
# For long operations (generating thousands of cases, a stress loop, a large
# suite): counts, elapsed, current item. Reused everywhere a long operation
# runs. Built on rich.
#
# API (implement in Workflow B):
#   progress_bar(ctx, total: int, description: str = "working") -> context manager
#       Yields a callable step(n=1) that advances the bar.
#       Non-interactive: yields a no-op step.

from contextlib import contextmanager


@contextmanager
def progress_bar(ctx, total, description="working"):
    raise NotImplementedError
    yield  # pragma: no cover
