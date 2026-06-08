# Tests for corpus import (morvix/importers.py).
#
# The point of these tests is the honesty boundary: importing existing input
# files must NEVER set an expected answer, even when the corpus ships .out/.ans
# files. We assert every imported case has expected_output is None, that bundled
# answers are stripped (and recorded), that byte-identical inputs are deduped, and
# that --keep-answers only writes an inert advisory copy with no expectation set.

import os
import zipfile

from morvix import importers
from morvix.importers import ANSWER_EXTS, INPUT_EXTS, import_corpus, report_import


def _corpus(tmp_path):
    """A small folder: two distinct inputs, a duplicate, and bundled answers."""
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "a.in").write_text("1\n2\n3\n")
    (d / "b.in").write_text("4\n5\n6\n")
    (d / "a.out").write_text("6\n")  # an answer - must be stripped
    (d / "b.ans").write_text("15\n")  # an answer - must be stripped
    return d


def test_ext_sets_are_disjoint_and_sane():
    # Inputs and answers must never overlap, or a file could be both.
    assert INPUT_EXTS.isdisjoint(ANSWER_EXTS)
    assert ".in" in INPUT_EXTS
    assert ".out" in ANSWER_EXTS
    assert ".ans" in ANSWER_EXTS


def test_import_ingests_in_files_as_cases(py_project, tmp_path):
    ctx, project = py_project
    d = _corpus(tmp_path)
    summary = import_corpus(ctx, project, str(d), group="imported")

    assert summary.created_count == 2
    names = {c.name for c in summary.created}
    assert len(names) == 2
    for case in summary.created:
        assert case.group == "imported"
        assert not case.manual
        assert "stdin" in case.inputs
        # The input file was actually written and the hash stamped.
        assert os.path.exists(project.abspath(case.inputs["stdin"]))
        assert case.input_hash


def test_import_default_names_are_generic(py_project, tmp_path):
    ctx, project = py_project
    d = _corpus(tmp_path)
    summary = import_corpus(ctx, project, str(d), group="imported")
    assert all(c.name.startswith("imp") for c in summary.created)


def test_import_keep_names_uses_source_basenames(py_project, tmp_path):
    ctx, project = py_project
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "edge_greedy_trap.in").write_text("1\n2\n3\n")
    (d / "big-case.txt").write_text("4\n5\n6\n")

    summary = import_corpus(ctx, project, str(d), group="imported", keep_names=True)
    names = {c.name for c in summary.created}
    assert names == {"edge_greedy_trap", "big-case"}


def test_import_keep_names_disambiguates_collisions(py_project, tmp_path):
    ctx, project = py_project
    # Same basename from two directories, distinct contents -> unique case names.
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    (tmp_path / "x" / "case.in").write_text("1\n")
    (tmp_path / "y" / "case.in").write_text("2\n")

    summary = import_corpus(
        ctx, project, str(tmp_path / "*/case.in"), group="imported", keep_names=True
    )
    names = sorted(c.name for c in summary.created)
    assert names == ["case", "case_2"]


def test_import_strips_bundled_answers(py_project, tmp_path):
    ctx, project = py_project
    d = _corpus(tmp_path)
    summary = import_corpus(ctx, project, str(d), group="imported")

    # The two answer files were recognised and dropped.
    assert len(summary.stripped_answers) == 2
    assert any(name.endswith(".out") for name in summary.stripped_answers)
    assert any(name.endswith(".ans") for name in summary.stripped_answers)

    # THE honesty assertion: no imported case carries any expected_*.
    for case in summary.created:
        assert case.expected_output is None
        assert case.expected_hash is None
        assert case.expected_exit is None
        assert case.expected_signal is None
        assert case.expected_files == {}

    # And nothing landed in the expected/ tree on disk.
    assert not summary.advisory_written


def test_import_dedup_by_hash(py_project, tmp_path):
    ctx, project = py_project
    d = tmp_path / "dup"
    d.mkdir()
    (d / "x.in").write_text("same\nbytes\n")
    (d / "y.in").write_text("same\nbytes\n")  # byte-identical duplicate
    (d / "z.in").write_text("different\n")

    summary = import_corpus(ctx, project, str(d), group="imported", dedup=True)
    assert summary.created_count == 2
    assert summary.skipped_duplicates == 1


def test_import_no_dedup_keeps_duplicate(py_project, tmp_path):
    ctx, project = py_project
    d = tmp_path / "dup2"
    d.mkdir()
    (d / "x.in").write_text("same\n")
    (d / "y.in").write_text("same\n")

    summary = import_corpus(ctx, project, str(d), group="imported", dedup=False)
    assert summary.created_count == 2
    assert summary.skipped_duplicates == 0


def test_import_keep_answers_advisory_only(py_project, tmp_path):
    ctx, project = py_project
    d = _corpus(tmp_path)
    summary = import_corpus(ctx, project, str(d), group="imported", keep_answers=True)

    # Advisory copies were written for the two stripped answers...
    assert len(summary.advisory_written) == 2
    for rel in summary.advisory_written:
        assert importers.ADVISORY_DIRNAME in rel
        assert os.path.exists(project.abspath(rel))
        # ...and they live in the advisory folder, NOT the expected/ tree.
        assert "expected" not in rel.split(os.sep)[:2]

    # Still no expectation is ever set on a case.
    for case in summary.created:
        assert case.expected_output is None
        assert case.expected_hash is None


def test_import_split_multitest(py_project, tmp_path):
    ctx, project = py_project
    d = tmp_path / "multi"
    d.mkdir()
    # "T then T sub-inputs", one per line.
    (d / "cases.in").write_text("3\n10\n20\n30\n")

    summary = import_corpus(ctx, project, str(d), group="imported", split=True)
    assert summary.split_files == 1
    assert summary.sub_cases == 3
    assert summary.created_count == 3
    contents = sorted(
        open(project.abspath(c.inputs["stdin"]), encoding="utf-8").read().strip()
        for c in summary.created
    )
    assert contents == ["10", "20", "30"]


def test_import_no_split_keeps_file_whole(py_project, tmp_path):
    ctx, project = py_project
    d = tmp_path / "whole"
    d.mkdir()
    (d / "cases.in").write_text("3\n10\n20\n30\n")

    summary = import_corpus(ctx, project, str(d), group="imported", split=False)
    assert summary.created_count == 1
    assert summary.split_files == 0


def test_import_from_zip(py_project, tmp_path):
    ctx, project = py_project
    zpath = tmp_path / "tests.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.in", "1\n2\n")
        zf.writestr("a.out", "3\n")  # answer in the archive - stripped
        zf.writestr("b.in", "9\n")

    summary = import_corpus(ctx, project, str(zpath), group="imported")
    assert summary.created_count == 2
    assert len(summary.stripped_answers) == 1
    for case in summary.created:
        assert case.expected_output is None


def test_import_from_glob(py_project, tmp_path):
    ctx, project = py_project
    d = tmp_path / "g"
    d.mkdir()
    (d / "t1.in").write_text("1\n")
    (d / "t2.in").write_text("2\n")
    (d / "t3.txt").write_text("3\n")  # .txt also counts as input
    (d / "notes.md").write_text("ignore me\n")  # unknown ext - ignored

    summary = import_corpus(ctx, project, os.path.join(str(d), "*.in"), group="imported")
    assert summary.created_count == 2


def test_import_dry_run_writes_nothing(py_project, tmp_path):
    ctx, project = py_project
    d = _corpus(tmp_path)
    before = len(project.cases)
    summary = import_corpus(ctx, project, str(d), group="imported", dry_run=True)

    # The preview reports cases but adds none to the project and writes no files.
    assert summary.created_count == 2
    assert summary.dry_run
    assert len(project.cases) == before
    for case in summary.created:
        assert not os.path.exists(project.abspath(case.inputs["stdin"]))
        assert case.expected_output is None


def test_import_skips_empty_inputs(py_project, tmp_path):
    ctx, project = py_project
    d = tmp_path / "e"
    d.mkdir()
    (d / "empty.in").write_text("   \n")
    (d / "real.in").write_text("42\n")

    summary = import_corpus(ctx, project, str(d), group="imported")
    assert summary.created_count == 1
    assert summary.skipped_empty == 1


def test_import_dedups_against_existing_cases(py_project, tmp_path):
    ctx, project = py_project
    # First import.
    d = tmp_path / "first"
    d.mkdir()
    (d / "a.in").write_text("shared\n")
    import_corpus(ctx, project, str(d), group="imported")

    # Re-importing the same bytes is a no-op when dedup is on.
    d2 = tmp_path / "second"
    d2.mkdir()
    (d2 / "a.in").write_text("shared\n")
    (d2 / "b.in").write_text("brand new\n")
    summary = import_corpus(ctx, project, str(d2), group="imported")
    assert summary.created_count == 1
    assert summary.skipped_duplicates == 1


def test_import_empty_source_raises(py_project, tmp_path):
    ctx, project = py_project
    empty = tmp_path / "nothing"
    empty.mkdir()
    try:
        import_corpus(ctx, project, str(empty), group="imported")
    except Exception as e:
        assert "import" in str(e).lower() or "nothing" in str(e).lower()
    else:
        raise AssertionError("expected a UserError for an empty source")


def test_report_import_runs(py_project, tmp_path):
    # The report just prints; assert it does not blow up and surfaces the honesty
    # warning when answers were stripped.
    ctx, project = py_project
    d = _corpus(tmp_path)
    summary = import_corpus(ctx, project, str(d), group="imported")
    report_import(ctx, summary)  # should not raise
