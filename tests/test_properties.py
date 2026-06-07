# Tests for the property oracle's pure parts (Section 13, the --property mode).
#
# These exercise only compile_property / PropertyExpr.evaluate / parse_ladder -
# the sandboxed, program-free pieces. The run-driver is tested elsewhere. The
# core honesty/safety claims here: dangerous expressions never compile, an
# unparseable output yields a SKIP (None) and never a false "violation", and the
# size ladder parses geometrically and rejects garbage.

import pytest

from morvix.errors import UserError
from morvix.properties import PropertyExpr, compile_property, parse_ladder

# Expressions the sandbox must refuse to compile. Each is a different escape
# route: imports, attribute access, dunders, unknown calls, lambdas, comprehensions.
DANGEROUS = [
    "__import__('os')",
    "__import__('os').system('echo hi')",
    "().__class__",
    "out_int.__class__",
    "out.foo",
    "out_int.bit_length()",
    "os.system('x')",
    "open('/etc/passwd')",
    "eval('1+1')",
    "exec('x=1')",
    "globals()",
    "(lambda: 1)()",
    "[x for x in range(3)]",
    "{k: v for k, v in env}",
    "__builtins__",
    "out_int := 3",
]


@pytest.mark.parametrize("expr", DANGEROUS)
def test_compile_property_rejects_dangerous(expr):
    with pytest.raises(UserError):
        compile_property(expr)


def test_compile_property_rejects_empty():
    with pytest.raises(UserError):
        compile_property("")
    with pytest.raises(UserError):
        compile_property("   ")


def test_compile_property_rejects_syntax_error():
    with pytest.raises(UserError):
        compile_property("out_int <=")


# Safe expressions the sandbox must accept and evaluate correctly.
@pytest.mark.parametrize(
    "expr,env,want",
    [
        ("out_int <= n", {"out_int": 3, "n": 5}, True),
        ("out_int <= n", {"out_int": 9, "n": 5}, False),
        ("out_len == n", {"out_len": 4, "n": 4}, True),
        ("0 <= out_int <= n", {"out_int": 5, "n": 10}, True),
        ("0 <= out_int <= n", {"out_int": 11, "n": 10}, False),
        ("out_int >= 0 and out_int <= n", {"out_int": 2, "n": 3}, True),
        ("len(tokens) == n", {"tokens": [1, 2, 3], "n": 3}, True),
        ("sum(tokens) <= n", {"tokens": [1, 2, 3], "n": 100}, True),
        ("min(tokens) >= 0", {"tokens": [0, 1, 2]}, True),
        ("max(tokens) <= n", {"tokens": [1, 9], "n": 5}, False),
        ("abs(out_int) <= n", {"out_int": -3, "n": 5}, True),
        ("tokens[0] == n", {"tokens": [7, 8], "n": 7}, True),
        ("out_int * 2 <= n", {"out_int": 3, "n": 10}, True),
        ("out_int in tokens", {"out_int": 2, "tokens": [1, 2, 3]}, True),
        ("out_int not in tokens", {"out_int": 9, "tokens": [1, 2, 3]}, True),
    ],
)
def test_safe_expression_evaluates(expr, env, want):
    prop = compile_property(expr)
    assert isinstance(prop, PropertyExpr)
    assert prop.evaluate(env) is want


def test_unparseable_output_is_skipped():
    # The driver could not parse the program's output into an int, so it left the
    # name as None. A property over it must yield None (skipped), NOT False.
    prop = compile_property("out_int <= n")
    assert prop.evaluate({"out_int": None, "n": 5}) is None


def test_missing_name_is_skipped_not_violation():
    # A name the driver never supplied -> could-not-evaluate -> None, never False.
    prop = compile_property("out_int <= n")
    assert prop.evaluate({"n": 5}) is None
    assert prop.evaluate({}) is None


def test_type_error_is_skipped():
    # Comparing incommensurable types is a "could not check", not a violation.
    prop = compile_property("out_int <= n")
    assert prop.evaluate({"out_int": "abc", "n": 5}) is None


def test_division_by_zero_is_skipped():
    prop = compile_property("n / out_int >= 1")
    assert prop.evaluate({"n": 5, "out_int": 0}) is None


def test_index_out_of_range_is_skipped():
    prop = compile_property("tokens[5] == n")
    assert prop.evaluate({"tokens": [1, 2], "n": 0}) is None


def test_evaluate_cannot_reach_builtins():
    # Even a name that happens to collide with a builtin is only what env says.
    # There is no __builtins__ leak: a property cannot call an un-allowlisted name.
    with pytest.raises(UserError):
        compile_property("range(3)")


def test_safe_call_not_shadowable_to_danger():
    # 'len' is allowed; 'open' is not, even though both are builtins.
    compile_property("len(tokens) <= n")  # ok
    with pytest.raises(UserError):
        compile_property("open(n)")


# --- parse_ladder ---


def test_parse_ladder_basic():
    assert parse_ladder("n=1..100000:8") == ("n", 1, 100000, 8)


def test_parse_ladder_scientific():
    # 1e5 must mean 100000, exactly like an axis range.
    assert parse_ladder("n=1..1e5:8") == ("n", 1, 100000, 8)


def test_parse_ladder_strips_whitespace():
    assert parse_ladder("  size = 10 .. 1000 : 4  ") == ("size", 10, 1000, 4)


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "   ",
        "n",  # no '='
        "=1..100:8",  # no var
        "n=1..100",  # no :steps
        "n=100:8",  # no range
        "n=1..100:0",  # steps must be positive
        "n=1..100:-3",  # negative steps
        "n=1..100:2.5",  # non-integer steps
        "n=100..1:8",  # lo > hi
        "n=abc..100:8",  # non-numeric bound
    ],
)
def test_parse_ladder_rejects_bad_specs(spec):
    with pytest.raises(UserError):
        parse_ladder(spec)
