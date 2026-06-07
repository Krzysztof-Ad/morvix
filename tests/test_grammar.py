# Tests for the declarative grammar sampler (grammar.py).

import re

import pytest

from morvix import grammar
from morvix.grammar import GrammarError


def test_count_threading_n_then_n_numbers():
    src = 'start: int(3..3) as n "\\n" repeat(n) { int(0..9) } sep " " "\\n"'
    out = grammar.sample_source(src, seed=1)
    lines = out.splitlines()
    assert lines[0] == "3"
    nums = lines[1].split(" ")
    assert len(nums) == 3  # the body repeated exactly n times


def test_grid_rows_cols_consistent():
    src = 'start: int(2..2) as r " " int(4..4) as c "\\n" repeat(r) { repeat(c) { char(".#") } "\\n" }'
    out = grammar.sample_source(src, seed=7)
    header, *rows = out.splitlines()
    r, c = (int(x) for x in header.split())
    assert len(rows) == r
    assert all(len(row) == c and set(row) <= {".", "#"} for row in rows)


def test_bound_arithmetic_expr():
    # hi depends on a bound value via arithmetic.
    src = 'start: int(5..5) as n " " int(n..n*2) as k'
    out = grammar.sample_source(src, seed=3)
    n_str, k_str = out.split(" ")
    assert 5 <= int(k_str) <= 10


def test_param_pins_bound_name():
    src = 'start: int(1..1000000) as n "\\n" repeat(n) { int(0..9) } sep " "'
    out = grammar.sample_source(src, seed=1, params={"n": 4})
    assert out.splitlines()[0] == "4"
    assert len(out.splitlines()[1].split(" ")) == 4


def test_deterministic_same_seed():
    src = 'start: repeat(10) { int(0..1000000) } sep " "'
    assert grammar.sample_source(src, seed=42) == grammar.sample_source(src, seed=42)


def test_let_binds_silently_and_drives_repeat():
    # A leading count never appears in the output, but still drives the body.
    src = 'start: let k = int(3..3) repeat(k) { char("a") } "\\n"'
    out = grammar.sample_source(src, seed=1)
    assert out == "aaa\n"  # exactly k chars, no count printed


def test_let_expression_form_computes_from_binds():
    src = 'start: int(2..2) as n "\\n" let m = n * 3 repeat(m) { char("x") } "\\n"'
    out = grammar.sample_source(src, seed=1)
    lines = out.splitlines()
    assert lines[0] == "2"
    assert len(lines[1]) == 6  # m = n * 3


def test_let_is_overridden_by_param():
    src = 'start: let k = int(1..9) repeat(k) { char("a") }'
    out = grammar.sample_source(src, seed=1, params={"k": 2})
    assert out == "aa"


def test_different_seed_differs():
    src = 'start: repeat(20) { int(0..1000000) } sep " "'
    assert grammar.sample_source(src, seed=1) != grammar.sample_source(src, seed=2)


def test_oneof_picks_one():
    src = 'start: oneof { "a" | "b" | "c" }'
    seen = {grammar.sample_source(src, seed=s) for s in range(30)}
    assert seen <= {"a", "b", "c"} and len(seen) >= 2


def test_str_and_float_terminals():
    src = 'start: str(5, "ab") " " float(0.0..1.0, 2)'
    s, f = grammar.sample_source(src, seed=1).split(" ")
    assert len(s) == 5 and set(s) <= {"a", "b"}
    assert re.fullmatch(r"0\.\d{2}|1\.00", f)


def test_calls_another_rule():
    src = "start: pair pair\npair: int(1..1) int(2..2)"
    assert grammar.sample_source(src, seed=1) == "1212"


def test_error_unknown_name():
    with pytest.raises(GrammarError):
        grammar.sample_source("start: repeat(missing) { int(0..1) }", seed=1)


def test_error_bad_syntax_reports_line():
    with pytest.raises(GrammarError) as e:
        grammar.parse("start: int(1..2)\nbad: int(3..", "<t>")
    assert e.value.line == 2


def test_error_empty_grammar():
    with pytest.raises(GrammarError):
        grammar.parse("# only comments\n", "<t>")


def test_size_guard_runaway_repeat():
    # n bound huge then repeated; the byte cap must trip rather than hang/OOM.
    src = 'start: int(1..1) as n repeat(100000000) { str(1000, "x") }'
    with pytest.raises(GrammarError):
        grammar.sample_source(src, seed=1)


# --- integration with the project pipeline ---


def test_new_grammar_writes_starter(py_project):
    from morvix import generators

    ctx, proj = py_project
    rel = generators.new_grammar(ctx, proj, "mygram")
    path = proj.abspath(rel)
    assert path.endswith(".gram")
    text = open(path).read()
    assert "start:" in text  # a usable starter rule
    # And the starter actually samples without error.
    grammar.sample_source(text, seed=1)


def test_gen_from_grammar_then_expected_passes(py_project):
    from morvix import generators
    from morvix.judge import judge, select_cases

    ctx, proj = py_project  # solution = SUM_ALL_PY (sums all ints on stdin)
    gpath = proj.abspath(generators.new_grammar(ctx, proj, "ints"))
    open(gpath, "w").write('start: repeat(5) { int(0..100) } sep " " "\\n"\n')
    cases = generators.gen_from_grammar(ctx, proj, gpath, count=6, seed=1, group="baseline")
    assert len(cases) == 6
    # Every generated case has inputs but NO frozen answer yet (honesty).
    assert all(c.expected_output is None and c.expected_hash is None for c in cases)
    generators.gen_expected(ctx, proj)
    run = judge(proj, proj.solution, proj.language, select_cases(proj))
    assert run.all_passed
    # Provenance records the grammar recipe.
    assert cases[0].provenance["mode"] == "grammar"
    assert cases[0].provenance["seed"] == 1
