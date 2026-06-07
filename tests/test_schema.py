# Schema/tokenizer tests: tokenizing, folding samples, and rendering a draft.
#
# Pure-logic, no project needed. The honesty rule shows up as: a rendered
# generator is valid Python that PRINTS something and never computes an answer.

import ast
import random
import subprocess
import sys

from morvix import schema


def test_tokenize_splits_lines_and_tokens():
    text = "3\n1 2 3\n"
    toks = schema.tokenize_lines(text)
    assert toks == [["3"], ["1", "2", "3"]]


def test_tokenize_empty_text_is_empty():
    assert schema.tokenize_lines("") == []


def test_tokenize_preserves_interior_blank_line():
    toks = schema.tokenize_lines("a\n\nb\n")
    assert toks == [["a"], [], ["b"]]


def test_classify_token_kinds():
    assert schema.classify_token("42") == "int"
    assert schema.classify_token("-7") == "int"
    assert schema.classify_token("3.14") == "float"
    assert schema.classify_token("hello") == "word"
    assert schema.classify_token("a,b") == "other"


def test_classify_records_int_ranges():
    grid = schema.classify("5\n1 9")
    assert grid[0][0].kind == "int"
    assert grid[0][0].lo == 5 and grid[0][0].hi == 5
    assert grid[1][0].lo == 1 and grid[1][1].hi == 9


def test_merge_fixed_lines_widens_int_ranges():
    grids = [schema.classify("1\n2 2"), schema.classify("5\n9 1")]
    s = schema.merge(grids)
    assert len(s.lines) == 2
    head = s.lines[0].tokens[0]
    assert head.kind == "int" and head.lo == 1 and head.hi == 5


def test_merge_count_driven_recovers_repeat_ref():
    # "n then n numbers, one per line": variable line count, count == n.
    samples = ["2\n10\n20", "3\n5\n6\n7", "1\n9"]
    grids = [schema.classify(s) for s in samples]
    s = schema.merge(grids)
    assert s.repeat_line is not None
    assert s.repeat_ref == [0, 0]


def test_render_generator_is_valid_python():
    samples = ["2\n10\n20", "3\n5\n6\n7"]
    s = schema.merge([schema.classify(x) for x in samples])
    src = schema.render_generator(s, "draft")
    # Parses cleanly...
    ast.parse(src)
    # ...and the honesty header is present.
    assert "UNVERIFIED DRAFT" in src
    assert "gen --expected" in src


def test_render_generator_runs_and_prints_something(tmp_path):
    samples = ["2\n10\n20", "3\n5\n6\n7"]
    s = schema.merge([schema.classify(x) for x in samples])
    src = schema.render_generator(s, "draft")
    p = tmp_path / "draft.py"
    p.write_text(src)
    out = subprocess.run([sys.executable, str(p), "1"], capture_output=True, text=True, check=True)
    assert out.stdout.strip() != ""


def test_render_generator_deterministic_for_same_seed(tmp_path):
    s = schema.merge([schema.classify(x) for x in ["2\n10\n20", "3\n5\n6\n7"]])
    src = schema.render_generator(s, "draft")
    p = tmp_path / "draft.py"
    p.write_text(src)

    def run(seed):
        return subprocess.run(
            [sys.executable, str(p), str(seed)], capture_output=True, text=True, check=True
        ).stdout

    assert run(7) == run(7)


def test_render_never_computes_an_answer():
    s = schema.merge([schema.classify("2\n10\n20"), schema.classify("3\n5\n6\n7")])
    src = schema.render_generator(s, "draft")
    for forbidden in ("expected_output", "expected_hash", "expected_exit", "expected_signal"):
        assert forbidden not in src


def test_schema_roundtrip_through_json(tmp_path):
    s = schema.merge([schema.classify("2\n10\n20"), schema.classify("3\n5\n6\n7")])
    path = str(tmp_path / "s.schema.json")
    schema.save_schema(s, path)
    back = schema.load_schema(path)
    assert back.to_dict() == s.to_dict()


def test_tokenspec_roundtrip():
    t = schema.TokenSpec(kind="int", lo=0, hi=9, extrapolated=True)
    assert schema.TokenSpec.from_dict(t.to_dict()) == t


def test_seeded_grid_is_deterministic_purely():
    # classify is pure: same text -> identical grid.
    a = schema.classify("4\n1 2 3 4")
    b = schema.classify("4\n1 2 3 4")
    assert [[(t.kind, t.lo, t.hi) for t in row] for row in a] == [
        [(t.kind, t.lo, t.hi) for t in row] for row in b
    ]
    # rng is unused by classify, but reference it so the import is meaningful.
    assert isinstance(random.Random(0), random.Random)
