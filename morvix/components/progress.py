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

from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn


@contextmanager
def progress_bar(ctx, total, description="working"):
    # Non-interactive: no output, just yield a no-op step
    if not ctx.interactive:
        def _noop(n=1):
            pass
        yield _noop
        return

    # Interactive: show a rich progress bar on ctx.console
    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=ctx.console,
        transient=True,
    )
    task_id = None
    try:
        progress.start()
        task_id = progress.add_task(description, total=total)

        def _step(n=1):
            progress.advance(task_id, n)

        yield _step
    finally:
        progress.stop()
