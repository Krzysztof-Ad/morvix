# Tests for morvix/pack.py: generator-pack export/import.
#
# A pack is a .zip of generator/grammar FILES. Export then import must round-trip
# those files. Crucially, import is honest: it writes files only - it never runs
# pack code, never creates a case, and never sets any expected_* field. A stray
# "*.py" dressed up as a case is still only written as a generator file.

import os
import zipfile

from morvix import layout, pack
from morvix.cases import TestCase


def _write_generator(proj, name, text):
    """Drop a generator/grammar file under .morvix/generators and return its relpath."""
    rel = os.path.join(layout.GENERATORS_DIR, name)
    path = proj.abspath(rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return rel


GEN_PY = "import random, sys\nn = int(sys.argv[1]) if len(sys.argv) > 1 else 5\nprint(n)\n"
GRAM = "start: int(1..100)\n"


def test_export_then_import_roundtrip(py_project, tmp_path):
    ctx, proj = py_project
    _write_generator(proj, "mygen.py", GEN_PY)
    _write_generator(proj, "mygram.gram", GRAM)

    out = str(tmp_path / "pack.zip")
    result = pack.export_pack(proj, out)
    assert result == out
    assert os.path.exists(out)

    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert pack.PACK_MANIFEST in names
    assert "generators/mygen.py" in names
    assert "generators/mygram.gram" in names

    # Import into a fresh project dir and confirm the files come back verbatim.
    dest_ctx, dest = _fresh_project(tmp_path / "dest")
    report = pack.import_pack(dest, out)
    assert sorted(report.imported) == ["mygen.py", "mygram.gram"]

    got_py = dest.abspath(os.path.join(layout.GENERATORS_DIR, "mygen.py"))
    got_gram = dest.abspath(os.path.join(layout.GENERATORS_DIR, "mygram.gram"))
    with open(got_py, encoding="utf-8") as f:
        assert f.read() == GEN_PY
    with open(got_gram, encoding="utf-8") as f:
        assert f.read() == GRAM


def test_export_selected_names_only(py_project, tmp_path):
    ctx, proj = py_project
    _write_generator(proj, "a.py", "print('a')\n")
    _write_generator(proj, "b.py", "print('b')\n")

    out = pack.export_pack(proj, str(tmp_path / "sel.zip"), names=["a"])
    with zipfile.ZipFile(out) as zf:
        members = [n for n in zf.namelist() if n.startswith("generators/")]
    assert members == ["generators/a.py"]


def test_import_pack_creates_no_cases_and_sets_no_expected(py_project, tmp_path):
    ctx, proj = py_project
    _write_generator(proj, "mygen.py", GEN_PY)
    out = pack.export_pack(proj, str(tmp_path / "p.zip"))

    dest_ctx, dest = _fresh_project(tmp_path / "dest")
    before = len(dest.cases)
    pack.import_pack(dest, out)

    # No cases were created and nothing carries an expectation.
    assert len(dest.cases) == before
    for case in dest.cases:
        assert case.expected_output is None
        assert case.expected_hash is None
        assert case.expected_exit is None
        assert case.expected_signal is None
        assert case.expected_files == {}


def test_stray_case_like_py_is_only_a_generator_file(py_project, tmp_path):
    # Build a hand-rolled pack zip whose payload tries to look like a test case:
    # a "case"-named .py at the generators root, plus a bundled answer file.
    out = str(tmp_path / "evil.zip")
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(pack.PACK_MANIFEST, '{"format": "morvix-pack/1", "files": []}\n')
        zf.writestr("generators/case_0001.py", "print('I am not a case')\n")
        zf.writestr("generators/case_0001.out", "42\n")  # a planted "answer"

    dest_ctx, dest = _fresh_project(tmp_path / "dest")
    report = pack.import_pack(dest, out)

    # The .py landed as a generator file; it was NOT run and is NOT a case.
    assert report.imported == ["case_0001.py"]
    assert len(dest.cases) == 0
    landed = dest.abspath(os.path.join(layout.GENERATORS_DIR, "case_0001.py"))
    assert os.path.exists(landed)

    # The planted answer was dropped, never written anywhere under generators/.
    assert "generators/case_0001.out" in report.dropped_answers
    assert not os.path.exists(dest.abspath(os.path.join(layout.GENERATORS_DIR, "case_0001.out")))


def test_import_skips_existing_without_force(py_project, tmp_path):
    ctx, proj = py_project
    _write_generator(proj, "mygen.py", GEN_PY)
    out = pack.export_pack(proj, str(tmp_path / "p.zip"))

    dest_ctx, dest = _fresh_project(tmp_path / "dest")
    _write_generator(dest, "mygen.py", "print('mine')\n")  # pre-existing

    report = pack.import_pack(dest, out)
    assert report.imported == []
    assert report.skipped == ["mygen.py"]
    # The local file was left untouched.
    with open(dest.abspath(os.path.join(layout.GENERATORS_DIR, "mygen.py")), encoding="utf-8") as f:
        assert f.read() == "print('mine')\n"

    # With force, it is overwritten.
    report2 = pack.import_pack(dest, out, force=True)
    assert report2.imported == ["mygen.py"]
    with open(dest.abspath(os.path.join(layout.GENERATORS_DIR, "mygen.py")), encoding="utf-8") as f:
        assert f.read() == GEN_PY


def test_import_rejects_non_zip(py_project, tmp_path):
    from morvix.errors import UserError

    ctx, proj = py_project
    junk = tmp_path / "not.zip"
    junk.write_text("hello, not a zip")

    import pytest

    with pytest.raises(UserError):
        pack.import_pack(proj, str(junk))


def test_import_ignores_zip_slip(py_project, tmp_path):
    out = str(tmp_path / "slip.zip")
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("generators/../../escape.py", "print('escape')\n")

    dest_ctx, dest = _fresh_project(tmp_path / "dest")
    report = pack.import_pack(dest, out)
    assert report.imported == []
    assert "generators/../../escape.py" in report.ignored
    # Nothing escaped the project.
    assert not os.path.exists(os.path.join(str(tmp_path), "escape.py"))


def _fresh_project(root):
    """A second, empty python project so import has somewhere clean to land."""
    from morvix.context import Context
    from morvix.project import Project
    from morvix.theme import make_console

    os.makedirs(str(root), exist_ok=True)
    proj = Project.create(str(root), "dest")
    ctx = Context.create(str(root), interactive=False, console=make_console(force_plain=True))
    ctx.project = proj
    return ctx, proj


# A TestCase import keeps the honesty-grep guard meaningful (the module never
# constructs one with an expectation); referenced so linters keep the import.
_ = TestCase
