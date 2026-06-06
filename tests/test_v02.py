# Tests for the 0.2 improvements: the hidden .morvix/ layout + legacy migration,
# the generator scaffold, and the degenerate-output warning.

import io
import json
import os
import subprocess
import sys

from rich.console import Console

from morvix import generators, layout
from morvix.cases import TestCase
from morvix.context import Context
from morvix.judge import judge, select_cases
from morvix.project import Project, ensure_gitignore

NOOP_PY = "import sys\nsys.stdin.read()\n"  # reads input, prints nothing
SUM_ALL_PY = "import sys\nprint(sum(int(x) for x in sys.stdin.read().split()))\n"


def _capturing_ctx(root):
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, width=100)
    ctx = Context.create(str(root), interactive=False, console=console)
    return ctx, buf


# --- .morvix/ layout ---


def test_create_uses_hidden_state_dir(tmp_path):
    Project.create(str(tmp_path), "t")
    assert (tmp_path / ".morvix" / "config" / "project.json").exists()
    # The project root stays clean - no bare config/ or tests/ dirs.
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / "tests").exists()


def test_legacy_flat_project_migrates_on_load(tmp_path):
    # Build a pre-0.2 flat project by hand.
    (tmp_path / "config").mkdir()
    (tmp_path / "tests" / "baseline").mkdir(parents=True)
    (tmp_path / "expected" / "baseline").mkdir(parents=True)
    (tmp_path / "sol.py").write_text(SUM_ALL_PY)
    (tmp_path / "config" / "project.json").write_text(
        json.dumps(
            {
                "name": "old",
                "language": "python",
                "model": "stdio",
                "solution": str(tmp_path / "sol.py"),
                "reference": str(tmp_path / "sol.py"),
            }
        )
    )
    (tmp_path / "config" / "cases.json").write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "name": "a",
                        "group": "baseline",
                        "manual": True,
                        "inputs": {"stdin": "tests/baseline/a.in"},
                        "expected_output": "expected/baseline/a.out",
                    }
                ]
            }
        )
    )
    (tmp_path / "tests" / "baseline" / "a.in").write_text("1 2 3\n")
    (tmp_path / "expected" / "baseline" / "a.out").write_text("6\n")

    proj = Project.load(str(tmp_path))

    # Migrated into .morvix/, old flat dirs gone.
    assert (tmp_path / ".morvix" / "config" / "project.json").exists()
    assert not (tmp_path / "config").exists()
    assert not (tmp_path / "tests").exists()
    # Case paths were rewritten and still resolve.
    case = proj.cases[0]
    assert case.inputs["stdin"].startswith(".morvix" + os.sep) or case.inputs["stdin"].startswith(
        ".morvix/"
    )
    assert os.path.exists(case.input_abspath(str(tmp_path)))
    # And the migrated project still judges correctly.
    run = judge(proj, proj.solution, "python", select_cases(proj))
    assert run.all_passed


# --- .gitignore ---


def test_init_writes_gitignore(tmp_path, make_ctx):
    from morvix import registry

    ctx = make_ctx(tmp_path)
    registry.safe_dispatch(ctx, ["init", "--name", "g", "--language", "python"])
    gi = tmp_path / ".gitignore"
    assert gi.exists()
    body = gi.read_text()
    assert ".morvix/results/" in body
    assert ".morvix/solutions/" in body


def test_ensure_gitignore_never_clobbers(tmp_path):
    existing = tmp_path / ".gitignore"
    existing.write_text("my own rules\n")
    created = ensure_gitignore(str(tmp_path))
    assert created is False
    assert existing.read_text() == "my own rules\n"  # left untouched


# --- flat package + receiver-with-morvix adoption ---


def test_receiver_with_morvix_adopts_flat_package(tmp_path, make_ctx):
    import zipfile

    from morvix import packaging

    sol = tmp_path / "sol.py"
    sol.write_text(SUM_ALL_PY)
    proj = Project.create(str(tmp_path), "share")
    proj.language = "python"
    proj.model = "stdio"
    proj.solution = str(sol)
    for name, inp, out in [("a", "1 2 3", "6"), ("b", "10 20", "30")]:
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
    proj.save()
    ctx = make_ctx(tmp_path)
    ctx.project = proj
    out_zip = str(tmp_path / "pkg.zip")
    packaging.build_package(ctx, proj, fmt="zip", out=out_zip)

    # Receiver unpacks the (flat) package elsewhere and opens it with Morvix.
    recv = tmp_path / "recv"
    recv.mkdir()
    with zipfile.ZipFile(out_zip) as z:
        z.extractall(str(recv))
    assert (recv / "morvix.json").exists()  # flat, visible
    assert not (recv / ".morvix").exists()

    loaded = Project.load(str(recv))  # adopts/migrates into .morvix/
    assert len(loaded.cases) == 2
    c = loaded.cases[0]
    assert os.path.exists(c.input_abspath(str(recv)))
    assert os.path.exists(c.expected_output_abspath(str(recv)))

    # The receiver drops in their own solution and re-runs - it judges cleanly.
    (recv / "sol.py").write_text(SUM_ALL_PY)
    run = judge(loaded, str(recv / "sol.py"), "python", select_cases(loaded))
    assert run.all_passed


# --- generator scaffold ---


def test_new_generator_scaffold(tmp_path):
    proj = Project.create(str(tmp_path), "t")
    ctx, _ = _capturing_ctx(tmp_path)
    rel = generators.new_generator(ctx, proj, "mygen")
    path = proj.abspath(rel)
    assert os.path.exists(path)
    assert rel.startswith(layout.GENERATORS_DIR)
    text = open(path).read()
    assert "build_input" in text
    # The scaffold actually runs and prints a reproducible input.
    out1 = subprocess.run([sys.executable, path, "1"], capture_output=True, text=True).stdout
    out2 = subprocess.run([sys.executable, path, "1"], capture_output=True, text=True).stdout
    assert out1 and out1 == out2


# --- degenerate-output warning ---


def test_warns_when_expected_outputs_are_empty(tmp_path):
    sol = tmp_path / "noop.py"
    sol.write_text(NOOP_PY)  # never prints anything
    proj = Project.create(str(tmp_path), "t")
    proj.language = "python"
    proj.model = "stdio"
    proj.solution = str(sol)
    proj.save()
    ctx, buf = _capturing_ctx(tmp_path)
    ctx.project = proj

    generators.gen_random(ctx, proj, "array", 6, 1, "baseline", {"count": 2, "hi": 50})
    proj.save()
    generators.gen_expected(ctx, proj)

    out = buf.getvalue()
    assert "empty" in out.lower()
    assert "gen --new-generator" in out
