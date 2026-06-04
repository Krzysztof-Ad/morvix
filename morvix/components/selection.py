# Selection list / multi-select (Section 6.1).
#
# Toggle several items out of many. Bulk operations are first-class because
# choosing among thousands of tests by hand is unacceptable: all / none /
# invert / by-group / by-glob / range, type-to-filter, and a live count.
#
# API (implement in Workflow B):
#   select(ctx, title: str, items: list[tuple[value, label, group]],
#          preselected: set | None = None) -> list[value]
#       Returns the list of selected values.
#       Non-interactive: returns every value (or list(preselected) if given).


def select(ctx, title, items, preselected=None):
    raise NotImplementedError
