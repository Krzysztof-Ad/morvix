# Tests for morvix/manifest.py.
#
# Covers write_manifest (keys present, private paths excluded) and adopt_manifest
# (round-trip: cases and runners survive, config/project.json is created).

import json
import os
import shutil

import pytest

from morvix.cases import TestCase
from morvix.layout import MANIFEST, PROJECT_FILE
from morvix.manifest import adopt_manifest, write_manifest
from morvix.project import Project, Runner


def _add_case(proj, tmp_path, name="c1", group="baseline"):
    """Attach a minimal TestCase to *proj* (no real input files needed)."""
    case = TestCase(name=name, group=group, manual=True)
    proj.cases.append(case)


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------

def test_write_manifest_required_keys(py_project, tmp_path):
    ctx, proj = py_project
    _add_case(proj, tmp_path)
    proj.runners["q"] = Runner(name="q")
    proj.save()

    path = write_manifest(proj)

    assert os.path.isfile(path)
    with open(path) as f:
        m = json.load(f)

    for key in ("name", "model", "compare", "limits", "cases", "runners"):
        assert key in m, f"manifest missing key: {key}"


def test_write_manifest_excludes_private_paths(py_project, tmp_path):
    ctx, proj = py_project
    proj.reference = str(tmp_path / "ref.py")
    proj.solution = str(tmp_path / "sol.py")
    proj.bruteforce = str(tmp_path / "brute.py")
    proj.save()

    write_manifest(proj)

    manifest_path = os.path.join(proj.root, MANIFEST)
    with open(manifest_path) as f:
        m = json.load(f)

    for key in ("reference", "solution", "bruteforce"):
        assert key not in m, f"manifest should NOT contain '{key}'"


def test_write_manifest_cases_and_runners_content(py_project, tmp_path):
    ctx, proj = py_project
    _add_case(proj, tmp_path, name="sample", group="baseline")
    proj.runners["q"] = Runner(name="q")
    proj.save()

    write_manifest(proj)

    manifest_path = os.path.join(proj.root, MANIFEST)
    with open(manifest_path) as f:
        m = json.load(f)

    case_ids = [f"{c['group']}/{c['name']}" for c in m["cases"]]
    assert "baseline/sample" in case_ids

    assert "q" in m["runners"]
    assert m["runners"]["q"]["name"] == "q"


# ---------------------------------------------------------------------------
# adopt_manifest (round-trip)
# ---------------------------------------------------------------------------

def test_adopt_manifest_creates_project_json(py_project, tmp_path):
    ctx, proj = py_project
    _add_case(proj, tmp_path, name="a1", group="baseline")
    proj.runners["q"] = Runner(name="q")
    proj.save()
    write_manifest(proj)

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    shutil.copy(os.path.join(proj.root, MANIFEST), str(fresh / MANIFEST))

    adopted = adopt_manifest(str(fresh))

    config_path = fresh / PROJECT_FILE
    assert config_path.exists(), "config/project.json should be created by adopt_manifest"


def test_adopt_manifest_preserves_cases(py_project, tmp_path):
    ctx, proj = py_project
    _add_case(proj, tmp_path, name="a1", group="baseline")
    _add_case(proj, tmp_path, name="a2", group="baseline")
    proj.save()
    write_manifest(proj)

    fresh = tmp_path / "fresh2"
    fresh.mkdir()
    shutil.copy(os.path.join(proj.root, MANIFEST), str(fresh / MANIFEST))

    adopted = adopt_manifest(str(fresh))

    adopted_ids = {c.id for c in adopted.cases}
    assert "baseline/a1" in adopted_ids
    assert "baseline/a2" in adopted_ids


def test_adopt_manifest_preserves_runners(py_project, tmp_path):
    ctx, proj = py_project
    proj.runners["q"] = Runner(name="q")
    proj.save()
    write_manifest(proj)

    fresh = tmp_path / "fresh3"
    fresh.mkdir()
    shutil.copy(os.path.join(proj.root, MANIFEST), str(fresh / MANIFEST))

    adopted = adopt_manifest(str(fresh))

    assert "q" in adopted.runners
    assert adopted.runners["q"].name == "q"


def test_project_load_adopts_manifest(py_project, tmp_path):
    """Project.load on a directory that only has morvix.json should adopt it."""
    ctx, proj = py_project
    _add_case(proj, tmp_path, name="b1", group="baseline")
    proj.runners["q"] = Runner(name="q")
    proj.save()
    write_manifest(proj)

    fresh = tmp_path / "fresh4"
    fresh.mkdir()
    shutil.copy(os.path.join(proj.root, MANIFEST), str(fresh / MANIFEST))

    loaded = Project.load(str(fresh))

    assert loaded.name == proj.name
    assert any(c.id == "baseline/b1" for c in loaded.cases)
    assert "q" in loaded.runners
    assert (fresh / PROJECT_FILE).exists()
