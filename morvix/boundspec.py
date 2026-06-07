# The bound-spec mini-language: declare an input axis once, reuse it everywhere.
#
# Several modes need the same little "what values can this variable take" idea:
# boundary enumeration, pairwise factors, bounded-exhaustive value sets. Rather
# than three syntaxes, there is one. A spec is "KEY=RHS" where RHS is either a
# range (1..1e5), a discrete set (sorted,reverse,random) or a single scalar.
#
#   --axis n=1..100000      a numeric range (inclusive)
#   --axis v=-1e9..1e9      negatives and scientific notation are fine
#   --axis layout=sorted,reverse,random   a discrete set
#
# Domains expand to the value lists each mode wants: boundary points, a few
# representative factor levels, or the full enumeration of an integer range.

from dataclasses import dataclass
from typing import Dict, List, Tuple, Union

from morvix.errors import UserError

Number = Union[int, float]


def num_token(tok: str) -> Tuple[Number, bool]:
    """Parse one numeric token; return (value, is_int).

    Accepts scientific notation, and reports an integral float (1e5) as the int
    100000 with is_int=True. This is the single numeric parser shared with the
    grammar so the two never diverge.
    """
    tok = tok.strip()
    try:
        return int(tok), True
    except ValueError:
        pass
    try:
        f = float(tok)
    except ValueError as e:
        raise UserError(f"Not a number: '{tok}'") from e
    if f.is_integer():
        return int(f), True
    return f, False


@dataclass(frozen=True)
class RangeDomain:
    name: str
    lo: Number
    hi: Number
    is_int: bool


@dataclass(frozen=True)
class SetDomain:
    name: str
    values: tuple


Domain = Union[RangeDomain, SetDomain]


def parse_spec(item: str) -> Domain:
    """Parse one 'KEY=RHS' axis spec into a Domain."""
    if "=" not in item:
        raise UserError(
            f"Bad axis '{item}': expected NAME=SPEC.",
            hint="For example: --axis n=1..1e5  or  --axis layout=sorted,reverse",
        )
    name, rhs = item.split("=", 1)
    name, rhs = name.strip(), rhs.strip()
    if not name or not rhs:
        raise UserError(f"Bad axis '{item}': both a name and a spec are required.")
    has_range = ".." in rhs
    has_set = "," in rhs
    if has_range and has_set:
        raise UserError(
            f"Bad axis '{name}': a spec is a range (..) or a set (,), not both.",
            hint="Use n=1..100 for a range or n=1,10,100 for a set.",
        )
    if has_range:
        lo_s, hi_s = rhs.split("..", 1)
        lo, lo_int = num_token(lo_s)
        hi, hi_int = num_token(hi_s)
        if hi < lo:
            raise UserError(f"Bad axis '{name}': {lo} > {hi}.")
        return RangeDomain(name=name, lo=lo, hi=hi, is_int=lo_int and hi_int)
    if has_set:
        return SetDomain(name=name, values=tuple(_coerce(t) for t in rhs.split(",")))
    return SetDomain(name=name, values=(_coerce(rhs),))


def parse_specs(items: List[str]) -> Dict[str, Domain]:
    """Parse many axis specs into {name: Domain}; later specs override earlier."""
    out: Dict[str, Domain] = {}
    for item in items:
        d = parse_spec(item)
        out[d.name] = d
    return out


def _coerce(tok: str):
    """A set member is a number when it looks like one, else the raw string."""
    tok = tok.strip()
    try:
        value, _ = num_token(tok)
        return value
    except UserError:
        return tok


def boundary_values(d: Domain, eps: float = 1e-6) -> list:
    """The boundary-analysis points of a domain: extremes, neighbours, 0/1/-1, mid."""
    if isinstance(d, SetDomain):
        return list(d.values)
    lo, hi = d.lo, d.hi
    cand = [lo, hi, 0, 1, -1]
    if d.is_int:
        cand += [lo + 1, hi - 1, (lo + hi) // 2]
    else:
        cand += [lo + eps, hi - eps, (lo + hi) / 2.0]
    out = []
    for v in cand:
        if lo <= v <= hi and v not in out:
            out.append(v)
    return out


def factor_levels(d: Domain, max_levels: int = 4) -> list:
    """A few representative values for combinatorial coverage (min/mid/max [+0])."""
    if isinstance(d, SetDomain):
        return list(d.values)[:max_levels]
    lo, hi = d.lo, d.hi
    mid = (lo + hi) // 2 if d.is_int else (lo + hi) / 2.0
    levels = [lo, mid, hi]
    if lo < 0 < hi and 0 not in levels:
        levels.append(0)
    out = []
    for v in levels:
        if v not in out:
            out.append(v)
    return out[:max_levels]


def enum_values(d: Domain) -> list:
    """Every value of a small integer range (or the set's members)."""
    if isinstance(d, SetDomain):
        return list(d.values)
    if not d.is_int:
        raise UserError(f"Axis '{d.name}': cannot enumerate a float range exhaustively.")
    return list(range(int(d.lo), int(d.hi) + 1))
