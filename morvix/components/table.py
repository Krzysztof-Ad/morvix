# Live results table (Section 6.5, Section 17.2).
#
# The colored, updating table that shows a run in progress and its outcome:
# per-case status, timing, memory, verdict, with per-group and overall
# summaries. Built on rich. Every command that shows results uses this one
# table, never a bespoke variant.
#
# API (implement in Workflow B):
#   class RunTable:
#       __init__(self, console, live: bool = True)
#       update(self, case_result)   # call as each case finishes
#       finish(self, run_result)    # render the per-group + overall summary
#   render_run(console, run_result) -> None   # static full render (non-interactive / after the fact)


class RunTable:
    def __init__(self, console, live=True):
        raise NotImplementedError

    def update(self, case_result):
        raise NotImplementedError

    def finish(self, run_result):
        raise NotImplementedError


def render_run(console, run_result):
    raise NotImplementedError
