# Tests for performance reporting: the aggregation, the rendered sections, and
# the shipped runner core producing the same report.

import os
import subprocess
import sys
import zipfile

from morvix import layout, packaging
from morvix.cases import TestCase
from morvix.results import CaseResult, RunResult, performance, to_json, to_markdown, to_text


def _run():
    cases = [
        CaseResult("g/a", "g", "pass", wall_time=0.10, cpu_time=0.05, peak_mem_kb=1000),
        CaseResult("g/b", "g", "pass", wall_time=0.30, cpu_time=0.20, peak_mem_kb=2000),
        CaseResult("g/c", "g", "pass", wall_time=0.20, cpu_time=0.10, peak_mem_kb=1500),
    ]
    return RunResult(solution="s", cases=cases)


def test_performance_aggregates():
    p = performance(_run())
    assert p["cases"] == 3
    assert abs(p["wall"]["total"] - 0.60) < 1e-9
    assert abs(p["wall"]["max"] - 0.30) < 1e-9
    assert abs(p["wall"]["min"] - 0.10) < 1e-9
    assert p["memory_kb"]["max"] == 2000
    assert p["slowest"][0]["case"] == "g/b"  # the slowest first


def test_renderers_include_performance_and_percent():
    run = _run()
    md, txt, js = to_markdown(run), to_text(run), to_json(run)
    assert "## Performance" in md and "(100%)" in md
    assert "Performance:" in txt
    assert js["performance"]["cases"] == 3


def test_runner_core_reports_performance(tmp_path, py_project):
    ctx, proj = py_project
    for n, (inp, out) in enumerate([("1 2", "3"), ("4 5", "9")]):
        irel = os.path.join(layout.TESTS_DIR, "baseline", "p%d.in" % n)
        erel = os.path.join(layout.EXPECTED_DIR, "baseline", "p%d.out" % n)
        os.makedirs(os.path.dirname(proj.abspath(irel)), exist_ok=True)
        os.makedirs(os.path.dirname(proj.abspath(erel)), exist_ok=True)
        open(proj.abspath(irel), "w").write(inp + "\n")
        open(proj.abspath(erel), "w").write(out + "\n")
        proj.add_case(
            TestCase(
                name="p%d" % n,
                group="baseline",
                manual=True,
                inputs={"stdin": irel},
                expected_output=erel,
            )
        )
    proj.save()
    zip_path = str(tmp_path / "p.zip")
    packaging.build_package(ctx, proj, fmt="zip", out=zip_path)

    extracted = tmp_path / "ex"
    extracted.mkdir()
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(str(extracted))
    (extracted / "sol.py").write_text(open(proj.solution).read())

    r = subprocess.run(
        [sys.executable, str(extracted / "runner" / "morvix_runner.py"), "sol.py", "--all"],
        cwd=str(extracted),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "Performance:" in r.stdout  # the shipped runner prints it too
    assert "passed (" in r.stdout  # with a percentage
