# The results table renders a per-case unified diff only when --diff is on
# (render_run's show_diff). Several receivers wanted parity with ./run.sh's diff;
# this guards that the diff text actually reaches the console when asked for.

from morvix.components.table import render_run
from morvix.results import CaseResult, RunResult


class _FakeConsole:
    """Records everything print()ed, with markup stripped enough to grep."""

    def __init__(self):
        self.out = []

        class _File:
            def isatty(self_inner):
                return False

        self.file = _File()

    def print(self, text=""):
        self.out.append(str(text))

    def text(self):
        return "\n".join(self.out)


def _failed_run():
    run = RunResult(solution="sol.py")
    run.cases.append(
        CaseResult(
            case_id="baseline/c1",
            group="baseline",
            status="fail",
            verdict="output differs",
            diff="--- expected\n+++ observed\n@@ -1 +1 @@\n-9\n+10",
        )
    )
    return run


def test_render_run_hides_diff_by_default():
    console = _FakeConsole()
    render_run(console, _failed_run(), show_perf=False)
    assert "+10" not in console.text()


def test_render_run_shows_diff_when_asked():
    console = _FakeConsole()
    render_run(console, _failed_run(), show_perf=False, show_diff=True)
    text = console.text()
    assert "-9" in text and "+10" in text
    assert "baseline/c1" in text


def test_render_run_no_diff_block_when_all_pass():
    console = _FakeConsole()
    run = RunResult(solution="sol.py")
    run.cases.append(CaseResult(case_id="baseline/c1", group="baseline", status="pass"))
    render_run(console, run, show_perf=False, show_diff=True)
    # No diff to show, so nothing diff-like leaks in.
    assert "@@" not in console.text()
