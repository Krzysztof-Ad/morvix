# Rust adapter: build a single-file rustc solution, run it, and judge it. Skips
# where rustc is absent.

import shutil

import pytest

from morvix.cases import TestCase
from morvix.judge import judge, select_cases
from morvix.project import Project

pytestmark = pytest.mark.skipif(shutil.which("rustc") is None, reason="rustc not installed")

SUM_RS = """use std::io::{self, Read};
fn main() {
    let mut s = String::new();
    io::stdin().read_to_string(&mut s).unwrap();
    let v: Vec<i64> = s.split_whitespace().map(|x| x.parse().unwrap()).collect();
    println!("{}", v[0] + v[1]);
}
"""


def test_rust_build_run_judge(tmp_path):
    sol = tmp_path / "sum.rs"
    sol.write_text(SUM_RS)
    proj = Project.create(str(tmp_path), "rs")
    proj.language = "rust"
    proj.model = "stdio"
    proj.solution = str(sol)
    (tmp_path / "tests" / "baseline").mkdir(parents=True)
    (tmp_path / "expected" / "baseline").mkdir(parents=True)
    for i, (inp, out) in enumerate([("40 2", "42"), ("100 -50", "50")]):
        (tmp_path / "tests" / "baseline" / ("r%d.in" % i)).write_text(inp + "\n")
        (tmp_path / "expected" / "baseline" / ("r%d.out" % i)).write_text(out + "\n")
        proj.add_case(TestCase(name="r%d" % i, group="baseline", manual=True,
                               inputs={"stdin": "tests/baseline/r%d.in" % i},
                               expected_output="expected/baseline/r%d.out" % i))
    proj.save()
    run = judge(proj, str(sol), "rust", select_cases(proj))
    assert run.all_passed
    assert run.passed == 2
