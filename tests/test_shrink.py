# Tests for the delta-debugging shrinker (shrink.py) and the failure drivers.

from morvix import generators
from morvix.project import Rival
from morvix.shrink import shrink_failure

# A solution that crashes when the input contains the token 13; otherwise sums.
SEGV_ON_13 = (
    "import sys\n"
    "d = sys.stdin.read().split()\n"
    "if '13' in d:\n"
    "    raise SystemExit(139)\n"
    "print(sum(int(x) for x in d))\n"
)
BUGGY_SUM = "import sys\nprint(sum(int(x) for x in sys.stdin.read().split()) + 1)\n"


def test_shrink_reduces_to_trigger_token():
    # Failure: the input still contains "13". Shrink should drop everything else.
    data = b"5\n10 11 12 13 14\n"
    pred = lambda b: b"13" in b  # noqa: E731
    small = shrink_failure(pred, data, budget=2000)
    assert b"13" in small
    assert len(small) < len(data)


def test_shrink_repairs_dependent_count():
    # "n then n numbers": still fails while a 0 is present; shrinking trailing
    # items must keep the header consistent so the predicate keeps matching.
    data = b"4\n7 0 8 9"
    pred = lambda b: b"0" in b.split()  # noqa: E731
    small = shrink_failure(pred, data, budget=4000)
    assert b"0" in small.split()
    assert len(small) <= len(data)


def test_shrink_reduces_number_magnitude():
    data = b"1\n999999"
    pred = lambda b: len(b.split()) >= 2 and b.split()[1] != b"0"  # noqa: E731
    small = shrink_failure(pred, data, budget=2000)
    # The big number is driven down to the minimal still-nonzero value.
    assert small.split()[1] in (b"1", b"-1")


def test_shrink_budget_terminates():
    calls = [0]

    def pred(b):
        calls[0] += 1
        return b"x" in b

    shrink_failure(pred, b"xxxxxxxxxx", budget=50)
    assert calls[0] <= 50


def test_shrink_never_returns_passing_input():
    data = b"1 2 3 4 5"
    pred = lambda b: b == data  # only the exact original "fails"  # noqa: E731
    small = shrink_failure(pred, data, budget=500)
    assert small == data  # cannot shrink without losing the failure


# --- integration: gen_crash triage + gen_shrink on a real crashing solution ---


def test_gen_crash_triage_keeps_only_crashers(py_project, tmp_path):
    ctx, proj = py_project
    sol = tmp_path / "segv.py"
    sol.write_text(SEGV_ON_13)
    proj.solution = str(sol)
    # Seed a baseline input so the mangler has something to chew on.
    generators.gen_manual(ctx, proj, "b", group="baseline", content="3\n13 1 2\n")
    kept, buckets = generators.gen_crash(ctx, proj, count=4, seed=1, group="bad")
    # Only inputs that actually crash/error are kept; buckets report the kinds.
    assert all(c.expected_output is None for c in kept)  # crash mode sets no answers
    if kept:
        assert sum(buckets.values()) == len(kept)


def test_gen_shrink_minimises_a_crashing_case(py_project, tmp_path):
    ctx, proj = py_project
    sol = tmp_path / "boom.py"
    sol.write_text(SEGV_ON_13)
    proj.solution = str(sol)
    generators.gen_manual(ctx, proj, "big", group="reg", content="6\n1 2 13 4 5 6\n")
    case = generators.gen_shrink(ctx, proj, "reg/big", budget=1500)
    assert case is not None
    text = open(proj.abspath(case.primary_input())).read()
    assert "13" in text  # the trigger token survives
    assert len(text) < len("6\n1 2 13 4 5 6\n")  # but the input is smaller
    # The solution's own observed misbehaviour is recorded (exit 139), not invented.
    assert case.expected_exit == 139 or case.expected_signal is not None


def test_gen_stress_keeps_multiple_and_shrinks(py_project, tmp_path):
    ctx, proj = py_project
    buggy = tmp_path / "buggy.py"
    buggy.write_text(BUGGY_SUM)
    correct = tmp_path / "ok.py"
    correct.write_text("import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n")
    proj.solution = str(buggy)
    proj.add_rival(Rival(name="ok", path=str(correct), stress=True))
    cases = generators.gen_stress(ctx, proj, count=20, seed=1, keep=3)
    assert 1 <= len(cases) <= 3
    # Each saved disagreement carries the oracle's answer and a shrunk input.
    for c in cases:
        assert c.expected_output is not None
        assert c.note and "disagreement" in c.note
