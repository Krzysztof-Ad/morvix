# Tests for rival performance comparison: the model + migration, the comparison
# assembly/rendering, and stress testing using a stress-tagged rival.

import os

from morvix import comparison
from morvix.cases import TestCase
from morvix.generators import gen_stress
from morvix.project import Project, Rival
from morvix.results import comparison_block

SUM_ALL = "import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n"
SUM_SLOW = (
    "import sys,time\nd=sys.stdin.read().split()\ntime.sleep(0.03)\nprint(sum(int(x) for x in d))\n"
)
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
        proj.add_case(
            TestCase(
                name=name,
                group="baseline",
                manual=True,
                inputs={"stdin": irel},
                expected_output=erel,
            )
        )


def test_rival_add_persists(tmp_path):
    proj = Project.create(str(tmp_path), "t")
    proj.add_rival(Rival(name="brute", path="/x/brute.c", stress=True))
    proj.save()
    reloaded = Project.load(str(tmp_path))
    r = reloaded.get_rival("brute")
    assert r is not None and r.stress and r.path == "/x/brute.c"
    assert reloaded.stress_rival().name == "brute"


def test_bruteforce_migrates_to_stress_rival(tmp_path):
    # A pre-0.7 project stored a single 'bruteforce' path; loading it folds that
    # into a stress-test rival so old projects keep their oracle.
    import json

    from morvix.layout import PROJECT_FILE

    proj = Project.create(str(tmp_path), "t")
    proj.save()
    cfg = os.path.join(str(tmp_path), PROJECT_FILE)
    with open(cfg) as f:
        data = json.load(f)
    data["bruteforce"] = "/x/old_brute.py"  # pre-0.7 style
    with open(cfg, "w") as f:
        json.dump(data, f)

    reloaded = Project.load(str(tmp_path))
    sr = reloaded.stress_rival()
    assert sr is not None and sr.path == "/x/old_brute.py"


def test_comparison_aggregate_aligns_to_main_cases():
    # A precomputed rival can cover more cases than the (filtered) solution run;
    # the aggregate must only count the cases actually being compared.
    from morvix.results import CaseResult, RunResult, comparison_block

    main = RunResult(solution="s")
    main.cases = [CaseResult("g/a", "g", "pass", wall_time=0.10)]
    rival = RunResult(solution="r")
    rival.cases = [
        CaseResult("g/a", "g", "pass", wall_time=0.20),
        CaseResult("g/b", "g", "pass", wall_time=5.0),
    ]  # not in main
    block = "\n".join(
        comparison_block(
            main, [{"label": "rv", "run": rival, "precomputed": True, "env": "x"}], per_case=False
        )
    )
    assert "0.200s" in block  # rival counted only g/a (0.20), not g/b (5.0)
    assert "2.00x" in block  # 0.20 / 0.10
    assert "5.200s" not in block  # the unrelated case must not leak into totals


def test_compare_live_renders_block(tmp_path, py_project):
    ctx, proj = py_project  # solution = SUM_ALL
    slow = tmp_path / "slow.py"
    slow.write_text(SUM_SLOW)
    proj.add_rival(Rival(name="slow", path=str(slow)))
    _add_cases(proj, [("a", "1 2 3", "6"), ("b", "10 20", "30")])
    proj.save()
    from morvix.judge import select_cases

    main, cols = comparison.compare_live(
        proj, proj.solution, "python", select_cases(proj), proj.rivals
    )
    assert main.all_passed
    lines = "\n".join(comparison_block(main, cols))
    assert "Comparison (vs solution):" in lines
    assert "slow" in lines
    assert "x" in lines  # a ratio is shown


def test_package_ships_precomputed_and_runner_compares(tmp_path, py_project):
    import json
    import subprocess
    import sys
    import zipfile

    from morvix import packaging
    from morvix.judge import select_cases

    ctx, proj = py_project  # solution = SUM_ALL
    rv = tmp_path / "rv.py"
    rv.write_text(SUM_ALL)
    proj.add_rival(Rival(name="rv", path=str(rv)))
    _add_cases(proj, [("a", "1 2", "3"), ("b", "4 5", "9")])
    proj.save()

    comparison.precompute_rivals(proj, select_cases(proj))
    out = str(tmp_path / "p.zip")
    packaging.build_package(ctx, proj, fmt="zip", out=out, rivals_mode="precomputed")

    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        man = json.loads(z.read("morvix.json"))
    assert "rivals/rv.json" in names  # precomputed numbers shipped (code-free)
    assert man["rivals"][0]["mode"] == "precomputed"
    assert not any(n == "rivals/rv.py" for n in names)  # no code shipped

    extracted = tmp_path / "ex"
    extracted.mkdir()
    with zipfile.ZipFile(out) as z:
        z.extractall(str(extracted))
    (extracted / "sol.py").write_text(SUM_ALL)
    r = subprocess.run(
        [sys.executable, str(extracted / "runner" / "morvix_runner.py"), "sol.py", "--all"],
        cwd=str(extracted),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "Comparison (vs solution):" in r.stdout
    assert "precomputed" in r.stdout
    # And --no-rivals drops the comparison.
    r2 = subprocess.run(
        [
            sys.executable,
            str(extracted / "runner" / "morvix_runner.py"),
            "sol.py",
            "--all",
            "--no-rivals",
        ],
        cwd=str(extracted),
        capture_output=True,
        text=True,
    )
    assert "Comparison (vs solution):" not in r2.stdout


def test_stress_uses_stress_rival(tmp_path, py_project, make_ctx):
    ctx, proj = py_project
    correct = proj.solution  # the fixture's correct sum solution
    buggy = tmp_path / "buggy.py"
    buggy.write_text(SUM_BUGGY)
    proj.solution = str(buggy)  # the solution under test is wrong
    proj.add_rival(Rival(name="ref", path=correct, stress=True))  # trusted oracle
    proj.save()
    case = gen_stress(ctx, proj, count=30, seed=3)
    assert case is not None  # a disagreement was found and saved
    assert case.manual is True
