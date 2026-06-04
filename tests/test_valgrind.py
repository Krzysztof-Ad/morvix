# The valgrind-augmented memory-correctness path (Section 15.2).
#
# valgrind is Linux-only (it has no Apple-Silicon support), so this test skips
# wherever valgrind or a C compiler is absent and runs for real in CI on Linux.
# A clean C program should get a clean memcheck verdict and pass; one with a
# heap buffer overflow should get a memcheck failure.

import os
import shutil

import pytest

from morvix.cases import TestCase
from morvix.judge import judge, select_cases
from morvix.project import Project, Runner

pytestmark = [
    pytest.mark.skipif(shutil.which("valgrind") is None, reason="valgrind not installed"),
    pytest.mark.skipif(shutil.which("gcc") is None and shutil.which("cc") is None,
                       reason="no C compiler"),
]

CLEAN_C = """#include <stdio.h>
#include <stdlib.h>
int main(void){
    long a,b; if(scanf("%ld %ld",&a,&b)!=2) return 1;
    int *p = malloc(2*sizeof(int));
    p[0]=1; p[1]=2;
    printf("%ld\\n", a+b);
    free(p);
    return 0;
}
"""

# Heap buffer overflow: valgrind reports an "Invalid write" -> memcheck fails.
OVERFLOW_C = """#include <stdio.h>
#include <stdlib.h>
int main(void){
    long a,b; if(scanf("%ld %ld",&a,&b)!=2) return 1;
    int *p = malloc(2*sizeof(int));
    p[5] = 1;            /* invalid write past the 2-int buffer */
    printf("%ld\\n", a+b);
    free(p);
    return 0;
}
"""


def _judge_one(tmp_path, src_text):
    sol = tmp_path / "s.c"
    sol.write_text(src_text)
    proj = Project.create(str(tmp_path), "vg")
    proj.language = "c"
    proj.model = "stdio"
    proj.solution = str(sol)
    (tmp_path / "tests" / "baseline").mkdir(parents=True)
    (tmp_path / "expected" / "baseline").mkdir(parents=True)
    (tmp_path / "tests" / "baseline" / "t.in").write_text("3 4\n")
    (tmp_path / "expected" / "baseline" / "t.out").write_text("7\n")
    proj.add_case(TestCase(name="t", group="baseline", manual=True,
                           inputs={"stdin": "tests/baseline/t.in"},
                           expected_output="expected/baseline/t.out"))
    proj.save()
    runner = Runner(name="vg", backend="valgrind", memcheck=True)
    return judge(proj, str(sol), "c", select_cases(proj), runner=runner).cases[0]


def test_clean_program_passes_memcheck(tmp_path):
    c = _judge_one(tmp_path, CLEAN_C)
    assert c.memcheck is True
    assert c.status == "pass"


def test_overflow_fails_memcheck(tmp_path):
    c = _judge_one(tmp_path, OVERFLOW_C)
    assert c.memcheck is False
    assert c.status == "fail"
