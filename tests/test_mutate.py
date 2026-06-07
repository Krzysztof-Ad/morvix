# Mutation engine tests: operators are deterministic with a seed, structure-aware
# with a schema, and never touch answers.
#
# Pure-logic, no project needed.

import random

from morvix import mutate, schema


def _count_schema():
    # The "n then n lines" schema: line 0 is a single int count that drives the
    # number of trailing body lines.
    grids = [schema.classify(s) for s in ["2\n10\n20", "3\n5\n6\n7", "1\n9"]]
    return schema.merge(grids)


def test_list_operators_nonempty_and_sorted():
    ops = mutate.list_operators()
    assert ops == sorted(ops)
    assert "dup_token" in ops and "tweak_int" in ops


def test_default_ops_are_known():
    for name in mutate.DEFAULT_OPS:
        assert name in mutate.OPERATORS


def test_mutate_deterministic_with_seed():
    text = "3\n1 2 3"
    a = mutate.mutate_once(random.Random(123), text, mutate.DEFAULT_OPS)
    b = mutate.mutate_once(random.Random(123), text, mutate.DEFAULT_OPS)
    assert a == b


def test_dup_line_with_schema_fixes_count():
    # The schema threads a count; duplicating a body line must repair the count
    # so "n then n lines" stays consistent.
    s = _count_schema()
    text = "2\n10\n20"
    rng = random.Random(0)
    out = mutate.mutate_once(rng, text, ["dup_line"], schema=s)
    # The first line (the count) should equal the number of trailing lines.
    assert mutate.count_consistent(out, s)
    lines = out.split("\n")
    assert int(lines[0]) == len(lines) - 1


def test_count_consistent_detects_off_by_one():
    s = _count_schema()
    assert mutate.count_consistent("2\n10\n20", s) is True
    # Declared 2 but three body lines: off-by-one.
    assert mutate.count_consistent("2\n10\n20\n30", s) is False


def test_count_consistent_true_without_schema():
    assert mutate.count_consistent("2\n10\n20\n30", None) is True


def test_mutate_without_schema_does_not_repair_count():
    # No schema means structure-blind: dup_line lengthens the body but leaves the
    # count alone, so it is no longer consistent against the count schema.
    s = _count_schema()
    rng = random.Random(0)
    out = mutate.mutate_once(rng, "2\n10\n20", ["dup_line"], schema=None)
    # There are now 3 body lines but the header still says 2.
    assert int(out.split("\n")[0]) == 2
    assert mutate.count_consistent(out, s) is False


def test_unknown_op_is_ignored():
    text = "1 2 3"
    out = mutate.mutate_once(random.Random(0), text, ["does_not_exist"])
    assert out == text


def test_swap_tokens_preserves_token_multiset():
    text = "1 2 3 4"
    out = mutate.mutate_once(random.Random(5), text, ["swap_tokens"])
    assert sorted(out.split()) == sorted(text.split())


def test_crossover_combines_two_inputs():
    a = "1\n2\n3"
    b = "9\n8\n7"
    out = mutate.crossover(random.Random(2), a, b)
    # Every produced line came from one parent.
    parent_lines = set(a.split("\n")) | set(b.split("\n"))
    for line in out.split("\n"):
        if line:
            assert line in parent_lines


def test_crossover_deterministic():
    a, b = "1\n2\n3", "9\n8\n7"
    assert mutate.crossover(random.Random(4), a, b) == mutate.crossover(random.Random(4), a, b)


def test_extreme_int_keeps_count_consistent_with_schema():
    # Changing a body value (not the count) must keep consistency.
    s = _count_schema()
    out = mutate.mutate_once(random.Random(1), "2\n10\n20", ["extreme_int"], schema=s)
    assert mutate.count_consistent(out, s)
