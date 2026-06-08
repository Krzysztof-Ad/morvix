# The property oracle: a tiny sandboxed expression over a run's observable values.
#
# A property is a one-line boolean claim about what the solution printed, e.g.
# "out_int <= n" - the output integer must not exceed the input n. It is an
# ORACLE-FREE check: it never knows the right answer, it only states a bound the
# output must respect for any input. Finding an input where the bound is violated
# is finding a bug, without ever asserting what the answer should have been.
#
# This module owns only the PURE, sandboxed pieces:
#   - compile_property(expr) -> PropertyExpr   parse + strict allow-list
#   - PropertyExpr.evaluate(env) -> bool|None  True/False, or None = "could not
#                                              evaluate" (treated as skipped,
#                                              NEVER a violation)
#   - parse_ladder(spec) -> (var, lo, hi, steps)   'n=1..100000:8'
#
# The run-driver (running the solution, building env, saving violating inputs) is
# wired separately; nothing here runs a program or touches an expected answer.
#
# Honesty: the only names a property sees are the ones the driver puts in `env`
# (input sizes and the solution's OWN observed output tokens). There is no path
# from here to expected_output/expected_hash/expected_exit/expected_signal.

import ast

from morvix import boundspec
from morvix.errors import UserError

# The only builtins a property may call. Each is a safe, pure summariser over the
# values already in env; none can touch the filesystem, import, or run code.
SAFE_CALLS = {
    "len": len,
    "int": int,
    "float": float,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
}

# The AST node kinds the sandbox permits. Anything outside this set is rejected at
# compile time, so a dangerous expression never reaches evaluation.
_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Subscript,
    ast.Index if hasattr(ast, "Index") else ast.Subscript,  # py<3.9 compat
    ast.Slice,
    ast.List,
    ast.Tuple,
    # boolean / comparison / arithmetic operators
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)


# A name that begins and ends with double underscore is a dunder; we never allow
# one - it is the usual escape hatch to builtins/classes/imports.
def _is_dunder(name):
    return name.startswith("__") and name.endswith("__")


def _check_node(node):
    """Reject any node that is not on the allow-list, with a clear reason."""
    # Attribute access is the classic sandbox escape (e.g. (). __class__...), so
    # it is banned outright - properties have no business reaching into objects.
    if isinstance(node, ast.Attribute):
        raise UserError(
            "Property uses attribute access, which is not allowed.",
            hint="Properties may only use names, numbers, comparisons and len/int/min/max/sum/abs.",
        )
    if not isinstance(node, _ALLOWED_NODES):
        raise UserError(
            f"Property uses {type(node).__name__}, which is not allowed.",
            hint="Properties may only use names, numbers, comparisons and len/int/min/max/sum/abs.",
        )
    if isinstance(node, ast.Name):
        if _is_dunder(node.id):
            raise UserError(f"Property refers to '{node.id}', which is not allowed.")
    if isinstance(node, ast.Call):
        # Only direct calls to a safe builtin by bare name; no method calls, no
        # keyword args, no *args/**kwargs.
        if not isinstance(node.func, ast.Name):
            raise UserError("Property may only call a plain function by name (len, int, ...).")
        if node.func.id not in SAFE_CALLS:
            allowed = ", ".join(sorted(SAFE_CALLS))
            raise UserError(
                f"Property calls '{node.func.id}', which is not allowed.",
                hint=f"Allowed calls: {allowed}.",
            )
        if node.keywords:
            raise UserError("Property function calls may not use keyword arguments.")
    for child in ast.iter_child_nodes(node):
        _check_node(child)


class PropertyExpr:
    """A compiled, sandboxed property. Evaluate it against a run's env dict.

    evaluate(env) returns:
      True   - the property held for this run,
      False  - the property was VIOLATED (the interesting case),
      None   - it could not be evaluated (a name was missing, the output was
               unparseable, an arithmetic/type error) -> treated as SKIPPED, and
               never as a violation. Honesty: a skip is silence, not a verdict.
    """

    def __init__(self, source, tree):
        self.source = source
        self._tree = tree
        # Compile once; evaluation reuses the code object.
        self._code = compile(tree, "<property>", "eval")

    def evaluate(self, env):
        # The sandbox: no builtins at all (__builtins__ blanked), and only the
        # safe callables plus whatever the driver placed in env are visible.
        names = dict(SAFE_CALLS)
        names.update(env)
        glb = {"__builtins__": {}}
        try:
            result = eval(self._code, glb, names)  # noqa: S307 - sandboxed AST
        except Exception:
            # Any failure (missing name, bad type, unparseable output the driver
            # left as None, division by zero) means "could not check" -> skipped.
            return None
        if result is None:
            return None
        return bool(result)

    def __repr__(self):
        return f"PropertyExpr({self.source!r})"


def compile_property(expr):
    """Parse a property string and verify it against the allow-list.

    Raises UserError on an empty expression, a syntax error, or any disallowed
    construct (imports, attribute access, unknown/dangerous calls, dunders, ...).
    Returns a PropertyExpr ready to evaluate.
    """
    if expr is None or not expr.strip():
        raise UserError(
            "Property expression is empty.",
            hint="Give a boolean expression, e.g. --property 'out_int <= n'.",
        )
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise UserError(f"Could not parse property '{expr}': {e.msg}.") from e
    _check_node(tree)
    return PropertyExpr(expr, tree)


def parse_ladder(spec):
    """Parse a per-rung size ladder 'VAR=LO..HI:STEPS' -> (var, lo, hi, steps).

    Used by --property --ladder-spec to vary one size parameter geometrically.
    Numbers go through boundspec.num_token, so '1e5' means 100000 here exactly as
    it does for axes. Raises UserError on any malformed spec.
    """
    if spec is None or not spec.strip():
        raise UserError("Ladder spec is empty.", hint="Use VAR=LO..HI:STEPS, e.g. n=1..100000:8.")
    text = spec.strip()
    if "=" not in text:
        raise UserError(
            f"Bad ladder spec '{spec}': expected VAR=LO..HI:STEPS.",
            hint="For example: n=1..100000:8",
        )
    var, rhs = text.split("=", 1)
    var = var.strip()
    if not var:
        raise UserError(f"Bad ladder spec '{spec}': a variable name is required.")
    if ":" not in rhs:
        raise UserError(f"Bad ladder spec '{spec}': missing ':STEPS' (e.g. n=1..100000:8).")
    range_part, steps_part = rhs.rsplit(":", 1)
    if ".." not in range_part:
        raise UserError(f"Bad ladder spec '{spec}': the range must be LO..HI (e.g. 1..100000).")
    lo_s, hi_s = range_part.split("..", 1)
    lo, _ = boundspec.num_token(lo_s)
    hi, _ = boundspec.num_token(hi_s)
    steps, steps_int = boundspec.num_token(steps_part)
    if not steps_int or steps < 1:
        raise UserError(f"Bad ladder spec '{spec}': STEPS must be a positive integer.")
    if hi < lo:
        raise UserError(f"Bad ladder spec '{spec}': {lo} > {hi}.")
    return var, lo, hi, int(steps)
