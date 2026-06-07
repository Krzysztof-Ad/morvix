# Tests for execgen: turning a generated text blob into args/file case shapes.
#
# The load-bearing invariant is honesty: these helpers set INPUTS only (argv,
# named input files, and the NAMES of output files to capture later) and never
# any expected answer. gen_expected is the only thing that freezes answers.

import os

from morvix import execgen

# --- args_from_text ---------------------------------------------------------


def test_args_from_text_line_split():
    text = "3\n7\nhello world\n"
    assert execgen.args_from_text(text) == ["3", "7", "hello world"]


def test_args_from_text_single_line_whitespace_split():
    assert execgen.args_from_text("3 7 12") == ["3", "7", "12"]


def test_args_from_text_skips_blank_lines():
    text = "a\n\n  \nb\n"
    assert execgen.args_from_text(text) == ["a", "b"]


# --- split_named_files ------------------------------------------------------


def test_split_named_files_roundtrip():
    files = {"input.txt": "1 2 3", "config.ini": "mode=fast"}
    blob = "\n".join(f"=== {name} ===\n{content}" for name, content in files.items())
    out = execgen.split_named_files(blob, ["input.txt", "config.ini"])
    assert out == files


def test_split_named_files_single_unmarked_blob():
    out = execgen.split_named_files("just some content\nline two", ["input.txt"])
    assert out == {"input.txt": "just some content\nline two"}


def test_split_named_files_fills_missing_keys_empty():
    blob = "=== a ===\nhello"
    out = execgen.split_named_files(blob, ["a", "b"])
    assert out == {"a": "hello", "b": ""}


# --- write_args_case --------------------------------------------------------


def test_write_args_case_sets_args_and_no_expected(py_project):
    _, proj = py_project
    case = execgen.write_args_case(proj, "argv", "a0", ["5", "9"])
    assert case.args == ["5", "9"]
    assert case.inputs == {}
    assert case.manual is False
    assert "model:args" in case.tags
    # Honesty: nothing expected is ever set here.
    assert case.expected_output is None
    assert case.expected_hash is None
    assert case.expected_exit is None
    assert case.expected_signal is None
    assert case.expected_files == {}
    # It is registered on the project.
    assert proj.get_case("argv/a0") is case


# --- write_files_case -------------------------------------------------------


def test_write_files_case_writes_inputs_records_out_files_no_expected(py_project):
    _, proj = py_project
    files = {"input.txt": "1 2 3", "data.txt": "x y z"}
    case = execgen.write_files_case(proj, "fm", "f0", files, ["output.txt"])

    # Each named input file is written under tests/ and keyed by its logical name.
    assert set(case.inputs) == {"input.txt", "data.txt"}
    for logical, content in files.items():
        rel = case.inputs[logical]
        assert os.path.basename(rel) == logical
        with open(proj.abspath(rel), encoding="utf-8") as f:
            assert f.read() == content

    # The output file NAMES to capture later are recorded, but no expected
    # content of any kind is set.
    assert case.provenance.get("out_files") == ["output.txt"]
    assert "model:file" in case.tags
    assert case.expected_files == {}
    assert case.expected_output is None
    assert case.expected_hash is None
    assert case.expected_exit is None
    assert case.expected_signal is None


def test_write_files_case_empty_out_files_records_nothing(py_project):
    _, proj = py_project
    case = execgen.write_files_case(proj, "fm", "f1", {"in": "data"}, [])
    # make_record drops None, so an empty out_files list leaves no key behind.
    assert "out_files" not in case.provenance


def test_write_files_case_stamps_input_hash(py_project):
    _, proj = py_project
    case = execgen.write_files_case(proj, "fm", "f2", {"in.txt": "payload"}, [])
    assert case.input_hash is not None
    assert len(case.input_hash) == 64  # sha256 hex
