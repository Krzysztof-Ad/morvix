# Declarative grammar generation (Section 13) - the flagship structured-input tool.
#
# Random shapes can't express "read N, then N numbers" or "read R C, then an
# R x C grid": the count and the body are linked. A grammar captures that link
# declaratively, so a sampled input is correct-by-construction. You write rules;
# a seeded sampler walks them once and prints one valid input.
#
# A grammar asserts the input's SHAPE, not its meaning, and never an answer -
# expected answers still come only from gen --expected running the solution.
#
# Syntax (one rule per line; '#' starts a comment; the 'start' rule is the entry):
#
#   start: int(1..100) as n "\n" repeat(n) { int(0..1e6) } sep " " "\n"
#   start: int(1..50) as r " " int(1..50) as c "\n" repeat(r) { repeat(c) { char(".#") } "\n" }
#
# Items in a sequence (whitespace-separated):
#   int(LO..HI) [as NAME]      a random integer in [LO,HI]; 'as NAME' binds it
#   float(LO..HI, NDIGITS)     a random float, fixed to NDIGITS decimals
#   char("ALPHABET")           one random character from ALPHABET
#   str(LEN, "ALPHABET")       LEN random characters from ALPHABET
#   "text"                     a literal (supports \n \t \\ \")
#   nl / sp                    shorthand literals for newline / space
#   repeat(COUNT) { BODY } [sep "S"]   BODY COUNT times, joined by S
#   oneof { A | B | ... }      pick one alternative at random
#   let NAME = int(LO..HI)     SILENTLY sample NAME (prints nothing) for later use
#   let NAME = EXPR            SILENTLY bind NAME to a computed value
#   NAME                       call another rule
# LO/HI/COUNT/LEN/NDIGITS are numeric expressions over literals, bound NAMEs and
# + - * / and parentheses, so bounds can depend on earlier-read values.

import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from morvix.boundspec import num_token

MAX_DEPTH = 200
MAX_BYTES = 64 * 1024 * 1024

STARTER_GRAMMAR = """# A Morvix grammar: sample ONE valid input by construction.
# Edit the rules so a sampled input matches EXACTLY what your program reads.
# Bind a value with 'as NAME', then reuse NAME as a repeat count or a bound.
#
# Then:  gen --grammar {path} --count 1000
#        gen --expected
#
# Example: read n, then n integers on one line.
start: int(1..100) as n "\\n" repeat(n) {{ int(0..1000000) }} sep " " "\\n"
"""


class GrammarError(ValueError):
    """A grammar parse or sampling error, with a 1-based line for the user."""

    def __init__(self, message: str, line: Optional[int] = None):
        self.line = line
        self.message = message
        super().__init__(f"line {line}: {message}" if line else message)


# --- AST ---------------------------------------------------------------------


@dataclass
class NumLit:
    value: float


@dataclass
class NameRef:
    name: str
    line: int


@dataclass
class BinOp:
    op: str
    left: "Num"
    right: "Num"


Num = Union[NumLit, NameRef, BinOp]


@dataclass
class IntTerm:
    lo: Num
    hi: Num
    bind: Optional[str]
    line: int


@dataclass
class FloatTerm:
    lo: Num
    hi: Num
    ndigits: Num
    line: int


@dataclass
class CharTerm:
    alphabet: str
    line: int


@dataclass
class StrTerm:
    length: Num
    alphabet: str
    line: int


@dataclass
class Literal:
    text: str


@dataclass
class Call:
    name: str
    line: int


@dataclass
class Repeat:
    count: Num
    body: List["Item"]
    sep: Optional[str]
    line: int


@dataclass
class OneOf:
    choices: List[List["Item"]]


@dataclass
class LetBind:
    # A SILENT bind: sample (or compute) a value and store it, emitting nothing.
    # 'lo'/'hi' set for the int-range form; 'value' set for the expression form.
    name: str
    lo: Optional[Num]
    hi: Optional[Num]
    value: Optional[Num]
    line: int


Item = Union[IntTerm, FloatTerm, CharTerm, StrTerm, Literal, Call, Repeat, OneOf, LetBind]


@dataclass
class Grammar:
    rules: Dict[str, List[Item]]
    start: str
    source: str = ""
    order: List[str] = field(default_factory=list)


# --- tokenizer ---------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<range>\.\.)
  | (?P<str>"(?:\\.|[^"\\])*")
  | (?P<op>[(){}|,+\-*/=])
  | (?P<ident>[A-Za-z_]\w*)
    """,
    re.VERBOSE,
)

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "r": "\r", "0": "\0", " ": " "}


def _unescape(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            out.append(_ESCAPES.get(s[i + 1], s[i + 1]))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _strip_comment(line: str) -> str:
    """Drop a trailing '#' comment, but not a '#' inside a "string literal"."""
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and in_str:
            i += 2
            continue
        if c == '"':
            in_str = not in_str
        elif c == "#" and not in_str:
            return line[:i]
        i += 1
    return line


def _tokenize(body: str, line: int):
    tokens: list = []
    pos = 0
    while pos < len(body):
        m = _TOKEN_RE.match(body, pos)
        if not m:
            raise GrammarError(f"unexpected character {body[pos]!r}", line)
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        text = m.group()
        if kind == "str":
            tokens.append(("str", _unescape(text[1:-1])))
        else:
            tokens.append((kind, text))
    return tokens


# --- parser ------------------------------------------------------------------


class _Parser:
    def __init__(self, tokens, line):
        self.toks = tokens
        self.i = 0
        self.line = line

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def _next(self):
        tok = self._peek()
        self.i += 1
        return tok

    def _expect(self, kind, text=None):
        k, t = self._next()
        if k != kind or (text is not None and t != text):
            want = text or kind
            raise GrammarError(f"expected {want!r}", self.line)
        return t

    def at_end(self):
        return self.i >= len(self.toks)

    # sequence := item* (stops at } or | or end)
    def sequence(self, stop=()):
        items = []
        while not self.at_end():
            k, t = self._peek()
            if k == "op" and t in stop:
                break
            items.append(self.item())
        return items

    def item(self) -> Item:
        k, t = self._peek()
        if k == "str":
            self._next()
            return Literal(t)
        if k == "ident":
            if t in ("int", "float", "char", "str"):
                return self._terminal(t)
            if t == "repeat":
                return self._repeat()
            if t == "oneof":
                return self._oneof()
            if t == "let":
                return self._let()
            if t == "nl":
                self._next()
                return Literal("\n")
            if t == "sp":
                self._next()
                return Literal(" ")
            self._next()
            return Call(t, self.line)
        raise GrammarError(f"unexpected token {t!r}", self.line)

    def _terminal(self, kind) -> Item:
        self._next()  # the keyword
        self._expect("op", "(")
        if kind == "int":
            lo = self.expr()
            self._expect("range")
            hi = self.expr()
            self._expect("op", ")")
            bind = None
            k, t = self._peek()
            if k == "ident" and t == "as":
                self._next()
                bind = self._expect("ident")
            return IntTerm(lo, hi, bind, self.line)
        if kind == "float":
            lo = self.expr()
            self._expect("range")
            hi = self.expr()
            self._expect("op", ",")
            ndig = self.expr()
            self._expect("op", ")")
            return FloatTerm(lo, hi, ndig, self.line)
        if kind == "char":
            alpha = self._expect("str")
            self._expect("op", ")")
            if not alpha:
                raise GrammarError("char() needs a non-empty alphabet", self.line)
            return CharTerm(alpha, self.line)
        # str
        length = self.expr()
        self._expect("op", ",")
        alpha = self._expect("str")
        self._expect("op", ")")
        if not alpha:
            raise GrammarError("str() needs a non-empty alphabet", self.line)
        return StrTerm(length, alpha, self.line)

    def _repeat(self) -> Item:
        self._next()  # 'repeat'
        self._expect("op", "(")
        count = self.expr()
        self._expect("op", ")")
        self._expect("op", "{")
        body = self.sequence(stop=("}",))
        self._expect("op", "}")
        sep = None
        k, t = self._peek()
        if k == "ident" and t == "sep":
            self._next()
            sep = self._expect("str")
        return Repeat(count, body, sep, self.line)

    def _let(self) -> Item:
        # let NAME = int(LO..HI)   (sample silently)
        # let NAME = EXPR          (compute from existing binds, silently)
        self._next()  # 'let'
        name = self._expect("ident")
        self._expect("op", "=")
        k, t = self._peek()
        if k == "ident" and t == "int":
            self._next()  # 'int'
            self._expect("op", "(")
            lo = self.expr()
            self._expect("range")
            hi = self.expr()
            self._expect("op", ")")
            return LetBind(name, lo, hi, None, self.line)
        return LetBind(name, None, None, self.expr(), self.line)

    def _oneof(self) -> Item:
        self._next()  # 'oneof'
        self._expect("op", "{")
        choices = [self.sequence(stop=("}", "|"))]
        while True:
            k, t = self._peek()
            if k == "op" and t == "|":
                self._next()
                choices.append(self.sequence(stop=("}", "|")))
            else:
                break
        self._expect("op", "}")
        return OneOf(choices)

    # expr := term (('+'|'-') term)*
    def expr(self) -> Num:
        node = self.term()
        while True:
            k, t = self._peek()
            if k == "op" and t in ("+", "-"):
                self._next()
                node = BinOp(t, node, self.term())
            else:
                return node

    def term(self) -> Num:
        node = self.factor()
        while True:
            k, t = self._peek()
            if k == "op" and t in ("*", "/"):
                self._next()
                node = BinOp(t, node, self.factor())
            else:
                return node

    def factor(self) -> Num:
        k, t = self._next()
        if k == "op" and t == "-":
            return BinOp("-", NumLit(0), self.factor())
        if k == "op" and t == "(":
            node = self.expr()
            self._expect("op", ")")
            return node
        if k == "num":
            return NumLit(num_token(t)[0])
        if k == "ident":
            return NameRef(t, self.line)
        raise GrammarError(f"expected a number or name, got {t!r}", self.line)


def parse(source: str, filename: str = "<grammar>") -> Grammar:
    """Parse grammar source into a Grammar (raises GrammarError on bad syntax)."""
    rules: Dict[str, List[Item]] = {}
    order: List[str] = []
    for lineno, raw in enumerate(source.splitlines(), 1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if ":" not in line:
            raise GrammarError("a rule looks like 'name: ...'", lineno)
        name, body = line.split(":", 1)
        name = name.strip()
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise GrammarError(f"bad rule name {name!r}", lineno)
        parser = _Parser(_tokenize(body, lineno), lineno)
        items = parser.sequence()
        if not parser.at_end():
            raise GrammarError("trailing tokens after the rule", lineno)
        rules[name] = items
        order.append(name)
    if not rules:
        raise GrammarError("the grammar is empty", None)
    start = "start" if "start" in rules else order[0]
    return Grammar(rules=rules, start=start, source=source, order=order)


# --- sampler -----------------------------------------------------------------


class _Sampler:
    def __init__(self, grammar: Grammar, rng: random.Random, env: dict):
        self.g = grammar
        self.rng = rng
        self.env = env
        self.out: List[str] = []
        self.size = 0

    def _emit(self, text: str):
        self.size += len(text)
        if self.size > MAX_BYTES:
            raise GrammarError(
                "sampled input exceeded the size cap - check repeat counts and bounds", None
            )
        self.out.append(text)

    def _eval(self, node: Num):
        if isinstance(node, NumLit):
            return node.value
        if isinstance(node, NameRef):
            if node.name not in self.env:
                raise GrammarError(f"unknown name {node.name!r}", node.line)
            return self.env[node.name]
        a, b = self._eval(node.left), self._eval(node.right)
        if node.op == "+":
            return a + b
        if node.op == "-":
            return a - b
        if node.op == "*":
            return a * b
        return a / b if b else 0

    def _eval_int(self, node: Num) -> int:
        return int(self._eval(node))

    def run_rule(self, name: str, depth: int):
        if depth > MAX_DEPTH:
            raise GrammarError("recursion too deep - check for a non-terminating rule", None)
        if name not in self.g.rules:
            raise GrammarError(f"unknown rule {name!r}", None)
        for item in self.g.rules[name]:
            self._emit_item(item, depth)

    def _emit_item(self, item: Item, depth: int):
        if isinstance(item, Literal):
            self._emit(item.text)
        elif isinstance(item, IntTerm):
            if item.bind and item.bind in self.env:
                v = int(self.env[item.bind])  # pinned (--param) wins over sampling
            else:
                lo, hi = self._eval_int(item.lo), self._eval_int(item.hi)
                if lo > hi:
                    raise GrammarError(f"empty range {lo}..{hi}", item.line)
                v = self.rng.randint(lo, hi)
                if item.bind:
                    self.env[item.bind] = v
            self._emit(str(v))
        elif isinstance(item, FloatTerm):
            lo, hi = self._eval(item.lo), self._eval(item.hi)
            if lo > hi:
                raise GrammarError(f"empty range {lo}..{hi}", item.line)
            nd = self._eval_int(item.ndigits)
            self._emit(f"{self.rng.uniform(lo, hi):.{max(nd, 0)}f}")
        elif isinstance(item, CharTerm):
            self._emit(self.rng.choice(item.alphabet))
        elif isinstance(item, StrTerm):
            n = self._eval_int(item.length)
            self._emit("".join(self.rng.choice(item.alphabet) for _ in range(max(n, 0))))
        elif isinstance(item, Call):
            self.run_rule(item.name, depth + 1)
        elif isinstance(item, Repeat):
            count = self._eval_int(item.count)
            for k in range(max(count, 0)):
                if k and item.sep:
                    self._emit(item.sep)
                for sub in item.body:
                    self._emit_item(sub, depth)
        elif isinstance(item, OneOf):
            for sub in self.rng.choice(item.choices):
                self._emit_item(sub, depth)
        elif isinstance(item, LetBind):
            # Silent: bind a value for later use, emit nothing. A pinned --param
            # of the same name wins, mirroring 'int(...) as NAME'.
            if item.name in self.env:
                pass
            elif item.value is not None:
                self.env[item.name] = self._eval(item.value)
            elif item.lo is not None and item.hi is not None:
                lo = self._eval_int(item.lo)
                hi = self._eval_int(item.hi)
                if lo > hi:
                    raise GrammarError(f"empty range {lo}..{hi}", item.line)
                self.env[item.name] = self.rng.randint(lo, hi)


def sample(grammar: Grammar, seed: int, params: Optional[dict] = None) -> str:
    """Sample one input from a parsed grammar with the given seed and pinned params."""
    rng = random.Random(seed)
    env: dict = dict(params or {})
    sampler = _Sampler(grammar, rng, env)
    sampler.run_rule(grammar.start, 0)
    return "".join(sampler.out)


def sample_source(
    source: str, seed: int, params: Optional[dict] = None, filename="<grammar>"
) -> str:
    """Parse + sample in one step (convenience for tests and previews)."""
    return sample(parse(source, filename), seed, params)
