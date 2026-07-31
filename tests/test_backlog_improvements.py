# The dogfood backlog: judging config on the CLI, a failure-mode rollup in the
# summary, and two gen --expected suggestions (whitespace masking format bugs,
# and a checker for order-insensitive output). One behaviour per test.

import argparse

from morvix import results, suggestions
from morvix.commands import config_cmd, gen_cmd
from morvix.generators import gen_manual
from morvix.project import Project
from morvix.results import CaseResult, RunResult


class _Rec:
    """A messenger that records what was said, for asserting on suggestions."""

    def __init__(self):
        self.warnings = []
        self.infos = []

    def warning(self, message, hint=None):
        self.warnings.append(message + (" " + hint if hint else ""))

    def info(self, message):
        self.infos.append(message)

    def success(self, message):
        pass

    def plain(self, message=""):
        pass


def _config_args(**over):
    p = argparse.ArgumentParser()
    config_cmd.configure(p)
    argv = []
    for key, value in over.items():
        flag = "--" + key.replace("_", "-")
        if value is True:
            argv.append(flag)
        else:
            argv += [flag, str(value)]
    return p.parse_args(argv)


def _outs(*lines):
    return [ln.encode() for ln in lines]


def _cr(status, **kw):
    c = CaseResult(case_id=kw.pop("cid", "g/x"), group="g", status=status)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# --- item 1: set judging knobs from `config`, no language needed -----------


def test_config_compare_sets_strategy(py_project):
    ctx, proj = py_project
    assert config_cmd.run(ctx, _config_args(compare="exact")) == 0
    assert Project.load(proj.root).compare["strategy"] == "exact"


def test_config_wall_sets_limit(py_project):
    ctx, proj = py_project
    config_cmd.run(ctx, _config_args(wall="2.5"))
    assert Project.load(proj.root).limits["wall"] == 2.5


def test_config_float_epsilon(py_project):
    ctx, proj = py_project
    config_cmd.run(ctx, _config_args(compare="float", epsilon_abs="0.001"))
    cmp = Project.load(proj.root).compare
    assert cmp["strategy"] == "float"
    assert cmp["epsilon_abs"] == 0.001


def test_config_checker_path(py_project, tmp_path):
    ctx, proj = py_project
    chk = tmp_path / "chk.py"
    chk.write_text("import sys; sys.exit(0)\n")
    config_cmd.run(ctx, _config_args(compare="checker", checker=str(chk)))
    cmp = Project.load(proj.root).compare
    assert cmp["strategy"] == "checker"
    assert cmp["checker"] == str(chk)


# --- item 2: warn when whitespace comparison would mask format bugs --------


def test_warn_whitespace_on_spaceless_output(py_project):
    ctx, proj = py_project
    proj.compare["strategy"] = "whitespace"
    ctx.messenger = _Rec()
    suggestions.warn_whitespace_masks_format(ctx, proj, _outs("ABAB", "CDCD", "EF", "GHGH", "IJ"))
    assert any("exact" in w for w in ctx.messenger.warnings)


def test_no_whitespace_warning_when_output_has_spaces(py_project):
    ctx, proj = py_project
    proj.compare["strategy"] = "whitespace"
    ctx.messenger = _Rec()
    suggestions.warn_whitespace_masks_format(
        ctx, proj, _outs("1 2 3", "4 5", "6 7 8", "9 0", "1 1")
    )
    assert not ctx.messenger.warnings


def test_no_whitespace_warning_under_exact(py_project):
    ctx, proj = py_project
    proj.compare["strategy"] = "exact"
    ctx.messenger = _Rec()
    suggestions.warn_whitespace_masks_format(ctx, proj, _outs("ABAB", "CDCD", "EF", "GHGH", "IJ"))
    assert not ctx.messenger.warnings


# --- item 4: suggest a checker for order-insensitive (multi-line) output ---


def test_suggest_checker_when_every_output_is_multiline(py_project):
    ctx, proj = py_project
    proj.compare["strategy"] = "exact"
    ctx.messenger = _Rec()
    suggestions.suggest_checker_for_ordering(ctx, proj, [b"a\nb\nc\n"] * 6)
    assert any("checker" in m for m in ctx.messenger.infos)


def test_no_checker_suggestion_for_single_line_output(py_project):
    ctx, proj = py_project
    proj.compare["strategy"] = "exact"
    ctx.messenger = _Rec()
    suggestions.suggest_checker_for_ordering(ctx, proj, [b"42\n"] * 6)
    assert not any("checker" in m for m in ctx.messenger.infos)


# --- item 3: a failure-mode rollup on the summary --------------------------


def test_failure_breakdown_classifies_each_mode():
    r = RunResult(solution="s")
    r.cases = [
        _cr("pass"),
        _cr("fail", verdict="output differs"),
        _cr("fail", verdict="killed by SIGSEGV", signal="SIGSEGV"),
        _cr("fail", verdict="timed out", timed_out=True),
        _cr("fail", verdict="exit 3", exit_code=3),
        _cr("error", verdict="no expected answer"),
    ]
    bd = dict(r.failure_breakdown())
    assert bd == {"wrong output": 1, "wrong exit": 1, "crashed": 1, "timed out": 1, "error": 1}


def test_no_failure_line_when_all_pass():
    r = RunResult(solution="s")
    r.cases = [_cr("pass"), _cr("pass")]
    assert results.failure_line(r) == ""


def test_failure_line_in_text_export():
    r = RunResult(solution="s")
    r.cases = [
        _cr("fail", signal="SIGSEGV", verdict="killed by SIGSEGV"),
        _cr("fail", verdict="output differs"),
        _cr("fail", verdict="output differs"),
    ]
    txt = results.to_text(r)
    assert "Failures:" in txt
    assert "crashed 1" in txt
    assert "wrong output 2" in txt


# --- item 5: gen --generator coverage summary; deliberate empty case -------


def test_coverage_summary_reports_case_count_and_sizes(py_project):
    ctx, proj = py_project
    gen_manual(ctx, proj, "a", group="g", content="xx")
    gen_manual(ctx, proj, "b", group="g", content="xxxxx")
    line = gen_cmd._coverage_summary(proj, "g")
    assert "2 case(s)" in line
    assert "2" in line and "5" in line


def test_explicit_empty_content_makes_no_warning(py_project):
    ctx, proj = py_project
    ctx.messenger = _Rec()
    gen_cmd._do_manual(ctx, proj, _gen_args(manual="eof", content=""))
    assert not any("empty" in w.lower() for w in ctx.messenger.warnings)


def _gen_args(**over):
    p = argparse.ArgumentParser()
    gen_cmd.configure(p)
    argv = []
    for key, value in over.items():
        flag = "--" + key.replace("_", "-")
        argv += [flag, str(value)]
    return p.parse_args(argv)
