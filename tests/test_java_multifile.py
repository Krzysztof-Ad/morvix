# Multi-file Java: proves the java adapter compiles a package tree via
# -sourcepath AND that judging actually discriminates - several cases, with a
# real pass/fail split, not just "the plumbing ran".

import shutil

import pytest

from morvix.cases import TestCase
from morvix.judge import judge, select_cases
from morvix.project import Project

pytestmark = pytest.mark.skipif(shutil.which("javac") is None, reason="javac not installed")

MAIN = """import util.Adder;
import java.util.Scanner;
public class Main {
    public static void main(String[] args) {
        Scanner s = new Scanner(System.in);
        System.out.println(Adder.add(s.nextLong(), s.nextLong()));
    }
}
"""

ADDER = """package util;
public class Adder {
    public static long add(long a, long b) { return a + b; }
}
"""


def test_multifile_java_compiles_and_judges(tmp_path):
    src = tmp_path / "src"
    (src / "util").mkdir(parents=True)
    (src / "Main.java").write_text(MAIN)
    (src / "util" / "Adder.java").write_text(ADDER)

    proj = Project.create(str(tmp_path), "j")
    proj.language = "java"
    proj.model = "stdio"
    sol = str(src / "Main.java")
    proj.solution = sol

    (tmp_path / "tests" / "baseline").mkdir(parents=True)
    (tmp_path / "expected" / "baseline").mkdir(parents=True)
    # c3's expected output is deliberately wrong, so it must FAIL.
    cases = [("c1", "2 3", "5"), ("c2", "10 20", "30"), ("c3", "1 1", "3")]
    for name, inp, out in cases:
        (tmp_path / "tests" / "baseline" / (name + ".in")).write_text(inp + "\n")
        (tmp_path / "expected" / "baseline" / (name + ".out")).write_text(out + "\n")
        proj.add_case(
            TestCase(
                name=name,
                group="baseline",
                manual=True,
                inputs={"stdin": "tests/baseline/%s.in" % name},
                expected_output="expected/baseline/%s.out" % name,
            )
        )
    proj.save()

    run = judge(proj, sol, "java", select_cases(proj))
    assert run.total == 3
    assert run.passed == 2  # the multi-file project built via -sourcepath and ran
    byid = {c.case_id: c for c in run.cases}
    assert byid["baseline/c1"].status == "pass"
    assert byid["baseline/c3"].status == "fail"  # judging really discriminates
