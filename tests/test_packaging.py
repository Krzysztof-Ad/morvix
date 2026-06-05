# Tests for morvix/packaging.py and the Receiver (runner) path.
#
# build_package produces a zip that contains exactly the right files and none
# of the private ones. The Receiver path unpacks the zip, drops in a solution
# and drives runner/morvix_runner.py directly, expecting a clean exit and a
# "passed" summary in stdout.

import os
import subprocess
import sys
import zipfile

import pytest

from morvix.cases import TestCase, default_expected_relpath, default_input_relpath
from morvix.packaging import build_package


def _add_case(proj, name, inp_data, exp_data, group="baseline"):
    inp_rel = default_input_relpath(group, name)
    exp_rel = default_expected_relpath(group, name)
    for rel, data in [(inp_rel, inp_data), (exp_rel, exp_data)]:
        path = os.path.join(proj.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
    case = TestCase(
        name=name,
        group=group,
        manual=True,
        inputs={"stdin": inp_rel},
        expected_output=exp_rel,
    )
    proj.add_case(case)


def _build_zip(ctx, proj, tmp_path):
    out = str(tmp_path / "pkg.zip")
    return build_package(ctx, proj, fmt="zip", out=out)


class TestBuildPackageZipContents:
    """build_package(fmt='zip') produces the right archive entries."""

    def test_required_entries_present(self, py_project, tmp_path):
        ctx, proj = py_project
        _add_case(proj, "c1", "5 10\n", "15\n")
        _add_case(proj, "c2", "0\n", "0\n")
        proj.save()

        zip_path = _build_zip(ctx, proj, tmp_path)

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()

        # The manifest lives under .morvix/; run.sh sits at the archive root.
        assert ".morvix/morvix.json" in names
        assert "run.sh" in names

        # At least one tests/ entry and at least one expected/ entry (under .morvix/).
        assert any(n.startswith(".morvix/tests/") for n in names), \
            "zip must contain at least one .morvix/tests/ entry"
        assert any(n.startswith(".morvix/expected/") for n in names), \
            "zip must contain at least one .morvix/expected/ entry"

    def test_private_paths_absent(self, py_project, tmp_path):
        ctx, proj = py_project
        _add_case(proj, "c1", "1 2\n", "3\n")
        proj.save()

        zip_path = _build_zip(ctx, proj, tmp_path)

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()

        # The solution source and the private config dir must never travel.
        for entry in names:
            assert not entry.startswith(".morvix/solutions/"), \
                f"solutions/ must not appear in package; found {entry!r}"
            assert not entry.startswith(".morvix/config/"), \
                f"config/ must not appear in package; found {entry!r}"


class TestReceiverPath:
    """Unpack a zip and run runner/morvix_runner.py as a Receiver would."""

    def test_runner_passes_correct_solution(self, py_project, tmp_path):
        ctx, proj = py_project
        _add_case(proj, "add", "3 4\n", "7\n")
        _add_case(proj, "mul", "6\n", "6\n")  # sum of one int
        proj.save()

        zip_path = _build_zip(ctx, proj, tmp_path)

        extracted = tmp_path / "recv"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(str(extracted))

        # Place a correct solution in the extracted directory.
        sol = extracted / "sol.py"
        sol.write_text(
            "import sys\n"
            "d = sys.stdin.read().split()\n"
            "print(sum(int(x) for x in d))\n"
        )

        runner = str(extracted / ".morvix" / "runner" / "morvix_runner.py")
        result = subprocess.run(
            [sys.executable, runner, "sol.py", "--all"],
            cwd=str(extracted),
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, \
            f"runner exited {result.returncode}; stderr: {result.stderr}"
        assert "passed" in result.stdout, \
            f"'passed' not found in stdout: {result.stdout!r}"

    def test_runner_fails_wrong_solution(self, py_project, tmp_path):
        ctx, proj = py_project
        _add_case(proj, "basic", "1 2 3\n", "6\n")
        proj.save()

        zip_path = _build_zip(ctx, proj, tmp_path)

        extracted = tmp_path / "recv2"
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(str(extracted))

        # A solution that always prints the wrong answer.
        sol = extracted / "wrong.py"
        sol.write_text("print(-999)\n")

        runner = str(extracted / ".morvix" / "runner" / "morvix_runner.py")
        result = subprocess.run(
            [sys.executable, runner, "wrong.py", "--all"],
            cwd=str(extracted),
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, \
            "runner should exit non-zero when the solution produces wrong output"
        assert "failed" in result.stdout or "FAIL" in result.stdout, \
            f"expected failure indication in stdout: {result.stdout!r}"
