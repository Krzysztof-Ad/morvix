# Tests for rival performance comparison: the model + migration, the comparison
# assembly/rendering, and stress testing using a stress-tagged rival.

import os

from morvix import comparison
from morvix.cases import TestCase
from morvix.generators import gen_stress
from morvix.project import Project, Rival
from morvix.results import comparison_block

SUM_ALL = "import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n"
SUM_SLOW = "import sys,time\nd=sys.stdin.read().split()\ntime.sleep(0.03)\nprint(sum(int(x) for x in d))\n"
SUM_BUGGY = "import sys\nprint(sum(int(x) for x in sys.stdin.read().split()) + 1)\n"


def _add_cases(proj, pairs):
    for name, inp, out in pairs:
        irel = os.path.join("tests", "baseline", name + ".in")
        erel = os.path.join("expected", "baseline", name + ".out")
        # paths are .morvix-relative via layout; use the project's dirs
        from morvix import layout
        irel = os.path.join(layout.TESTS_DIR, "baseline", name + ".in")
        erel = os.path.join(layout.EXPECTED_DIR, "baseline", name + ".out")
        os.makedirs(os.path.dirname(proj.abspath(irel)), exist_ok=True)
        os.makedirs(os.path.dirname(proj.abspath(erel)), exist_ok=True)
        open(proj.abspath(irel), "w").write(inp + "\n")
        open(proj.abspath(erel), "w").write(out + "\n")
        proj.add_case(TestCase(name=name, group="baseline", manual=True,
                               inputs={"stdin": irel}, expected_output=erel))


def test_rival_add_persists(tmp_path):
    proj = Project.create(str(tmp_path), "t")
    proj.add_rival(Rival(name="brute", path="/x/brute.c", stress=True))
    proj.save()
    reloaded = Project.load(str(tmp_path))
    r = reloaded.get_rival("brute")
    assert r is not None and r.stress and r.path == "/x/brute.c"
    assert reloaded.stress_rival().name == "brute"


def test_bruteforce_migrates_to_stress_rival(tmp_path):
    proj = Project.create(str(tmp_path), "t")
    proj.bruteforce = "/x/old_brute.py"      # pre-0.6 style
    proj.save()
    reloaded = Project.load(str(tmp_path))
    sr = reloaded.stress_rival()
    assert sr is not None and sr.path == "/x/old_brute.py"


def test_compare_live_renders_block(tmp_path, py_project):
    ctx, proj = py_project                    # solution = SUM_ALL
    slow = tmp_path / "slow.py"
    slow.write_text(SUM_SLOW)
    proj.add_rival(Rival(name="slow", path=str(slow)))
    _add_cases(proj, [("a", "1 2 3", "6"), ("b", "10 20", "30")])
    proj.save()
    from morvix.judge import select_cases
    main, cols = comparison.compare_live(proj, proj.solution, "python",
                                         select_cases(proj), proj.rivals)
    assert main.all_passed
    lines = "\n".join(comparison_block(main, cols))
    assert "Comparison (vs solution):" in lines
    assert "slow" in lines
    assert "x" in lines                        # a ratio is shown


def test_stress_uses_stress_rival(tmp_path, py_project, make_ctx):
    ctx, proj = py_project
    buggy = tmp_path / "buggy.py"
    buggy.write_text(SUM_BUGGY)
    proj.solution = str(buggy)                 # the solution under test is wrong
    proj.add_rival(Rival(name="ref", path=proj.reference, stress=True))  # trusted oracle
    proj.save()
    case = gen_stress(ctx, proj, count=30, seed=3)
    assert case is not None                    # a disagreement was found and saved
    assert case.manual is True
