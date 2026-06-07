# Inference tests: recover a count relationship from samples, render a draft,
# and report honest caveats. Inference never runs a program or computes answers.

import ast
import subprocess
import sys

from morvix import inference


class _FakeMessenger:
    def __init__(self):
        self.lines = []

    def info(self, message):
        self.lines.append(("info", message))

    def warning(self, message, hint=None):
        self.lines.append(("warning", message))

    def plain(self, message=""):
        self.lines.append(("plain", message))


class _FakeCtx:
    def __init__(self):
        self.messenger = _FakeMessenger()


def test_infer_count_driven_structure():
    samples = ["2\n10\n20", "3\n5\n6\n7", "1\n9"]
    result = inference.infer_schema(samples)
    assert result.sample_count == 3
    s = result.schema
    # The count integer on line 0 drives the trailing-line count.
    assert s.repeat_ref == [0, 0]
    assert s.repeat_line is not None


def test_infer_records_int_ranges():
    samples = ["1\n2 2", "5\n9 1"]
    result = inference.infer_schema(samples)
    head = result.schema.lines[0].tokens[0]
    assert head.lo == 1 and head.hi == 5


def test_infer_empty_samples_is_honest():
    result = inference.infer_schema([])
    assert result.sample_count == 0
    assert any("empty" in n for n in result.notes)


def test_notes_lead_with_draft_disclaimer():
    result = inference.infer_schema(["2\n10\n20", "3\n5\n6\n7"])
    assert result.notes[0].startswith("DRAFT of input shape")


def test_low_sample_warning():
    result = inference.infer_schema(["2\n10\n20"])
    assert any("guess" in n.lower() for n in result.notes)


def test_rendered_draft_runs_and_prints(tmp_path):
    result = inference.infer_schema(["2\n10\n20", "3\n5\n6\n7"])
    src = inference.render_draft(result, "gen")
    ast.parse(src)
    p = tmp_path / "gen.py"
    p.write_text(src)
    out = subprocess.run([sys.executable, str(p), "1"], capture_output=True, text=True, check=True)
    assert out.stdout.strip() != ""


def test_report_inference_prints_disclaimer_and_no_answer():
    ctx = _FakeCtx()
    result = inference.infer_schema(["2\n10\n20", "3\n5\n6\n7", "1\n9"])
    inference.report_inference(ctx, result)
    text = " ".join(m for _, m in ctx.messenger.lines)
    assert "DRAFT of input shape" in text
    assert "gen --expected" in text
    # Nothing here should ever mention computing an answer.
    for forbidden in ("expected_output", "expected_hash"):
        assert forbidden not in text


def test_report_inference_empty_warns():
    ctx = _FakeCtx()
    inference.report_inference(ctx, inference.infer_schema([]))
    kinds = [k for k, _ in ctx.messenger.lines]
    assert "warning" in kinds


def test_try_write_grammar_for_count_driven():
    result = inference.infer_schema(["2\n10\n20", "3\n5\n6\n7", "1\n9"])
    gram = inference.try_write_grammar(result, "gram")
    assert gram is not None
    assert "repeat(n)" in gram
    assert "UNVERIFIED DRAFT" in gram


def test_try_write_grammar_none_for_irregular():
    # Fixed-shape, no variable repeat -> no clean grammar mapping.
    result = inference.infer_schema(["1 2 3", "4 5 6"])
    assert inference.try_write_grammar(result) is None


def test_inference_does_not_run_anything(monkeypatch):
    # Guard: infer_schema must not shell out.
    def _boom(*a, **k):
        raise AssertionError("inference must not run a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    inference.infer_schema(["2\n10\n20", "3\n5\n6\n7"])
