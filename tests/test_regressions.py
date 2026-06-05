# Regression tests for issues found in the post-build review. Each one pins a
# fix so the bug cannot quietly return.

import os
import zipfile

from morvix.cases import TestCase
from morvix.compare import CompareInput, compare
from morvix.judge import judge, select_cases
from morvix.project import Project, Runner
from morvix import packaging


def _ns(root):
    from types import SimpleNamespace
    return SimpleNamespace(root=root)


def test_nonzero_exit_fails_even_when_output_matches(tmp_path, make_ctx):
    # A program that prints the right answer but exits non-zero must FAIL by
    # default - a clean exit 0 is required when no exit expectation is set.
    sol = tmp_path / "s.py"
    sol.write_text("print(42)\nimport sys\nsys.exit(3)\n")
    proj = Project.create(str(tmp_path), "t")
    proj.language = "python"
    proj.solution = str(sol)
    (tmp_path / "tests" / "baseline").mkdir(parents=True)
    (tmp_path / "expected" / "baseline").mkdir(parents=True)
    (tmp_path / "tests" / "baseline" / "c.in").write_text("")
    (tmp_path / "expected" / "baseline" / "c.out").write_text("42\n")
    proj.add_case(TestCase(name="c", group="baseline", manual=True,
                           inputs={"stdin": "tests/baseline/c.in"},
                           expected_output="expected/baseline/c.out"))
    proj.save()
    run = judge(proj, str(sol), "python", select_cases(proj))
    assert not run.all_passed
    assert run.cases[0].status == "fail"


def test_float_identical_nonfinite_tokens_pass(tmp_path):
    # Identical inf/nan tokens used to fail because abs(a-b) is nan.
    def vf(observed, expected):
        ci = CompareInput(observed.encode(), expected.encode(), None, _ns(str(tmp_path)), {})
        return compare("float", ci).passed
    assert vf("inf", "inf")
    assert vf("nan", "nan")
    assert vf("1.0 2.0", "1.0000001 2.0")
    assert not vf("1.0", "1.5")


def test_package_runner_filter(tmp_path, make_ctx):
    # package --runner NAME must ship only the requested runner profile.
    proj = Project.create(str(tmp_path), "t")
    proj.language = "python"
    proj.runners = {"quick": Runner(name="quick"), "full": Runner(name="full")}
    (tmp_path / "tests" / "baseline").mkdir(parents=True)
    (tmp_path / "expected" / "baseline").mkdir(parents=True)
    (tmp_path / "tests" / "baseline" / "a.in").write_text("1 2\n")
    (tmp_path / "expected" / "baseline" / "a.out").write_text("3\n")
    proj.add_case(TestCase(name="a", group="baseline", manual=True,
                           inputs={"stdin": "tests/baseline/a.in"},
                           expected_output="expected/baseline/a.out"))
    proj.save()
    ctx = make_ctx(tmp_path)
    ctx.project = proj
    out = str(tmp_path / "pkg.zip")
    packaging.build_package(ctx, proj, fmt="zip", runners=["quick"], out=out)
    import json
    with zipfile.ZipFile(out) as z:
        manifest = json.loads(z.read(".morvix/morvix.json"))
    assert set(manifest["runners"]) == {"quick"}
