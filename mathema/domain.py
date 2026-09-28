# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The domain model: what values a claim's quantifier admits.

Everything about a declared domain lives here, the value types
(`Interval`, the composite `Domain`, the `MISSING` sentinel), parsing
(`split_quantifier`/`parse_binding`, covering `for x in [0, 1]`-style
bindings with unions, exclusions, type refinements, and the
missing-value clauses), membership (`domain_contains`), rendering
(`render_domain`/`render_domain_bound`), and the JSON codec the spec
store round-trips bounds through.

Deliberately a leaf: stdlib plus the package's own `_render_mode`/
`_scan` leaves, no sympy and no dependency on the claim grammar, so
every layer (the sampler, the symbolic prover, the spec store, the
renderer) can share one domain model without import cycles.
`grammar.py` re-exports this module's public names for compatibility;
new code should import from here.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ._render_mode import get_unicode_output
from ._scan import _split_commas

# superscript rendering for a vector/matrix space exponent, so `R^n`
# reads `ℝⁿ` in unicode the way `x^2` reads `x²` elsewhere. Only
# used when every character has a superscript form (dim names are
# normally single lowercase letters, which all do); otherwise the
# plain `^(...)` spelling is kept, never a half-superscripted mess.
_SUPERSCRIPT = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
    "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ",
    "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
    "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
    "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
    "×": "ˣ",   # the times sign, superscript is the small x
}
_SUPERSCRIPT_INV = {v: k for k, v in _SUPERSCRIPT.items()}


def _to_superscript(text: str) -> "str | None":
    """`text` in unicode superscript, or None if any character has no
    superscript form (so the caller keeps the ascii `^(...)` spelling
    rather than rendering half of it)."""
    out = []
    for ch in text:
        if ch in _SUPERSCRIPT:
            out.append(_SUPERSCRIPT[ch])
        else:
            return None
    return "".join(out)


def _from_superscript(text: str) -> str:
    """A run of superscript characters back to plain text; a non-
    superscript character passes through unchanged."""
    return "".join(_SUPERSCRIPT_INV.get(ch, ch) for ch in text)


#: dimension names of a space exponent: a single name, or a list of
#: them separated by `,` (the canonical `m,n`), `*` or `×`. Names are
#: identifiers; a bare integer is allowed for a fixed dimension (`R^3`).
_DIM_EXPONENT = re.compile(
    r"^(?:[A-Za-z_]\w*|\d+)(?:\s*[*×,]\s*(?:[A-Za-z_]\w*|\d+))*$")


_SUPERSCRIPT_RUN = re.compile(
    "[" + "".join(re.escape(c) for c in _SUPERSCRIPT.values()) + "]+")

#: the superscript separator between dimensions (`ℝᵐˣⁿ`). It is also the
#: superscript letter x, so a dimension named with an `x` never displays
#: as a superscript.
_SUPERSCRIPT_TIMES = "ˣ"

#: a superscript run directly after a set (`ℝ`, `R`, an interval's
#: closing bracket) that holds the separator: a whole matrix exponent,
#: digits included (`ℝ³ˣ³`).
_SPACE_SUPERSCRIPT_RUN = re.compile(
    r"([ℝℤℕℂ\]\)]|\b[RZNC])(" + _SUPERSCRIPT_RUN.pattern + ")")


def _plain_exponent(run: str) -> str:
    """A superscript exponent run as a plain `^` exponent: `ⁿ` -> `^n`,
    `ᵐˣⁿ` -> `^(m,n)`, `³ˣ³` -> `^(3,3)`. A run that is only the
    separator reads as the dimension `x`. A run with an empty dimension
    (`ᵐˣ`) keeps its `×` so the domain parser refuses it."""
    if run == _SUPERSCRIPT_TIMES:
        return "^x"
    names = [_from_superscript(piece) for piece in run.split(_SUPERSCRIPT_TIMES)]
    if len(names) == 1:
        return f"^{names[0]}"
    if not all(names):
        return "^(" + "×".join(names) + ")"
    return "^(" + ",".join(names) + ")"


def desuperscript_spaces(text: str) -> str:
    """Every superscript matrix exponent after a set rewritten as a plain
    `^(m,n)` exponent, before anything reads its superscript digits as
    an ordinary power (`ℝ³ˣ³` -> `ℝ^(3,3)`)."""
    def repl(m):
        run = m.group(2)
        if _SUPERSCRIPT_TIMES not in run:
            return m.group(0)
        return m.group(1) + _plain_exponent(run)
    return _SPACE_SUPERSCRIPT_RUN.sub(repl, text)


def _desuperscript(text: str) -> str:
    """Any run of superscript characters rewritten as an explicit
    `^<plain>` power, so the unicode space form (`ℝⁿ`, `[0,1]ᵏ`) and
    the ascii form (`R^n`, `[0,1]^k`) reach the same parse. A matrix
    exponent becomes the comma list (`ℝᵐˣⁿ` -> `R^(m,n)`)."""
    return _SUPERSCRIPT_RUN.sub(lambda m: _plain_exponent(m.group(0)), text)


def _split_top_caret(text: str) -> "tuple[str, str] | None":
    """`(base, exponent)` at a power operator outside every bracket
    pair, or None. The dimension power binds the WHOLE element domain,
    so its operator is the one at bracket depth zero; a power inside
    `[1, 10**6]` is an endpoint and never matched. Both `^` and `**`
    are accepted, since `normalize()` swaps `^` to `**` before a
    quantifier is parsed."""
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith("**", i):
            return text[:i].rstrip(), text[i + 2:].strip()
        elif depth == 0 and ch == "^":
            return text[:i].rstrip(), text[i + 1:].strip()
        i += 1
    return None


def _parse_dims(exponent: str) -> "tuple | None":
    """A space exponent (`n`, `(m,n)`, `{m,n}`, `(m*n)`, `(m×n)`,
    superscript forms) as a tuple of dimension tokens, or None when it
    is not a dimension exponent at all (so an ordinary numeric power is
    left alone)."""
    exp = _from_superscript(exponent).strip()
    if (exp[:1], exp[-1:]) in (("(", ")"), ("{", "}")):
        exp = exp[1:-1].strip()
    if not _DIM_EXPONENT.match(exp):
        return None
    parts = re.split(r"\s*[*×,]\s*", exp)
    return tuple(p.strip() for p in parts if p.strip())


class InvalidDomain(ValueError):
    """Raised by `split_quantifier()` when text that clearly started a
    quantifier (`for ... :`) has a binding that doesn't parse, a real,
    specific reason (which part, what's wrong with it), never a silent
    empty domain that leaves an author guessing why their claim's own
    declared bounds didn't take effect. Never raised for text that
    doesn't look like a quantifier at all (no leading `for ... :`);
    that's legitimately "no domain here", not a syntax error."""


class DuplicateBinding(InvalidDomain):
    """Raised by `split_quantifier()` when one quantifier binds the same
    name twice: two domains for one name, neither of which can be
    preferred silently."""


_FOR_PREFIX = re.compile(r"^\s*for\s+", re.DOTALL)
# "x in D" / "x ∈ D" / "x \in D" / "x \elem D", all one membership
# operator, matched up front so every binding shape below only ever has
# to key on the literal word "in" internally.
_MEMBERSHIP_OPS = r"(?:in|\\elem|\\in|∈)"
# the name may be dotted (`self.rate`, `cfg.a`): a bundled parameter's
# field is quantified exactly like a scalar parameter
# a binding's name: a parameter, or a path into one through fields and
# indices, `o.qty`, `o.address.zip`, `o.lines[0].sku`, `o.lines[*].qty`
_PATH = r"\w+(?:\.\w+|\[(?:\d+|\*)\])*"
_MEMBERSHIP_PREFIX = re.compile(rf"^\s*(?P<name>{_PATH})\s+{_MEMBERSHIP_OPS}\s+")
# "D ⊂ R/Z/N" / "D \sub R/Z/N" / "D \subset R/Z/N", a type refinement,
# found anywhere in the binding text rather than anchored to the end, so
# a missing-value override (∪ {∅} / \ {∅}, below) reads naturally on
# either side of it ("[0,10] ⊂ Z ∪ {∅}" or "[0,10] ∪ {∅} ⊂ Z"). The
# Unicode blackboard-bold letters are accepted here too, matching how
# `domain_desc()` (symbolic/_proof_support.py) already renders this
# clause on output; render_domain() below does the same, so a domain
# it prints is always valid input again, round-trip.
_SUBSET_OPS = r"(?:\\subset|\\sub|subset|⊂)"
# Beyond the canonical R/Z/N (and their Unicode blackboard-bold spellings),
# a `⊂`/`subset` clause also accepts the common-language type names,
# "integer"/"int" for Z, "real"/"float" for R, normalized to the same
# canonical letter immediately below via _SUBSET_ASCII, same as the
# Unicode letters already are. Scoped to this clause only, not the bare
# `x in Z`/`x in R` spelling (_PIECE_NAMED), unrequested there. A bare
# `:float`/`:int` colon annotation, attached directly to a bound with no
# space (`[1,100]:float`), is a second spelling of the exact same clause,
# matching a Python type annotation rather than requiring the
# `subset`/`⊂` keyword, see render_domain's own ascii-mode preference
# for this spelling over `subset R`/`subset Z`.
_SUBSET_ANYWHERE = re.compile(
    rf"\s*(?:{_SUBSET_OPS}\s+|:\s*)(?P<type>R|Z|N|C|ℝ|ℤ|ℕ|ℂ|real|float|integer|int|complex)\s*")
_SUBSET_ASCII = {"ℝ": "R", "ℤ": "Z", "ℕ": "N", "ℂ": "C",
                "real": "R", "float": "R", "integer": "Z", "int": "Z",
                "complex": "C"}
# "D \ {v1, v2, ...}" / "D, exclude={v1, v2, ...}", a trailing
# exclusion, subtracted from whatever D's own pieces already cover.
# `_EXCLUDE_SUFFIX` is the inline spelling, anchored to the end of one
# binding's own text; `_STANDALONE_EXCLUDE` is the keyword spelling,
# which arrives as its OWN comma-separated part (see
# `_merge_exclude_keyword_parts`) and is spliced onto the binding that
# precedes it before either regex here ever runs.
_EXCLUDE_SUFFIX = re.compile(r"\s*(?:\\|exclude\s*=)\s*\{\s*(?P<set>.*?)\s*\}\s*$")
_STANDALONE_EXCLUDE = re.compile(r"^\s*exclude\s*=\s*\{\s*(?P<set>.*?)\s*\}\s*$")
# "D1 | D2" / "D1 ∪ D2", a union of two or more pieces within one
# binding's own domain expression (after the membership prefix and any
# trailing exclusion/type-refinement clauses have already been peeled
# off it).
_UNION_SPLIT = re.compile(r"\s*(?:\||∪)\s*")
# One union piece: an interval (either spelling, `(0, 1]` bracket
# semantics as ever), a discrete set, or a bare named set (R/Z/N),
# the same three shapes `split_quantifier()` always supported, just
# without the "name in" prefix, since a piece after the first `|`/`∪`
# never repeats it.
_PIECE_RANGE = re.compile(r"^([\[\(])\s*([^,]+?)\s*,\s*\.\.\.\s*,\s*(.+?)\s*([\]\)])$")
_PIECE_INTERVAL = re.compile(r"^([\[\(])\s*([^,]+?)\s*,\s*(.+?)\s*([\]\)])$")
_PIECE_SET = re.compile(r"^\{\s*(.*?)\s*\}$")
_PIECE_NAMED = re.compile(r"^(R|Z|N|C|ℝ|ℤ|ℕ|ℂ)$")
# a language piece, `L[ascii]`, `L[latin-1]`, `L[myapp.models.Order]`:
# a name, or a dotted path an adaptor resolves; the double-struck `𝕃`
# (U+1D543) is the same piece on input. A bare `L` is not a piece (it
# is refused, as any unknown bare name is), so `L^2` never reads as a
# space.
_PIECE_LANGUAGE = re.compile(
    r"^(?:L|\U0001d543)\[\s*(?P<name>[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)*)\s*"
    r"(?:,\s*(?P<refine>.+?))?\s*\]$")
# a refinement inside a language piece, `L[ascii, len <= 80]`,
# `L[json, depth <= 6]`: a key and one bound, or a key and an interval
# of whole numbers; the key means whatever the language that serves it
# says, and core reads none of them
_REFINE_BOUND = re.compile(r"^(?P<key>[A-Za-z_]\w*)\s*(?P<op><=|<|>=|>)\s*(?P<n>\d+)$")
_REFINE_INTERVAL = re.compile(
    r"^(?P<key>[A-Za-z_]\w*)\s+in\s+(?P<lb>[\[(])\s*(?P<lo>\d+)\s*,\s*(?P<hi>\d+)\s*"
    r"(?P<rb>[\])])$")
# Sampling-intensity modifiers, not a parameter binding at all: `n=500`
# in the same comma-list sets domain["n"] (how many draws/rows, not a
# bound on any variable); domain means scope *and* intensity of
# verification, not just numeric range.
_BINDING_INTENSITY = re.compile(r"^\s*n\s*=\s*(\d+)\s*$")
# something that reads as a path binding but is not a path, refused by
# name rather than left to read as a second relation
_PATH_LIKE_BINDING = re.compile(
    rf"^\s*(?P<path>\w+[.\[][^\s]*)\s+{_MEMBERSHIP_OPS}\s+")
_BOUND_CONSTS = {"pi": math.pi, "-pi": -math.pi, "e": math.e,
                 "oo": math.inf, "-oo": -math.inf,
                 "infinity": math.inf, "-infinity": -math.inf}
# a discrete-set member written as a whole number, which stays an int
# rather than going through _bound()'s float(), see _set_value()
_INTEGER_MEMBER = re.compile(r"^[+-]?\d+$")


def _set_value(s: str, *, in_element: bool = False):
    """One element of a discrete-set domain (`x in {...}`): a sentinel
    (`None`/`absent` for absence, `∅`/`missing` for the hole class,
    `nan`/`NA`/`null`/`NaT` or a defined spelling for one hole member;
    checked first since none of these could plausibly mean anything
    else in this position, and inside an element clause a `None` is the
    `null` member),
    a quoted string literal, a bare `True`/`False`, or else the same
    numeric/named-constant parsing _bound() does for interval bounds.
    Kept separate from _bound() rather than widening what an interval
    bound accepts, an interval [lo, hi] over strings or booleans isn't
    a thing, but a discrete set of them (`scale in {"info", "linear"}`,
    `x_discrete in {True}`) is a real, useful domain shape for a branch
    condition tested against a string or boolean parameter. Checked
    before _bound() specifically because bool is a subclass of int in
    Python; `_bound("True")` would otherwise raise, not silently
    return the wrong type, but the explicit check here is what makes
    `True`/`False` produce real Python bools rather than failing to
    parse at all.

    A bare integer literal stays an `int`, where an interval endpoint
    would become a float: the members of `{1, 2, 3}` are the integers
    themselves, and rendering them back as `{1.0, 2.0, 3.0}` would
    describe a different set than the one written."""
    s = s.strip()
    sentinel = _sentinel_of(s, in_element=in_element)
    if sentinel is not None:
        return sentinel
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    if s in ("True", "False"):
        return s == "True"
    if _INTEGER_MEMBER.match(s):
        return int(s)
    return _bound(s)


def _bound(s: str):
    s = s.strip()
    if s in _BOUND_CONSTS:
        return _BOUND_CONSTS[s]
    try:
        return float(s)   # handles "-1.5", "1e6", "inf", "-inf"
    except ValueError:
        pass
    folded = _const_fold(s)
    if folded is not None:
        return folded
    # a complex corner literal ("1+2j", "-1-1.5i"): the i-suffix
    # spelling converts to the j one Python parses natively. `i\b`
    # never touches "inf" (no word boundary between i and n).
    candidate = re.sub(r"i\b", "j", s.replace(" ", ""))
    value = complex(candidate)   # ValueError propagates as before
    return value if value.imag != 0 else value.real


def _const_fold(s: str):
    """Intent:
        A bound endpoint written as constant arithmetic (`10**6`,
        `2*pi`, `1/3`, `-(2**31)`) folded to its numeric value;
        `for M in [1, 10**6]` is how a person writes a million, and
        refusing it taught nothing. Only pure arithmetic over numeric
        literals and the named constants (`pi`, `e`, `oo`) folds; any
        free name means this is not a constant, and the caller's own
        error path stands.
    """
    import ast as _ast
    consts = {"pi": math.pi, "e": math.e, "oo": math.inf, "inf": math.inf}
    try:
        tree = _ast.parse(s, mode="eval").body
    except SyntaxError:
        return None

    def fold(node):
        if isinstance(node, _ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, _ast.Name) and node.id in consts:
            return consts[node.id]
        if isinstance(node, _ast.UnaryOp) and isinstance(node.op, (_ast.USub, _ast.UAdd)):
            v = fold(node.operand)
            return None if v is None else (-v if isinstance(node.op, _ast.USub) else v)
        if isinstance(node, _ast.BinOp):
            ops = {_ast.Add: lambda a, b: a + b, _ast.Sub: lambda a, b: a - b,
                   _ast.Mult: lambda a, b: a * b, _ast.Div: lambda a, b: a / b,
                   _ast.Pow: lambda a, b: a ** b}
            op = ops.get(type(node.op))
            if op is None:
                return None
            a, b = fold(node.left), fold(node.right)
            if a is None or b is None:
                return None
            try:
                return float(op(a, b))
            except (OverflowError, ZeroDivisionError, ValueError):
                return None
        return None

    return fold(tree)


class Interval(tuple):
    """A domain interval `(lo, hi)`, open or closed per endpoint;
    `[` is closed, `(` is open, matching ordinary interval notation, so
    `(0, 1]` and `[0, 1]` are genuinely different domains, not folded
    together the way they used to be. Behaves exactly like a plain
    `(lo, hi)` tuple everywhere existing code already treats a domain
    interval as one (`isinstance(bounds, tuple)`, `lo, hi = bounds`),
    only code that specifically wants the exact boundary semantics
    needs to read `.closed_lo`/`.closed_hi`, everything else keeps
    working unchanged. Defaults to closed on both ends, the same
    semantics a bare `(lo, hi)` tuple already had."""
    def __new__(cls, lo: float, hi: float, closed_lo: bool = True,
               closed_hi: bool = True):
        self = super().__new__(cls, (lo, hi))
        self.closed_lo = closed_lo
        self.closed_hi = closed_hi
        return self

    def __repr__(self) -> str:
        left = "[" if self.closed_lo else "("
        right = "]" if self.closed_hi else ")"
        return f"{left}{self[0]}, {self[1]}{right}"


class ReachInterval(Interval):
    """The computation's reading of an unbounded direction: an
    `Interval` whose `reach_lo`/`reach_hi` end is the finite magnitude
    (the pseudo-infinity, else the number representation's maximum)
    standing in for an infinite end, closed there. A sampler reads the
    marked end as unbounded, drawing log-uniformly over the decades up to
    it, and every other consumer sees an ordinary finite interval. `bare`
    marks a parameter no domain was declared for, sampled as an undeclared
    parameter is, plus the far draws."""
    def __new__(cls, lo: float, hi: float, closed_lo: bool = True,
                closed_hi: bool = True, *, reach_lo: bool = False,
                reach_hi: bool = False, bare: bool = False):
        self = super().__new__(cls, lo, hi, closed_lo, closed_hi)
        self.reach_lo = reach_lo
        self.reach_hi = reach_hi
        self.bare = bare
        return self


class _Sentinel:
    """A missing value as a domain states it, never a value a function
    receives. Two kinds: `absent` is the absence of the object (the
    parameter, the container, the field is `None`), and `missing` is a
    hole in a slot, an element-wise value with no computable content.
    A hole sentinel names either the whole class (`member` None, spelled
    `missing` or `∅`) or one member of it (`nan`, `NA`, `null`, `NaT`,
    or a spelling a definition row adds). Equal and hashed by
    `(kind, member)`, so `MISSING in dom.excluded` is a plain membership
    test whichever spelling produced it."""
    __slots__ = ("kind", "member")

    def __init__(self, kind: str, member: "str | None" = None) -> None:
        self.kind = kind
        self.member = member

    @property
    def word(self) -> str:
        """The canonical ascii word: `None`, `missing`, or the member."""
        if self.kind == "absent":
            return "None"
        return self.member if self.member is not None else "missing"

    def __repr__(self) -> str:
        if self.kind == "missing" and self.member is None:
            return "∅"
        return self.word

    def __eq__(self, other) -> bool:
        return (isinstance(other, _Sentinel) and self.kind == other.kind
                and self.member == other.member)

    def __hash__(self) -> int:
        return hash(("mathema.sentinel", self.kind, self.member))

    def __reduce__(self):
        return (_Sentinel, (self.kind, self.member))


#: the older name of the sentinel type
_MissingType = _Sentinel

#: a hole in a slot, the whole class: every member the slot type has
MISSING = _Sentinel("missing")
#: the absence of the object
ABSENT = _Sentinel("absent")


def member(name: str) -> _Sentinel:
    """The hole sentinel naming one member of the class, `member("nan")`."""
    return _Sentinel("missing", str(name))


#: spellings of absence: at the top level of a binding they set
#: `Domain.absent`; inside an element clause a `None` is the `null` hole
_ABSENCE_TOKENS = frozenset({"None", "absent"})
#: spellings of a hole: the class (`∅`, `missing`) and the built-in
#: members; a definition row adds the spellings it names
_HOLE_TOKENS = {"∅", "missing", "nan", "NA", "null", "NaT"}
#: the class spellings among the hole tokens
_CLASS_TOKENS = frozenset({"∅", "missing"})
#: every sentinel spelling, the older name
_MISSING_TOKENS = _HOLE_TOKENS | _ABSENCE_TOKENS


def sentinel_tokens() -> frozenset:
    """Every word read as a sentinel: the absence words and the hole
    words, defined spellings included."""
    return frozenset(_ABSENCE_TOKENS | _HOLE_TOKENS)


def add_hole_spelling(word: str) -> None:
    """Read `word` as a hole member from now on (a definition row's
    spelling, `NaN` for a runtime that spells its hole that way)."""
    _HOLE_TOKENS.add(str(word))


def _sentinel_of(token: str, *, in_element: bool = False) -> "_Sentinel | None":
    """The sentinel a word spells, or None when it spells none. A `None`
    inside an element clause is the `null` member of the hole class."""
    token = token.strip()
    if token in _ABSENCE_TOKENS:
        return member("null") if in_element else ABSENT
    if token in _CLASS_TOKENS:
        return MISSING
    if token in _HOLE_TOKENS:
        return member(token)
    return None


def is_sentinel(value) -> bool:
    """Whether `value` is one of this module's sentinels."""
    return isinstance(value, _Sentinel)


def is_hole_sentinel(value) -> bool:
    """Whether `value` is a hole sentinel, the class or a member."""
    return isinstance(value, _Sentinel) and value.kind == "missing"


# Type names of known missing-value sentinels that aren't themselves
# IEEE-754 NaN-like (pandas' pd.NA/pd.NaT: `pd.NA != pd.NA` is itself a
# non-boolean NA, not a clean True/False, so the self-inequality check
# below can't see them), checked by name only, no import of the
# library that defines them, so this stays extensible (another
# library's own null type name is one more string here) without ever
# turning pandas, or anything else, into a hard dependency of core.
_MISSING_TYPE_NAMES = frozenset({"NAType", "NaTType"})
_MEMBER_TYPE_NAMES = {"NAType": "NA", "NaTType": "NaT"}


def is_missing(value) -> bool:
    """A value is missing if it's `None`, one of this module's
    sentinels, IEEE-754 NaN (self-inequality catches a Python `float`, a
    numpy `float64`, and a pandas float uniformly, all three being
    ordinary IEEE-754 under the hood, with no import of any of them
    needed), or one of a small, extensible set of known missing-
    sentinel type names checked by name alone. This is the slot
    reading: a `None` held in a slot is the `null` hole."""
    if value is None or isinstance(value, _Sentinel):
        return True
    try:
        if value != value:
            return True
    except Exception:
        pass
    return type(value).__name__ in _MISSING_TYPE_NAMES


def is_absent(value) -> bool:
    """Whether `value` is the absence of an object: `None`, or the
    absence sentinel."""
    return value is None or value == ABSENT


def member_of(value) -> "str | None":
    """The member word a missing slot value is (`nan`, `NA`, `NaT`, and
    `null` for a `None` held in a slot), the sentinel's own word for a
    sentinel, or None for a value that is not missing."""
    if isinstance(value, _Sentinel):
        return value.word
    if value is None:
        return "null"
    name = _MEMBER_TYPE_NAMES.get(type(value).__name__)
    if name is not None:
        return name
    try:
        if value != value:
            return "nan"
    except Exception:
        return None
    return None


# transitional alias: is_missing was _is_missing until the 2026-08
# refactor; slated for removal once nothing references the old name.
_is_missing = is_missing


@dataclass(frozen=True)
class LanguageRef:
    """One language piece of a domain, `L[ascii]`: the name a language
    resolves under (`mathema.languages.resolve_language`). It sits in
    `Domain.pieces` beside an `Interval` or a `frozenset`, under
    `base_type` `"L"`, so a union with a finite set, an exclusion and
    the missing-value policy all read as they do for a numeric domain.
    Membership, sampling and the record's description of the language
    all go through the resolved `Language`; nothing here interprets
    the name. A frozen dataclass rather than a tuple, since every
    interval test in this module reads a tuple piece as `(lo, hi)`."""
    name: str
    #: the refinements the piece carries, `(key, Interval)` pairs in key
    #: order (`L[json, depth <= 6, nodes <= 200]`); a key is served by
    #: whatever refinement is registered under it
    refinements: tuple = ()

    def refinement(self, key: str):
        """The interval refinement `key` states, or None."""
        return dict(self.refinements).get(key)

    @property
    def text(self) -> str:
        """What sits inside the brackets: the name, then each
        refinement, `json, depth <= 6, nodes <= 200`."""
        return ", ".join([self.name, *(render_refinement(key, interval)
                                       for key, interval in self.refinements)])

    def __repr__(self) -> str:
        return f"L[{self.text}]"


def _whole(v) -> str:
    return str(int(v)) if float(v).is_integer() else str(v)


def render_refinement(key: str, interval) -> str:
    """A refinement as text: `key <= 80` or `key < 80` for an upper
    bound from zero, `key >= 1` or `key > 20` for a lower bound alone,
    and `key in [1, 80]` for both."""
    lo, hi = interval[0], interval[1]
    closed_lo = getattr(interval, "closed_lo", True)
    closed_hi = getattr(interval, "closed_hi", True)
    if hi == float("inf"):
        return f"{key} {'>=' if closed_lo else '>'} {_whole(lo)}"
    if lo == 0 and closed_lo:
        return f"{key} {'<=' if closed_hi else '<'} {_whole(hi)}"
    return (f"{key} in {'[' if closed_lo else '('}{_whole(lo)}, "
            f"{_whole(hi)}{']' if closed_hi else ')'}")


def refinement_range(interval) -> "tuple[int, int | None]":
    """The closed range of whole numbers a refinement keeps, the upper
    end None when unbounded."""
    lo, hi = interval[0], interval[1]
    first = int(lo) if getattr(interval, "closed_lo", True) else int(lo) + 1
    if hi == float("inf"):
        return first, None
    last = int(hi) if getattr(interval, "closed_hi", True) else int(hi) - 1
    return first, last


def _parse_refinement(text: str, whole: str) -> tuple:
    """`(key, Interval)` for one refinement, or InvalidDomain naming the
    spellings that are read."""
    t = text.strip()
    m = _REFINE_BOUND.match(t)
    if m is not None:
        key, n, op = m.group("key"), float(m.group("n")), m.group("op")
        interval = {"<=": Interval(0.0, n), "<": Interval(0.0, n, True, False),
                    ">=": Interval(n, float("inf")),
                    ">": Interval(n, float("inf"), False, True)}[op]
    else:
        m = _REFINE_INTERVAL.match(t)
        if m is None:
            raise InvalidDomain(
                f"{whole!r}: a language refinement is `key <= n`, `key < n`, "
                f"`key >= n`, `key > n` or `key in [lo, hi]` with whole "
                f"numbers, `len <= 80` or `depth in [1, 6]`; {t!r} is not one")
        key = m.group("key")
        interval = Interval(float(m.group("lo")), float(m.group("hi")),
                            m.group("lb") == "[", m.group("rb") == "]")
    first, last = refinement_range(interval)
    if last is not None and last < max(first, 0):
        raise InvalidDomain(f"{whole!r}: no {key} satisfies {t!r}")
    return key, interval


def _parse_refinements(text: str, whole: str) -> tuple:
    """Every refinement a piece states, in key order; a key stated twice
    is refused."""
    found: dict = {}
    for part in _split_commas(text):
        key, interval = _parse_refinement(part, whole)
        if key in found:
            raise InvalidDomain(f"{whole!r}: the refinement {key!r} is stated twice")
        found[key] = interval
    return tuple(sorted(found.items()))


_PATH_STEP = re.compile(r"\.(\w+)|\[(\d+|\*)\]")


def path_steps(path: str) -> "list[str | int]":
    """The steps of a path after its root: a field name, an index, or
    `"*"` for every element (`.lines[*].qty` is `["lines", "*",
    "qty"]`)."""
    steps: list = []
    for field_name, index in _PATH_STEP.findall(path):
        steps.append(field_name if field_name else ("*" if index == "*" else int(index)))
    return steps


def path_values(value, steps) -> list:
    """Intent:
        Every value a path reaches from `value`: one, or one per element
        where a step is `"*"`. A step through an absent field, a `None`,
        or an index past the end reaches `None`, the absence of what
        the path names; a hole the path reaches (a NaN field) is the
        value itself. Walked with an explicit stack, never by
        recursion.
    """
    out: list = []
    stack = [(value, 0)]
    while stack:
        current, i = stack.pop()
        if i == len(steps):
            out.append(current)
            continue
        step = steps[i]
        if current is None or is_missing(current):
            out.append(None)
            continue
        if step == "*":
            try:
                items = list(current)
            except TypeError:
                out.append(None)
                continue
            stack.extend((item, i + 1) for item in reversed(items))
            continue
        if isinstance(step, int):
            try:
                stack.append((current[step], i + 1))
            except (IndexError, KeyError, TypeError):
                out.append(None)
            continue
        if isinstance(current, dict):
            stack.append((current[step], i + 1) if step in current else (None, len(steps)))
        elif hasattr(current, step):
            stack.append((getattr(current, step), i + 1))
        else:
            out.append(None)
    return out


def path_bindings_hold(value, root: str, bindings: dict) -> bool:
    """Intent:
        Whether every path binding rooted at `root` (`{"o.lines[*].qty":
        bound}`) holds of `value`: every value the path reaches is in
        its bound.
    """
    for key, bound in bindings.items():
        if not (key.startswith(root + ".") or key.startswith(root + "[")):
            continue
        for leaf in path_values(value, path_steps(key[len(root):])):
            try:
                if not domain_contains(leaf, bound):
                    return False
            except Exception:
                return False
    return True


def language_ref(text: str) -> "LanguageRef | None":
    """The `LanguageRef` the inside of `L[...]` spells (`unicode`,
    `unicode, len <= 80`), or None when it spells none."""
    m = _PIECE_LANGUAGE.match(f"L[{text}]")
    if m is None:
        return None
    refine = m.group("refine")
    return LanguageRef(m.group("name"), _parse_refinements(refine, text) if refine else ())


@dataclass(frozen=True)
class Domain:
    """A domain that's more than one bare `Interval`/`"Z"`/`"N"`/
    `frozenset` (`split_quantifier()`'s original three shapes): a union
    of one or more `pieces` (each an `Interval`, a discrete-value
    `frozenset`, or under `base_type` `"L"` a `LanguageRef`),
    restricted to `base_type` (`"R"`/`"Z"`/`"N"`/`"C"`/`"L"`), minus
    whatever concrete values sit in `excluded` (which may include
    `MISSING`). Every domain the rest of the codebase already produces
    is the trivial case of this shape, `split_quantifier()` only
    builds a real `Domain` when a binding actually uses exclusion,
    union, or an explicit type refinement; an ordinary `x in [0, 1]`
    still comes back a bare `Interval`, unchanged. `domain_contains()`,
    not this class directly, is what every consumer should call through
    to test membership; it normalizes either shape first. `explicit_
    type` records whether the *binding's own text* actually stated a
    type (`⊂ Z`/`subset R`/a bare `x in Z`) as opposed to `base_type`
    defaulting to `"R"` for some other reason (a union/exclusion on an
    otherwise-untyped domain); this is a real, separate bit of
    information from `excluded`/`MISSING` (missing-value policy no
    longer implies anything about whether a type was stated, and never
    should again, see `parse_binding()`)."""
    base_type: str = "R"
    pieces: tuple = ()
    excluded: frozenset = frozenset()
    explicit_type: bool = False
    # dimension names of a VECTOR/MATRIX space, empty for a scalar.
    # When present, `pieces`/`base_type`/`excluded` describe the
    # ELEMENT domain and the whole renders as `<element>^<dims>`
    # (`[0,1]^n`, `R^(m*n)`): the value is a nested sequence of that
    # element type with these outer dimensions. `dim(param, k)`
    # measures the k-th dim, and each name is a first-class symbol in
    # a premise or law.
    dims: tuple = ()
    # the object itself may be absent (`None`): the parameter, or the
    # whole vector or matrix of a space
    absent: bool = False
    # the members the hole class stands for on this slot type, resolved
    # once by `complete()` from the annotation, the runtime type and the
    # definition rows (`("nan",)` for a float slot); never rendered, the
    # class renders as its word
    members: tuple = field(default=(), compare=False)


# the closed vocabulary of base types a Domain may carry. Every
# function that projects a domain into sympy or answers membership
# checks against this set and refuses an unknown name loudly, an
# unrecognized type silently treated as real is a wrong proof waiting
# to happen, not a default. `"L"` is a language domain (`L[ascii]`):
# its pieces are `LanguageRef`s and finite sets, it has no real-set
# reading, and its members are strings or structured values.
KNOWN_BASE_TYPES = frozenset({"R", "Z", "N", "C", "L"})


def _require_known_base_type(base_type: str) -> None:
    """Intent:
        Refuse an unrecognized base type before any real-only machinery
        can act on it.

    Raises:
        InvalidDomain: when `base_type` is not in `KNOWN_BASE_TYPES`.
    """
    if base_type not in KNOWN_BASE_TYPES:
        raise InvalidDomain(
            f"unknown domain base type {base_type!r}: known types are "
            + ", ".join(sorted(KNOWN_BASE_TYPES)))


def _real_scalar(value):
    """Intent:
        The value as a real number for membership tests, or `None` when
        it has no real reading (a genuinely imaginary complex, a bool,
        a non-numeric object).

    Notes:
        A `complex` with zero imaginary part reads as its real part
        (3+0j is the number 3); one with a nonzero imaginary part is
        not a member of any R/Z/N domain.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, complex):
        return value.real if value.imag == 0 else None
    return None


def _as_domain(bound) -> Domain:
    """Intent:
        Normalize any of split_quantifier()'s domain-value shapes into
        a Domain. Shared entry point for domain_contains() and
        render_domain().

    Notes:
        A bare "Z"/"N" string is a named type, which states the whole
        missing-value policy (nothing admitted); a bare interval states
        none of it. A hand-built Domain object is returned unchanged.
    """
    if bound is None:
        return Domain()
    if isinstance(bound, Domain):
        return bound
    if isinstance(bound, LanguageRef):
        return Domain(base_type="L", pieces=(bound,), explicit_type=True)
    if isinstance(bound, str):
        return Domain(base_type=bound, explicit_type=True)
    if isinstance(bound, frozenset):
        return Domain(pieces=(bound,))
    if isinstance(bound, tuple):
        return Domain(pieces=(bound,))
    return Domain()


# --- the missing-value policy of a domain ------------------------------
#
# A domain states two things about missing values: whether the object
# may be absent (`absent`) and which holes a slot may hold (sentinel
# pieces). A domain with a type clause, a named type, a language, or an
# enumerated set states both (what it does not admit it excludes); a
# bare interval states neither, and `complete()` fills each unstated
# kind from the parameter's annotation.


@dataclass(frozen=True)
class MissingDefaults:
    """What an annotation implies about missing values: whether the
    object may be absent, the members of the hole class on its slots
    (empty when the slot type has no hole), the slot type named in the
    note that states the resolution, whether an annotation said so, and
    the spellings the object's absence is realised as."""
    absent: bool
    members: tuple
    slot_type: str
    annotated: bool = True
    absence: tuple = ("None",)


#: the defaults of a parameter with no annotation, and of a claim read
#: without its function: the object may be absent and a slot may hold
#: the scalar runtime's own hole
NO_ANNOTATION = MissingDefaults(True, ("nan",), "unannotated", annotated=False)


def _is_enumerated(dom: Domain) -> bool:
    """A domain that lists its members: every piece a finite set. A
    named type with only sentinels beside it (`R|missing`) is the whole
    type, not a set of sentinels."""
    if not dom.pieces or not all(isinstance(p, frozenset) for p in dom.pieces):
        return False
    return not dom.explicit_type or any(
        not isinstance(v, _Sentinel) for p in dom.pieces for v in p)


def _sentinel_piece(piece) -> bool:
    return (isinstance(piece, frozenset) and bool(piece)
            and all(isinstance(v, _Sentinel) for v in piece))


def stated(bound) -> bool:
    """Whether a domain states its whole missing-value policy: a type
    clause or named type, a language, or an enumerated set."""
    dom = _as_domain(bound)
    return dom.explicit_type or dom.base_type == "L" or _is_enumerated(dom)


def _set_sentinels(dom: Domain) -> list:
    return [v for p in dom.pieces if isinstance(p, frozenset)
            for v in p if isinstance(v, _Sentinel)]


def admitted(bound, defaults: "MissingDefaults | None" = None) -> tuple:
    """Intent:
        `(absent, holes)`: whether the domain admits the absence of the
        object, and the hole sentinels it admits (the class, members),
        each kind the domain does not state read from `defaults`
        (`NO_ANNOTATION` when not given).
    """
    dom = _as_domain(bound)
    defaults = defaults or NO_ANNOTATION
    listed = _set_sentinels(dom)
    if _is_enumerated(dom):
        return (ABSENT in listed,
                tuple(s for s in listed if s.kind == "missing"))
    holes = tuple(s for s in listed if s.kind == "missing")
    is_stated = stated(dom)
    if dom.absent or ABSENT in listed:
        absent = True
    elif is_stated or ABSENT in dom.excluded:
        absent = False
    else:
        absent = defaults.absent
    if not holes and not is_stated \
            and not any(is_hole_sentinel(v) for v in dom.excluded):
        holes = (MISSING,) if defaults.members else ()
    return absent, holes


def admits(bound, sentinel) -> bool:
    """Whether the domain admits `sentinel`: the absence sentinel, the
    class, or one member (admitted by name, or through the class when
    the domain's resolved members include it or are unresolved)."""
    absent, holes = admitted(bound)
    if sentinel == ABSENT:
        return absent
    if sentinel in holes:
        return True
    if isinstance(sentinel, _Sentinel) and sentinel.member is not None \
            and MISSING in holes:
        members = _as_domain(bound).members
        return not members or sentinel.member in members
    return sentinel == MISSING and bool(holes)


def numeric_excluded(dom: Domain) -> frozenset:
    """The values a domain excludes, its sentinels left out."""
    return frozenset(v for v in dom.excluded if not isinstance(v, _Sentinel))


def complete(bound, defaults: MissingDefaults):
    """Intent:
        The domain with every kind it does not state filled from
        `defaults`: absence admitted (`absent`) or excluded (the absence
        sentinel in `excluded`), the hole class admitted (a `{missing}`
        piece) or excluded, and the class's resolved members recorded
        on `members`. A stated domain keeps its own policy and gains the
        resolution; an enumerated set is exactly its members and gains
        only the resolution of a listed class. `None` stays `None`.
    """
    if bound is None:
        return None
    dom = _as_domain(bound)
    if _is_enumerated(dom):
        if MISSING not in _set_sentinels(dom):
            return bound
        return Domain(base_type=dom.base_type, pieces=dom.pieces,
                      excluded=dom.excluded, explicit_type=dom.explicit_type,
                      dims=dom.dims, absent=dom.absent,
                      members=tuple(defaults.members))
    absent, holes = admitted(dom, defaults)
    pieces = [p for p in dom.pieces if not _sentinel_piece(p)]
    excluded = set(dom.excluded)
    if holes:
        pieces.append(frozenset(holes))
    elif not any(is_hole_sentinel(v) for v in excluded):
        excluded.add(MISSING)
    if not absent:
        excluded.add(ABSENT)
    members: tuple = ()
    if MISSING in holes:
        members = tuple(defaults.members)
    elif holes:
        members = tuple(s.member for s in holes if s.member is not None)
    return Domain(base_type=dom.base_type, pieces=tuple(pieces),
                  excluded=frozenset(excluded), explicit_type=dom.explicit_type,
                  dims=dom.dims, absent=absent, members=members)


def _piece_contains(value, piece) -> bool:
    if isinstance(piece, frozenset):
        return value in piece
    if isinstance(piece, str):
        if piece == "Z":
            return isinstance(value, int) and not isinstance(value, bool)
        if piece == "N":
            return isinstance(value, int) and not isinstance(value, bool) and value >= 0
        return _real_scalar(value) is not None   # "R": any real number
    lo, hi = piece
    value = _real_scalar(value)
    if value is None:
        return False
    closed_lo = getattr(piece, "closed_lo", True)
    closed_hi = getattr(piece, "closed_hi", True)
    lo_ok = value >= lo if closed_lo else value > lo
    hi_ok = value <= hi if closed_hi else value < hi
    return lo_ok and hi_ok


def _piece_contains_complex(value, piece) -> bool:
    """Intent:
        Membership of a (possibly complex) number in a piece of a
        C-typed domain: a discrete set by membership; anything else
        declines in v1 (interval pieces have no complex reading until
        a region shape lands).
    """
    if isinstance(piece, frozenset):
        return value in piece
    lo, hi = piece
    if isinstance(lo, complex) or isinstance(hi, complex):
        # two complex corner literals name the axis-aligned rectangle
        # between them (closed; corner order free)
        z = complex(value)
        lo, hi = complex(lo), complex(hi)
        return (min(lo.real, hi.real) <= z.real <= max(lo.real, hi.real)
                and min(lo.imag, hi.imag) <= z.imag <= max(lo.imag, hi.imag))
    # an interval piece under C with real endpoints reads as the real
    # segment it names (a legitimate region of the plane)
    return _piece_contains(value, piece)


def _safe_in(value, values) -> bool:
    """`value in values` for a value that may not be hashable (a
    mapping member of a schema language), which is then in no set."""
    try:
        return value in values
    except TypeError:
        return False


def _language_piece_contains(value, piece) -> bool:
    """Membership of `value` in one piece of a language domain: a
    `LanguageRef` asks the resolved language, a finite set is checked
    directly, and nothing else is a piece of a language domain."""
    if isinstance(piece, LanguageRef):
        from .languages import resolve_language
        return bool(resolve_language(piece).contains(value))
    if isinstance(piece, frozenset):
        return _safe_in(value, piece)
    return False


def _language_members(dom: "Domain", limit: int):
    """Every member of a language domain when each piece is finite
    and the union has at most `limit` members, else `None`; a
    language answering `members(limit)` with more than `limit` values
    is read as infinite, never as a prefix to sweep."""
    from .languages import resolve_language
    out: list = []
    for piece in dom.pieces:
        if isinstance(piece, frozenset):
            values = [v for v in piece if not isinstance(v, _Sentinel)]
        elif isinstance(piece, LanguageRef):
            members = resolve_language(piece).members(limit)
            if members is None or len(members) > limit:
                return None
            values = list(members)
        else:
            return None
        for v in values:
            if not _safe_in(v, out):
                out.append(v)
        if len(out) > limit:
            return None
    out = [v for v in out if not _safe_in(v, dom.excluded)]
    if not out:
        return None
    return tuple(sorted(out, key=_member_sort_key))


def _pandas_value(name: str):
    def value():
        import importlib
        return getattr(importlib.import_module("pandas"), name)
    return value


#: how each member word is realised as the value a function receives;
#: a definition row's spelling registers its own (`register_spelling`)
_SPELLING_VALUES: dict = {"nan": lambda: math.nan, "null": lambda: None,
                          "NA": _pandas_value("NA"), "NaT": _pandas_value("NaT")}


def register_spelling(word: str, realise) -> None:
    """Realise the member `word` by calling `realise()` from now on, and
    read `word` as a hole member in claim text."""
    _SPELLING_VALUES[str(word)] = realise
    add_hole_spelling(word)


#: how each spelling of absence is realised; `None` is Python's own
_ABSENCE_VALUES: dict = {"None": lambda: None}


def register_absence_spelling(word: str, realise) -> None:
    """Realise the absence spelling `word` by calling `realise()`."""
    _ABSENCE_VALUES[str(word)] = realise


def spelling_value(word: str):
    """The value the member `word` is realised as.

    Raises:
        KeyError: no realiser is known for `word`.
        ImportError: the library that holds the value is not installed.
    """
    return _SPELLING_VALUES[word]()


def realise_sentinel(sentinel, members: tuple = (), absence: tuple = ()) -> list:
    """Intent:
        The concrete values a sentinel stands for, the ones a function
        is called with: for absence one value per spelling in `absence`
        (Python's `None` when none are given), for the class one value
        per member of `members` (the scalar runtime's `nan` when none
        were resolved), for a member the member's own value. A spelling
        whose value cannot be built here (its library is not installed)
        is left out.
    """
    if sentinel == ABSENT:
        out = []
        for word in tuple(absence) or ("None",):
            realise = _ABSENCE_VALUES.get(word)
            if realise is not None:
                out.append(realise())
        return out
    words = (tuple(members) or ("nan",)) if sentinel.member is None \
        else (sentinel.member,)
    out = []
    for word in words:
        try:
            out.append(spelling_value(word))
        except (KeyError, ImportError):
            continue
    return out


def _realised_members(values, members: tuple, absence: tuple = ()) -> list:
    """Every value of a finite set, each sentinel replaced by the values
    it stands for, the first occurrence of each kept."""
    out: list = []
    seen: set = set()
    for v in values:
        concrete = (realise_sentinel(v, members, absence)
                    if isinstance(v, _Sentinel) else [v])
        for c in concrete:
            key = (type(c).__name__, repr(c))
            if key not in seen:
                seen.add(key)
                out.append(c)
    return out


def finite_members(bound, limit: int, members: "tuple | None" = None,
                   absence: tuple = ()):
    """Intent:
        Every value the domain `bound` admits, as a sorted tuple, when
        there are finitely many of them and no more than `limit`. `None`
        when the domain is infinite, is not enumerable, or is larger
        than `limit`. A finite set's sentinels are its members and come
        back as the real values a function receives: `None` for
        absence, and for the hole class one value per member of
        `members` (else the domain's resolved members, else `nan`).

    Notes:
        Enumerable means one of two things: a discrete `frozenset` of
        values, or an integer-typed (`Z`/`N`) interval with finite
        endpoints. A bare `Interval` is real-typed and so has
        uncountably many members even when its endpoints are finite;
        it returns `None`, and so does an unbounded `"Z"`/`"N"`.

        Returning `None` past `limit` rather than a truncated tuple is
        the point of the parameter. A caller that enumerates a prefix
        of a domain and reports a clean sweep has sampled, not proved,
        and the distinction is the whole reason this function exists.

        A vector or matrix space (`dims` set) describes a nested value
        whose ELEMENT domain these pieces bound, not a scalar to sweep,
        so it is declined. A language domain is enumerable exactly when
        every language in it answers `members(limit)` with a tuple.
        `excluded` is honoured; a sentinel admitted beside an interval
        or a language is not swept here, only a finite set's listed
        sentinels are.
    """
    if isinstance(bound, frozenset):
        found = sorted(_realised_members(bound, members or (), absence),
                       key=_member_sort_key)
        return tuple(found) if len(found) <= limit else None
    if isinstance(bound, Domain) and _is_enumerated(bound) \
            and bound.base_type != "L" and not bound.dims \
            and _set_sentinels(bound):
        values = [v for p in bound.pieces for v in p]
        found = [v for v in _realised_members(values, members or bound.members,
                                              absence)
                 if is_missing(v) or not _safe_in(v, numeric_excluded(bound))]
        found = sorted(found, key=_member_sort_key)
        return tuple(found) if found and len(found) <= limit else None
    if isinstance(bound, Domain) and bound.base_type == "L":
        return _language_members(bound, limit)
    if not isinstance(bound, Domain) or bound.dims:
        return None
    if not bound.pieces:
        # no pieces means the whole of the base type, a bare `x in Z`.
        # That is unbounded, and an empty result here would let a sweep
        # report a clean pass over zero points, which proves nothing at
        # all while looking exactly like a proof.
        return None
    if bound.base_type not in ("Z", "N"):
        # a real or complex piece has uncountably many members; only an
        # explicit discrete set under such a type can be swept
        if not bound.pieces or not all(isinstance(p, frozenset)
                                       for p in bound.pieces):
            return None
    out: set = set()
    for piece in bound.pieces:
        if _sentinel_piece(piece):
            continue
        if isinstance(piece, frozenset):
            out |= set(piece)
            continue
        if not isinstance(piece, tuple) or len(piece) != 2:
            return None
        lo, hi = piece
        try:
            lo_f, hi_f = float(lo), float(hi)
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(lo_f) and math.isfinite(hi_f)):
            return None
        first = math.ceil(lo_f) if getattr(piece, "closed_lo", True) \
            else math.floor(lo_f) + 1
        last = math.floor(hi_f) if getattr(piece, "closed_hi", True) \
            else math.ceil(hi_f) - 1
        if last - first + 1 > limit:
            return None
        out |= {int(v) for v in range(int(first), int(last) + 1)}
        if len(out) > limit:
            return None
    if bound.base_type == "N":
        out = {v for v in out if isinstance(v, int) and v >= 0}
    out -= numeric_excluded(bound)
    if not out or len(out) > limit:
        # an empty region is not something to sweep: a clean pass over
        # no points is vacuous, and the convention for an empty region
        # is to say nothing rather than to prove everything (the same
        # rule `_tighten_domain_by_assumption` follows).
        return None
    return tuple(sorted(out, key=_member_sort_key))


def _integer_span(piece, base_type: str):
    """Intent:
        The first and last integers an interval piece admits under an
        integer base type, as `(first, last)`, honouring open ends and
        fractional endpoints; `N` starts no lower than 0. An infinite
        end comes back infinite, and `first > last` means no integer
        lies inside.
    """
    lo, hi = float(piece[0]), float(piece[1])
    closed_lo = getattr(piece, "closed_lo", True)
    closed_hi = getattr(piece, "closed_hi", True)
    if math.isinf(lo):
        first = lo
    else:
        first = math.ceil(lo) if closed_lo else math.floor(lo) + 1
    if math.isinf(hi):
        last = hi
    else:
        last = math.floor(hi) if closed_hi else math.ceil(hi) - 1
    if base_type == "N":
        first = max(first, 0)
    return first, last


def bound_is_empty(bound) -> bool:
    """Intent:
        Whether a declared bound admits no value at all: a reversed
        interval, a degenerate one with an open end (`(1, 1)`,
        `[1, 1)`), or an integer-typed domain none of whose pieces holds
        an integer outside `excluded` (`(0, 1) ⊂ Z`).

    Notes:
        A vector or matrix space, a complex rectangle, a discrete set,
        a bare named set and anything unrecognised read as non-empty:
        the answer is `True` only when emptiness is certain. The
        missing-value policy is not a member of the value set, so a
        domain that admits only a missing value still counts as empty.
    """
    dom = bound if isinstance(bound, Domain) else None
    excluded: frozenset
    if dom is None:
        if not (isinstance(bound, tuple) and not isinstance(bound, frozenset)
                and len(bound) == 2):
            return False
        pieces, base_type, excluded = (bound,), "R", frozenset()
    else:
        if dom.dims or dom.base_type == "C" or not dom.pieces:
            return False
        pieces = tuple(p for p in dom.pieces if not _sentinel_piece(p))
        base_type, excluded = dom.base_type, numeric_excluded(dom)
        if not pieces:
            return False
    for piece in pieces:
        if not (isinstance(piece, tuple) and not isinstance(piece, frozenset)
                and len(piece) == 2):
            return False
        try:
            lo, hi = float(piece[0]), float(piece[1])
        except (TypeError, ValueError):
            return False
        if base_type in ("Z", "N"):
            first, last = _integer_span(piece, base_type)
            if first > last:
                continue
            if math.isinf(first) or math.isinf(last) \
                    or last - first + 1 > len(excluded):
                return False
            if any(v not in excluded for v in range(int(first), int(last) + 1)):
                return False
            continue
        if lo < hi:
            return False
        if lo == hi and getattr(piece, "closed_lo", True) \
                and getattr(piece, "closed_hi", True) and lo not in excluded:
            return False
    return True


def domain_contains(value, bound, slot: bool = False) -> bool:
    """Is `value` a member of the domain `bound` describes, the single
    source of truth every consumer (`authoring.enforce_domain`, the
    derive route's concrete checks, domain-aware probing) calls through,
    rather than each re-deriving membership logic inline (which is
    exactly how `enforce_domain`'s own interval check went silently
    blind to `Interval.closed_lo`/`closed_hi`, checked identically to a
    closed bound for years).

    A missing value is answered by the domain's missing-value policy
    before any piece is compared: a top-level `None` is the absence of
    the object, a member when the domain admits absence; with `slot`
    set a `None` is instead the `null` hole of a slot. A hole (NaN,
    `pd.NA`, `NaT`, a sentinel) is a member when the domain admits the
    class (and, once the class is resolved, the hole is one of its
    members) or admits that member by name. A kind the domain does not
    state reads as admitted, the default of a parameter with no
    annotation."""
    dom = _as_domain(bound)
    _require_known_base_type(dom.base_type)
    if isinstance(value, _Sentinel):
        return admits(dom, value)
    if value is None and not slot:
        return admits(dom, ABSENT)
    if is_missing(value):
        word = member_of(value)
        return admits(dom, member(word)) if word else admits(dom, MISSING)
    if _safe_in(value, dom.excluded):
        return False
    if dom.base_type == "L":
        # a language domain: the resolved language decides, a finite
        # piece by membership, and a number is a member of neither
        return any(_language_piece_contains(value, p) for p in dom.pieces)
    if dom.base_type == "C":
        # the complex plane: any number belongs (the reals embed);
        # discrete pieces and exclusions still apply below.
        if not isinstance(value, (int, float, complex)) or isinstance(value, bool):
            return False
        if not dom.pieces:
            return True
        return any(_piece_contains_complex(value, p) for p in dom.pieces)
    if isinstance(value, complex) and not isinstance(value, (int, float)):
        # a genuinely imaginary value belongs to no R/Z/N domain; one
        # with zero imaginary part is the real number it equals.
        if value.imag != 0:
            return False
        value = value.real
    if dom.base_type == "Z" and not (isinstance(value, int) and not isinstance(value, bool)):
        return False
    if dom.base_type == "N" and not (isinstance(value, int) and not isinstance(value, bool)
                                     and value >= 0):
        return False
    if not dom.pieces:
        return True   # unrestricted within base_type
    return any(_piece_contains(value, p) for p in dom.pieces)


_TYPE_GLYPH = {"R": "ℝ", "Z": "ℤ", "N": "ℕ", "C": "ℂ"}


def _as_int_if_whole(value):
    """`value` as a plain `int` if it's a float/int with no fractional
    part, otherwise `value` unchanged, never silently truncates a
    genuinely fractional bound (`0.5`), only drops a `.0` that was never
    meaningful in the first place."""
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value == value and abs(value) != float("inf")
            and value == int(value)):
        return int(value)
    return value


def _member_sort_key(v):
    """Discrete-set members in a stable, readable order: numbers by
    value, then strings alphabetically, then absence, then the hole
    class, then hole members by name. A realised missing value sorts
    with its sentinel (`None` with absence, NaN with the `nan` member).
    Ordering by `str` alone would put `{1, 10, 2}` in that order and
    would interleave the sentinels with real values."""
    if isinstance(v, _Sentinel):
        if v.kind == "absent":
            return (2, 0.0, "")
        return (3, 0.0, "") if v.member is None else (4, 0.0, v.member)
    if v is None:
        return (2, 0.0, "")
    if isinstance(v, str):
        return (1, 0.0, v)
    word = member_of(v)
    if word is not None:
        return (4, 0.0, word)
    try:
        return (0, float(v), "")
    except (TypeError, ValueError):
        # a member of a finite language that is neither (an enum
        # member, say) sorts after every value with an order
        return (5, 0.0, repr(v))


def _sentinel_word(s: "_Sentinel", *, ascii_mode: bool, words: bool = False) -> str:
    """A sentinel as the grammar spells it: `None` for absence, the class
    as `missing` (`∅` in unicode, unless `words` asks for the word, as a
    language domain does), a member as its own word."""
    if s.kind == "absent":
        return "None"
    if s.member is None:
        return "missing" if (ascii_mode or words) else "∅"
    return s.member


def _ordered_sentinels(absent: bool, holes) -> list:
    """Admitted sentinels in the fixed rendering order: absence, the
    class, then members alphabetically."""
    return ([ABSENT] if absent else []) + sorted(
        set(holes), key=lambda h: (h.member is not None, h.member or ""))


def _render_set_member(v, *, ascii_mode: bool, words: bool = False) -> str:
    """One discrete-set member in the spelling the input grammar reads
    back: a sentinel as its word (the class as `∅` in unicode), a string
    always double-quoted, everything else as its own literal.
    `_set_value` accepts either quote style on the way in and keeps
    neither, so one spelling comes back out.

    A member whose own text contains a double quote is outside what a
    set binding can express: rendered inside double quotes, such a value
    cannot be read back."""
    if isinstance(v, _Sentinel):
        return _sentinel_word(v, ascii_mode=ascii_mode, words=words)
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)


def _render_piece(piece, *, ascii_mode: bool, as_int: bool = False) -> str:
    if isinstance(piece, LanguageRef):
        return repr(piece)
    if isinstance(piece, str):
        return piece if ascii_mode else _TYPE_GLYPH.get(piece, piece)
    if isinstance(piece, frozenset):
        vals = ", ".join(_render_set_member(v, ascii_mode=ascii_mode)
                         for v in sorted(piece, key=_member_sort_key))
        return "{" + vals + "}"
    lo, hi = piece[0], piece[1]
    if isinstance(lo, complex) or isinstance(hi, complex):
        return f"[{_render_complex(complex(lo))}, {_render_complex(complex(hi))}]"
    if as_int:
        lo, hi = _as_int_if_whole(lo), _as_int_if_whole(hi)
    return repr(Interval(lo, hi, closed_lo=getattr(piece, "closed_lo", True),
                         closed_hi=getattr(piece, "closed_hi", True)))


def _render_complex(z: complex) -> str:
    """A complex value in the claim grammar's own coordinate spelling
    (`-1-1j`), which parses back, never Python's parenthesized repr."""
    return f"{z.real:g}{z.imag:+g}j"


def _render_dims(dims: tuple, ascii_mode: bool) -> str:
    """A space exponent for `dims`: `^n`/`^(m,n)` in ascii. In unicode,
    the superscript (`ⁿ`/`ᵐˣⁿ`) when every dimension has a superscript
    form and none contains the letter `x` (spelled like the separator
    `ˣ`), else the same plain `^n`/`^(m,n)` exponent, so the display
    always reads back as the same space."""
    if not dims:
        return ""
    plain = f"^{dims[0]}" if len(dims) == 1 else "^(" + ",".join(dims) + ")"
    if ascii_mode or any("x" in d for d in dims):
        return plain
    sup = _to_superscript("×".join(dims))
    return sup if sup is not None else plain


def render_domain(bound, *, show_missing: bool = True, ascii_mode: bool | None = None,
                  always_show_type: bool = True) -> str:
    """A domain -> the canonical set-notation text a person would type
    for it, always in the same glyph vocabulary the input grammar
    itself accepts, never a natural-language paraphrase of it. Input
    stays terse, but a rendered domain never leaves a real default
    unstated: a bounded interval always states its resolved type (`R`
    by default, same as any explicit `Z`/`N`), and a domain with no
    real restriction collapses to the bare type (`R`/`ℝ`).
    `always_show_type=False` is the terse-when-unstated spelling of
    `render_domain_bound()`'s hand-editable surface.

    The missing-value policy renders what the domain admits and never
    what it excludes: the absence of the object as `None`, the hole
    class as `missing` (`∅` in unicode), a member as its own word, in
    the order `None`, `missing`, members alphabetically. ASCII fuses
    them onto the type clause (`[0.0, 1.0] : float|None|missing`, a bare
    `R|missing`); unicode writes a union after it (`[0.0, 1.0] ⊂ ℝ ∪
    {None, ∅}`). A domain that does not state its policy renders the
    default of a parameter with no annotation (absence and the class);
    `complete()` resolves it from the annotation first. An enumerated
    set lists its sentinels inside the braces (`{0.25, None}`,
    `{missing}`). A vector or matrix space puts an admitted hole in
    its element clause, in brackets before the power
    (`([0.0, 1.0] | {missing})^n : float`, `(ℝ ∪ {∅})ⁿˣⁿ`), and the
    absence of the whole value after the type (`... : float|None`). A
    language domain spells the words in both modes, since `∅` is the
    empty language to a reader of formal languages. `show_missing=False`
    leaves the policy unstated (a hand-editable bound).

    `ascii_mode` renders `R`/`Z`/`N` plain rather than as `ℝ`/`ℤ`/`ℕ`
    and prefers a Python-style annotation for the type clause (`[1,
    100] : float`, `[1, 100] : int`; `N` keeps the worded `subset N`).
    Left unstated it follows the global `get_unicode_output()`
    preference. A `Z`/`N`-typed bound's whole endpoints render without
    a `.0`."""
    if ascii_mode is None:
        ascii_mode = not get_unicode_output()
    dom = _as_domain(bound)
    as_int = dom.base_type in ("Z", "N")
    union_op = " | " if ascii_mode else " ∪ "
    num_excl = numeric_excluded(dom)
    language = dom.base_type == "L"

    def excluded_text() -> str:
        if not num_excl:
            return ""
        return " \\ " + _render_piece(frozenset(num_excl),
                                        ascii_mode=ascii_mode or language,
                                        as_int=as_int)

    if _is_enumerated(dom) and not dom.dims:
        values = sorted({v for p in dom.pieces for v in p}, key=_member_sort_key)
        text = "{" + ", ".join(_render_set_member(v, ascii_mode=ascii_mode,
                                                  words=language)
                               for v in values) + "}"
        text += excluded_text()
        if dom.explicit_type and not language:
            text += _type_annotation_suffix(dom.base_type, ascii_mode)
        return text
    absent, holes = admitted(dom)
    if not show_missing:
        absent, holes = False, ()
    ordered = _ordered_sentinels(absent, holes)
    value_pieces = [p for p in dom.pieces if not _sentinel_piece(p)]
    if language:
        text = union_op.join(_render_piece(p, ascii_mode=ascii_mode)
                             for p in value_pieces)
        text += excluded_text()
        text += "".join("|" + _sentinel_word(s, ascii_mode=True) for s in ordered)
        return text
    fully_unbounded = (
        len(value_pieces) == 1 and not num_excl
        and isinstance(value_pieces[0], tuple)
        and value_pieces[0][0] == float("-inf") and value_pieces[0][1] == float("inf"))
    bare = not value_pieces or fully_unbounded
    type_name = dom.base_type if ascii_mode else _TYPE_GLYPH.get(dom.base_type, dom.base_type)
    if bare:
        body = type_name
    else:
        body = union_op.join(_render_piece(p, ascii_mode=ascii_mode, as_int=as_int)
                             for p in value_pieces)
    show_type = not bare and (always_show_type or dom.base_type != "R")
    if dom.dims:
        # the element clause carries the holes of a slot, the tail the
        # absence of the whole value
        hole_words = [_sentinel_word(h, ascii_mode=ascii_mode)
                      for h in ordered if h.kind == "missing"]
        if hole_words:
            body = f"({body}{union_op}{{{', '.join(hole_words)}}})"
        text = body + _render_dims(dom.dims, ascii_mode) + excluded_text()
        tail = [s for s in ordered if s.kind == "absent"]
    else:
        text = body + excluded_text()
        tail = ordered
    if show_type:
        text += _type_annotation_suffix(dom.base_type, ascii_mode)
    if tail:
        if ascii_mode:
            text += "".join("|" + _sentinel_word(s, ascii_mode=True) for s in tail)
        else:
            text += " ∪ {" + ", ".join(_sentinel_word(s, ascii_mode=False)
                                       for s in tail) + "}"
    return text


# every bounded domain's own resolved type is always stated in rendered
# output (never left implicit, even for the common default "R" case),
# matching this grammar's own terse-input/explicit-output split: input
# never has to say "float"/"subset R" to mean an ordinary real interval,
# but a rendered claim always does. ASCII prefers a Python-style type
# annotation after a spaced colon (`[1, 100] : float`/`[1, 100] : int`)
# over the `subset`-worded clause, matching the input spelling
# `parse_binding()`'s own `_SUBSET_ANYWHERE` accepts for it; `N` has no
# matching Python type name, so it keeps the worded `subset N` clause in
# ascii too.
_ASCII_TYPE_ANNOTATION = {"R": " : float", "Z": " : int", "C": " : complex"}


def _type_annotation_suffix(base_type: str, ascii_mode: bool) -> str:
    if ascii_mode:
        return _ASCII_TYPE_ANNOTATION.get(base_type, f" subset {base_type}")
    return f" ⊂ {_TYPE_GLYPH.get(base_type, base_type)}"


#: the stand-in an older record wrote for the hole class in a stored
#: `excluded`/`set` list, read back as `missing`
_MISSING_JSON_TOKEN = "__mathema_missing__"


def _json_value(v):
    """A set member or excluded value as stored: a sentinel as
    `{"sentinel": <word>}`, anything else as itself."""
    if isinstance(v, _Sentinel):
        return {"sentinel": v.word}
    return v


def _value_from_json(v):
    """The inverse of `_json_value`: `{"sentinel": <word>}` back to its
    sentinel, a stored `null` as absence, and the older
    `__mathema_missing__` as the hole class."""
    if isinstance(v, dict) and "sentinel" in v:
        return _sentinel_of(str(v["sentinel"])) or member(str(v["sentinel"]))
    if v is None:
        return ABSENT
    if v == _MISSING_JSON_TOKEN:
        return MISSING
    return v


def _json_sort_key(v) -> str:
    return f"~{v['sentinel']}" if isinstance(v, dict) else str(v)


def domain_bound_to_json(b) -> str | dict:
    """One domain bound (an `Interval`/bare `(lo, hi)` tuple, `"Z"`/`"N"`,
    a `frozenset`, or a `Domain`, `split_quantifier()`'s own
    vocabulary) -> a JSON/YAML-safe value. `"Z"`/`"N"` pass through
    unchanged. A tuple -> a self-describing `{"lo", "hi", "closed_lo",
    "closed_hi"}` dict, not a positional `[lo, hi]` list, readable in
    a hand-edited `claims.yaml`, and unambiguous against the legacy
    `[lo, hi]` list shape by type alone (a list means "an old file,
    always closed"; resolving that is `domain_bound_from_json`'s job).
    A `frozenset` -> `{"set": [sorted members]}`, so a discrete-value
    domain is never confused with an interval the way a bare
    `list(frozenset(...))` used to be. A `Domain` -> `{"base_type",
    "pieces", "excluded", "explicit_type"}` plus `"dims"` for a vector or
    matrix space (`R^(n*n)`), each piece/excluded-member
    recursively encoded the same way (with `MISSING` itself standing in
    as one fixed, JSON-safe token)."""
    if isinstance(b, Domain):
        out = {"base_type": b.base_type,
               "pieces": [domain_bound_to_json(p) for p in b.pieces],
               "excluded": sorted((_json_value(v) for v in b.excluded),
                                  key=_json_sort_key),
               "explicit_type": b.explicit_type}
        if b.dims:
            out["dims"] = list(b.dims)
        if b.absent:
            out["absent"] = True
        if b.members:
            out["members"] = list(b.members)
        return out
    if isinstance(b, LanguageRef):
        return {"language": b.name,
                **{key: domain_bound_to_json(interval) for key, interval in b.refinements}}
    if isinstance(b, str):
        return b
    if isinstance(b, frozenset):
        return {"set": [_json_value(v) for v in sorted(b, key=_member_sort_key)]}
    lo, hi = b
    return {"lo": _endpoint_to_json(lo), "hi": _endpoint_to_json(hi),
           "closed_lo": getattr(b, "closed_lo", True),
           "closed_hi": getattr(b, "closed_hi", True)}


def _endpoint_to_json(v):
    """Intent:
        One interval endpoint as a JSON/YAML-safe value: numbers pass
        through; a complex corner becomes its coordinate spelling
        ("1+2j"), the same string `_endpoint_from_json` reads back."""
    if isinstance(v, complex) and not isinstance(v, (int, float)):
        return _render_complex(v)
    return v


def domain_bound_from_json(v):
    """The inverse of `domain_bound_to_json`, tolerates the new dict
    shapes (including `Domain`'s own), the legacy plain `[lo, hi]` list
    (every domain bound ever written by mathema before this function
    existed, always an implicitly closed interval): a stored file on
    disk keeps loading exactly as it always has, forever, no migration
    step required."""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return Interval(_endpoint_from_json(v[0]), _endpoint_from_json(v[1]))
    if "language" in v:
        return LanguageRef(str(v["language"]), tuple(sorted(
            (key, domain_bound_from_json(interval))
            for key, interval in v.items() if key != "language")))
    if "base_type" in v:
        return Domain(base_type=v["base_type"],
                      pieces=tuple(domain_bound_from_json(p) for p in v["pieces"]),
                      excluded=frozenset(_value_from_json(x) for x in v["excluded"]),
                      explicit_type=v.get("explicit_type", False),
                      dims=tuple(str(d) for d in v.get("dims", ())),
                      absent=bool(v.get("absent", False)),
                      members=tuple(str(m) for m in v.get("members", ())))
    if "set" in v:
        return frozenset(_value_from_json(x) for x in v["set"])
    return Interval(_endpoint_from_json(v["lo"]), _endpoint_from_json(v["hi"]),
                    closed_lo=v.get("closed_lo", True), closed_hi=v.get("closed_hi", True))


def _endpoint_from_json(v):
    """Intent:
        One stored interval endpoint back to a number: the float every
        endpoint has always been, or a complex corner stored as its
        coordinate spelling ("1+2j")."""
    if isinstance(v, str) and ("j" in v or "J" in v):
        return complex(v)
    return float(v)


def render_domain_bound(b) -> str:
    """One domain bound -> the text a person would type for it, an
    alias for `render_domain()` with its missing-value clause left off
    (a hand-editable bound, such as a spec's `let x be [0, 1]` line or
    a diagnostic's `declared:` bound, states nothing about missing
    values), its type
    names spelled plain (`Z`, not `ℤ`), and its resolved type left
    unstated for the common, unrefined case (`[0, 1]`, not
    `[0, 1]:float`), a hand-editable surface, typeable without
    reaching for a Unicode glyph or a type annotation neither was ever
    required before."""
    return render_domain(b, show_missing=False, ascii_mode=True, always_show_type=False)


def _parse_piece(text: str, *, in_element: bool = False):
    """One union-piece's text (an interval, either spelling; a discrete
    set; a bare named set; or a bare sentinel word) -> `Interval` |
    `frozenset` | `"R"`/`"Z"`/`"N"` | `None` when it's none of those. No
    "name in" prefix here, a piece after the first `|`/`∪` in a
    binding never repeats it. A bare sentinel word (`None`, `missing`,
    `nan`, ...) is shorthand for the singleton set the braced spelling
    produces, so `[0, 100] | missing` means `[0, 100] | {missing}`.
    Inside an element clause (`in_element`) a `None` is the `null`
    hole."""
    text = text.strip()
    sentinel = _sentinel_of(text, in_element=in_element)
    if sentinel is not None:
        return frozenset({sentinel})
    m = _PIECE_RANGE.match(text) or _PIECE_INTERVAL.match(text)
    if m is not None:
        try:
            lo, hi = _bound(m.group(2)), _bound(m.group(3))
        except ValueError:
            return None
        return Interval(lo, hi, closed_lo=m.group(1) == "[", closed_hi=m.group(4) == "]")
    m = _PIECE_SET.match(text)
    if m is not None:
        try:
            return frozenset(_set_value(v, in_element=in_element)
                             for v in _split_commas(m.group(1)) if v.strip())
        except ValueError:
            return None
    m = _PIECE_LANGUAGE.match(text)
    if m is not None:
        refine = m.group("refine")
        return LanguageRef(m.group("name"),
                           _parse_refinements(refine, text) if refine else ())
    m = _PIECE_NAMED.match(text)
    if m is not None:
        return _SUBSET_ASCII.get(m.group(1), m.group(1))
    return None


def _interval_problem(piece) -> str | None:
    """Intent:
        Why an interval piece cannot be read as a set of reals, or None:
        an endpoint that is not a number (NaN) orders against nothing.

    Notes:
        An empty interval (`[2, 1]`, `(1, 1]`) is readable and is
        refused at adjudication as `skipped:misspecified`, so one such
        claim does not stop the rest of a claims file from loading.
    """
    if not isinstance(piece, Interval):
        return None
    lo, hi = piece
    if not all(isinstance(v, (int, float)) for v in (lo, hi)):
        return None
    if lo != lo or hi != hi:
        return "has an endpoint that is not a number"
    return None


def _merge_exclude_keyword_parts(parts: list[str]) -> list[str]:
    """`exclude={...}` as its own top-level comma-part (the keyword
    form, `x in [0,10], exclude={-1}`) refers to whichever binding
    immediately precedes it in the same quantifier, splice it onto
    that part's own text (as the same trailing `\\{...}` syntax the
    inline form already produces) and drop the standalone part, before
    any per-part parsing runs. A standalone `exclude={...}` with
    nothing preceding it in this list is left alone, `parse_binding()`
    rejects it on its own, same as any other unrecognized binding."""
    out: list[str] = []
    for part in parts:
        m = _STANDALONE_EXCLUDE.match(part)
        if m is not None and out:
            out[-1] = f"{out[-1]} \\ {{{m.group('set')}}}"
            continue
        out.append(part)
    return out


def parse_binding(part: str):
    """One comma-separated quantifier binding -> `(name, domain_value)`,
    or `None` when `part` isn't a recognized binding at all (including
    the sampling-intensity modifier, `split_quantifier()`'s own concern,
    not this function's). Handles every shape this module accepts in
    one place: membership (`in`/`∈`/`\\in`/`\\elem`), one or more pieces
    joined by `|`/`∪` (an interval either spelling, a discrete set, or a
    bare named set), an optional trailing exclusion (`\\{...}`, or the
    keyword form already spliced in by `_merge_exclude_keyword_parts`),
    and an optional `⊂`/`\\sub`/`\\subset` type refinement found anywhere
    in the text (not anchored to the end, so a missing-value override
    reads naturally on either side of it).

    Returns a bare `Interval`/`"Z"`/`"N"`/`frozenset` when nothing but a
    plain binding was stated, `x in [0, 1]` behaves exactly like the
    tuple/string forms every existing caller already treats one as. A
    `Domain` comes back once exclusion, union, or an explicit type
    refinement is genuinely present, including a *bare* `x in Z`/`x in
    N`/`x in R`, stating a type at all, even the bare named-set
    spelling, is a deliberate, precise choice.

    Missing (`MISSING`/`∅`) is included by default regardless of
    whether a type was stated, `x in [0, 1]` and `x in [0, 1] subset
    Z` both permit it, only an explicit `\\{∅}`/`\\{missing}`
    exclusion clause in the binding's own text ever excludes it. This
    is the wider, unverified-safe default: a claim's own domain text
    stating a type doesn't make the real function actually reject a
    missing value, so it isn't treated as though it does."""
    result = _parse_binding(part)
    return None if isinstance(result, str) else result


def _sentinel_word_pattern() -> str:
    words = sorted(sentinel_tokens(), key=len, reverse=True)
    return "(?:" + "|".join(re.escape(w) for w in words) + ")"


def _peel_trailing_sentinels(text: str) -> tuple:
    """Intent:
        `(text, words)`: `text` with every trailing sentinel clause
        peeled off its end, and the words those clauses spelled, in
        order. A clause is the ascii fused spelling (`|None`,
        `|missing`, one word each) or a braced union (`| {nan}`,
        `∪ {None, ∅}`) whose members are all sentinel words. A braced
        set holding anything else is a piece of the domain, not a
        clause, and stays.
    """
    word = _sentinel_word_pattern()
    fused = re.compile(rf"\s*\|\s*({word})\s*$")
    braced = re.compile(
        rf"\s*(?:\||∪)\s*\{{\s*({word}(?:\s*,\s*{word})*)\s*\}}\s*$")
    words: list = []
    while True:
        m = braced.search(text) or fused.search(text)
        if m is None:
            return text, words
        head = text[:m.start()].rstrip()
        if not head or _MEMBERSHIP_PREFIX.match(head + " ") and \
                not _MEMBERSHIP_PREFIX.sub("", head + " ").strip():
            return text, words
        words = [w.strip() for w in m.group(1).split(",")] + words
        text = head


def _top_level_union(text: str) -> bool:
    """Whether `text` holds a union operator outside every bracket."""
    depth = 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and ch in "|∪":
            return True
    return False


def _element_clause(base: str) -> "str | None":
    """The inside of a bracketed element clause, `([0, 1] | {missing})`
    before a power, or None when `base` is not one (an open interval
    `(0, 1)` holds no union and is a piece)."""
    b = base.strip()
    if not (b.startswith("(") and b.endswith(")")):
        return None
    depth = 0
    for i, ch in enumerate(b):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0 and i != len(b) - 1:
                return None
    inner = b[1:-1].strip()
    return inner if _top_level_union(inner) else None


def _parse_binding(part: str):
    """Intent:
        The one implementation behind `parse_binding()`: `(name, value)`
        on success, or a specific human-readable failure reason (a
        `str`) naming the first stage that didn't check out, so
        `split_quantifier()` can raise `InvalidDomain` with a clear,
        actionable message from the very parse that failed.

    Notes:
        Sentinels are ordinary union pieces. A trailing sentinel clause
        (`: float|None|missing`, `⊂ ℝ ∪ {None, ∅}`, the older `| {∅}`)
        is peeled first, then the type clause, then an exclusion, and
        what is left is the set expression. At the top level `None` is
        the absence of the object; the holes a vector's slots may hold
        sit in the bracketed element clause before the power
        (`([0, 1] | {missing})^n`), where a `None` is the `null` hole,
        and a trailing hole word on a space (the older `[0, 1]^n |
        {missing}`) is read as that clause. An enumerated set is
        exactly its members, sentinels included.
    """
    text = _desuperscript(part.strip())
    if ":=" in text:
        return (f"{part!r}: `:=` states a definition (a `defines:` row), "
                f"which a binding never holds; state the type after a "
                f"colon, `x in [0, 1] : float`")
    type_explicit = None
    text, tail_words = _peel_trailing_sentinels(text)

    m = _SUBSET_ANYWHERE.search(text)
    if m is not None:
        type_explicit = _SUBSET_ASCII.get(m.group("type"), m.group("type"))
        text = (text[:m.start()] + " " + text[m.end():]).strip()
    # a type clause can sit between the set expression and a sentinel
    # clause, so look again once it is gone
    text, more = _peel_trailing_sentinels(text)
    tail_words = more + tail_words

    excluded_text = None
    m = _EXCLUDE_SUFFIX.search(text)
    if m is not None:
        excluded_text = m.group("set")
        text = text[:m.start()].rstrip()
        text, more = _peel_trailing_sentinels(text)
        tail_words = more + tail_words

    m = _MEMBERSHIP_PREFIX.match(text)
    if m is None:
        return (f"{part!r}: no recognized membership operator "
                f"(in / ∈ / \\in / \\elem), expected 'name in domain'")
    name = m.group("name")
    rest = text[m.end():].strip()
    if not rest:
        return f"{part!r}: {name!r} has no domain after the membership operator"
    # a VECTOR/MATRIX space power binds the whole element domain:
    # `[0,1]^n`, `R^(m*n)`, or the unicode superscript forms. The caret
    # is the one at bracket depth zero, so an endpoint like `10^6`
    # inside the interval is never mistaken for it.
    space_dims: tuple = ()
    in_element = False
    split = _split_top_caret(rest)
    if split is not None:
        parsed_dims = _parse_dims(split[1])
        if parsed_dims is not None:
            rest, space_dims = split[0], parsed_dims
            inner = _element_clause(rest)
            if inner is not None:
                rest, in_element = inner, True
    pieces = []
    for pt in _UNION_SPLIT.split(rest):
        piece = _parse_piece(pt, in_element=in_element) if pt else None
        if piece is None:
            return (f"{part!r}: {pt!r} isn't a recognized interval, discrete "
                    f"set, or named set (R/Z/N) for {name!r}")
        problem = _interval_problem(piece)
        if problem is not None:
            return f"{part!r}: {pt.strip()!r} {problem} for {name!r}"
        pieces.append(piece)

    # the sentinels among the pieces, apart from the values
    sentinels: list = []
    value_pieces: list = []
    for piece in pieces:
        if isinstance(piece, frozenset):
            found = [v for v in piece if isinstance(v, _Sentinel)]
            values = frozenset(v for v in piece if not isinstance(v, _Sentinel))
            sentinels.extend(found)
            if values or not found:
                value_pieces.append(values)
        else:
            value_pieces.append(piece)
    for word in tail_words:
        sentinel = _sentinel_of(word)
        if space_dims and sentinel is not None and sentinel.kind == "missing":
            # a hole word after a space is about its slots
            sentinels.append(sentinel)
        elif sentinel is not None:
            sentinels.append(sentinel)

    # a single bare named-set piece ("x in Z", "x in R") sets the base
    # type directly, the same as an explicit ⊂ clause would; it isn't
    # really a "piece" (there's no interval/discrete-set to union
    # alongside), and stating it at all is just as deliberate a type
    # choice as ⊂ Z.
    if len(value_pieces) == 1 and isinstance(value_pieces[0], str):
        bare_type = value_pieces[0]
        if type_explicit is not None and type_explicit != bare_type:
            return (f"{part!r}: states two different types ({bare_type} and "
                    f"⊂ {type_explicit}) for {name!r}")
        type_explicit = bare_type
        value_pieces = []
        named_only = True
    else:
        named_only = False

    # a language piece (`L[ascii]`) makes the whole binding a language
    # domain: no numeric type clause, no dimension power (a length
    # bound sits inside the piece, `L[ascii, len <= 80]`), and no interval or named set
    # beside it in the union; a finite set of literal members is fine
    if any(isinstance(p, LanguageRef) for p in value_pieces):
        if type_explicit is not None:
            return (f"{part!r}: a language domain (L[...]) carries no "
                    f"numeric type, so the stated type {type_explicit} "
                    f"contradicts it for {name!r}")
        if space_dims:
            return (f"{part!r}: a language domain has no dimension power; "
                    f"bound a length inside the brackets, "
                    f"'L[ascii, len <= 80]', for {name!r}")
        if any(not isinstance(p, (LanguageRef, frozenset)) for p in value_pieces):
            return (f"{part!r}: a language domain can be unioned with a "
                    f"finite set of members, not with an interval or a "
                    f"named number set, for {name!r}")
        type_explicit = "L"

    excluded = set()
    if excluded_text is not None:
        try:
            for v in _split_commas(excluded_text):
                if v.strip():
                    excluded.add(_set_value(v))
        except ValueError:
            return (f"{part!r}: an excluded value in {{{excluded_text}}} isn't "
                    f"a recognized number, string, boolean, or sentinel")
    if MISSING in sentinels and any(
            isinstance(v, _Sentinel) and v.kind == "missing" and v.member
            for v in excluded):
        return (f"{part!r}: `missing` admits every member of the class, so "
                f"one cannot be excluded from it; name the members you "
                f"admit, `|nan` or `| {{null, nan}}`, for {name!r}")

    def _complex_cornered(piece):
        return (isinstance(piece, tuple) and not isinstance(piece, frozenset)
                and any(isinstance(v, complex) for v in piece))

    if any(_complex_cornered(p) for p in value_pieces):
        # complex corner literals name a rectangle of the plane: the
        # type is C whether or not the binding spelled it, and a stated
        # real type contradicts the corners outright.
        if type_explicit not in (None, "C"):
            return (f"{part!r}: complex interval corners contradict the "
                    f"stated type {type_explicit}")
        type_explicit = "C"

    base_type = type_explicit or "R"
    unique: list = []
    for sentinel in sentinels:
        if sentinel not in unique:
            unique.append(sentinel)

    # an enumerated domain is exactly its members: the values it lists
    # and the sentinels it lists, one set
    enumerated = type_explicit != "L" and not space_dims and not named_only and (
        all(isinstance(p, frozenset) for p in value_pieces)
        and (bool(value_pieces) or bool(unique)))
    if enumerated:
        members = frozenset().union(*value_pieces, unique)
        if all(isinstance(v, _Sentinel) for v in members):
            # a set of sentinels alone lists no value of any type
            type_explicit = None
        if type_explicit is None and not excluded:
            return name, members
        return name, Domain(base_type=base_type, pieces=(members,),
                            excluded=frozenset(excluded),
                            explicit_type=type_explicit is not None)

    absent = ABSENT in unique
    holes = [s for s in unique if s.kind == "missing"]
    # collapse to the OLD raw shape only when nothing but a plain piece
    # was stated: a stated type, an exclusion, a sentinel or a space
    # power needs the Domain shape to carry it
    if (type_explicit is None and not excluded and len(value_pieces) == 1
            and not space_dims and not unique):
        return name, value_pieces[0]
    all_pieces = tuple(value_pieces) + ((frozenset(holes),) if holes else ())
    return name, Domain(base_type=base_type, pieces=all_pieces,
                        excluded=frozenset(excluded),
                        explicit_type=type_explicit is not None,
                        dims=space_dims, absent=absent)


_NE_EXCLUSION = re.compile(r"^\s*([A-Za-z_]\w*)\s*!=\s*([^,]+?)\s*$")


def _exclude_point(bound, value: float):
    """`bound` with one point excluded, the same set the explicit
    `\\ {value}` spelling produces, built here for the `name != value`
    domain sugar."""
    if isinstance(bound, Domain):
        return Domain(base_type=bound.base_type, pieces=bound.pieces,
                      excluded=bound.excluded | {value},
                      explicit_type=bound.explicit_type)
    if isinstance(bound, tuple) and not isinstance(bound, frozenset):
        return Domain(base_type="R", pieces=(bound,),
                      excluded=frozenset({value}), explicit_type=False)
    if isinstance(bound, frozenset):
        return frozenset(v for v in bound if v != value)
    if isinstance(bound, str):
        return Domain(base_type=bound, pieces=(),
                      excluded=frozenset({value}), explicit_type=True)
    return bound


def split_quantifier(text: str) -> tuple[dict, str]:
    """Peel a leading quantifier off a normalized law, lifting it into
    domain structure: `for x in [0, ..., 1], y in [-1, ..., 1], f(x, y) <= 1`
    (typed as `x ∈ [0,1]` if preferred; `in`/`∈`/`\\in`/`\\elem` are all
    the same membership operator) returns
    ({"x": Interval(0.0, 1.0), "y": Interval(-1.0, 1.0)}, "f(x, y) <= 1").

    A binding's domain value is one of the original three shapes,
    `Interval` (an ordinary `(lo, hi)` tuple, plus `.closed_lo`/
    `.closed_hi` for the exact boundary), a bare `"Z"`/`"N"`, or a
    `frozenset` of explicit values (`x in {0, 1}`), unless it actually
    uses exclusion (`\\{...}`/`exclude={...}`), union (`|`/`∪`), or an
    explicit type refinement (`⊂`/`\\sub`/`\\subset R/Z/N`, or now the
    bare `Z`/`N`/`R` spelling too), in which case it's a `Domain`
    instead, see `parse_binding()` for the full grammar and
    `domain_contains()` for how either shape is checked against a real
    value. `n=500` in the same binding list is a sampling-intensity
    modifier, not a per-parameter bound at all, lifted into
    `domain["n"]` as a plain int. Known sharp edge: a function with an
    actual parameter literally named `n` collides with this reserved
    key if both are used in the same claim.

    The quantifier is not statement syntax, per claim-anatomy.md it
    nests inside the claim's domain, so this desugars it there and the
    statement stays a bare relation. Bindings and the statement are all
    top-level comma-separated segments after `for `, distinguished by
    shape (a binding always parses as one via `parse_binding()`, the
    exclude-keyword form, or the `n=...` intensity modifier; the
    statement doesn't) rather than a separate delimiter, a comma
    inside `[...]`/`{...}`/`(...)` is never top-level, so `f(x, y)`'s
    own comma and `[0, 1]`'s own comma are never mistaken for the
    binding/statement boundary. No leading `for ` at all returns
    `({}, text)` unchanged, legitimately no domain here (a
    `raises(...)`-only claim, say). Once text *does* start that way,
    though, the first segment failing to parse as a binding raises
    `InvalidDomain` with a specific reason, rather than silently
    discarding the whole quantifier and letting a mis-typed domain go
    unnoticed, same for a quantifier with no statement segment left
    at all (`for x in [0, 1]` with nothing after it)."""
    m = _FOR_PREFIX.match(text)
    if m is None:
        return {}, text
    segments = _split_commas(text[m.end():])

    def ne_exclusion(seg: str):
        # `di != 2` between bindings: a measure-zero point exclusion on
        # di's own bound, the same set `di in [...] \ {2}` states,
        # sugar, folded into the binding rather than refused as a
        # second relation
        m2 = _NE_EXCLUSION.match(seg)
        if m2 is None:
            return None
        value = _const_fold(m2.group(2)) if not _is_number(m2.group(2)) \
            else float(m2.group(2))
        if value is None:
            return None
        return m2.group(1), value

    def _is_number(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    def is_binding(seg: str) -> bool:
        return (_BINDING_INTENSITY.match(seg) is not None
               or _STANDALONE_EXCLUDE.match(seg) is not None
               or ne_exclusion(seg) is not None
               or parse_binding(seg) is not None)

    n_bindings = 0
    for seg in segments:
        if not is_binding(seg):
            bad = _PATH_LIKE_BINDING.match(seg)
            if bad is not None and not re.fullmatch(_PATH, bad.group("path")):
                raise InvalidDomain(
                    f"{seg.strip()!r}: {bad.group('path')!r} is not a path; a "
                    f"path is fields and indices, `o.address.zip`, "
                    f"`o.lines[0].sku`, `o.lines[*].qty`")
            break
        n_bindings += 1
    if n_bindings == 0:
        # the reason comes from the failing parse itself (`_parse_binding`
        # returns it directly), never a separate explainer re-walk.
        raise InvalidDomain(_parse_binding(segments[0].strip()))
    if n_bindings == len(segments):
        raise InvalidDomain(
            f"{text!r}: every segment after 'for' parses as a binding, "
            "the quantifier has no statement left to quantify")
    domain = {}
    ne_pending: list = []
    # the exclude-keyword splice rewrites binding text, so merged parts
    # are parsed fresh here rather than reusing the scan above.
    parts = _merge_exclude_keyword_parts(segments[:n_bindings])
    for part in parts:
        b = _BINDING_INTENSITY.match(part)
        if b is not None:
            domain["n"] = int(b.group(1))
            continue
        ne = ne_exclusion(part)
        if ne is not None:
            ne_pending.append(ne)
            continue
        parsed = _parse_binding(part)
        if isinstance(parsed, str):
            raise InvalidDomain(parsed)
        name, value = parsed
        if name in domain:
            raise DuplicateBinding(
                f"{name!r} is bound twice in one quantifier; give it one "
                f"domain")
        domain[name] = value
    for name, value in ne_pending:
        bound = domain.get(name)
        if bound is None:
            raise InvalidDomain(
                f"{name} != {value:g} excludes a point, but {name!r} has no "
                f"bound to exclude it from, state `{name} in [...]` "
                f"alongside it")
        domain[name] = _exclude_point(bound, value)
    return domain, ", ".join(segments[n_bindings:]).strip()

# --- the symbolic projection: one place where a declared bound becomes ------
# --- something a prover can consume ----------------------------------------
#
# sympy is imported lazily inside each function: this module stays
# import-time sympy-free (the sampler and the spec store import it
# without ever touching sympy), while the prover gets its sets,
# assumption keywords, and Q-predicates from the same domain model the
# renderer and the sampler read, never from its own re-derivation of
# what a bound shape means.


def canonical_bound(bound) -> tuple:
    """Intent:
        The tightest standard-set spelling of a resolved bound: an
        integer-typed domain whose one interval piece is the whole
        nonnegative ray (`[0, oo]:int`, the `[0, oo) subset Z` shape)
        IS the natural numbers, and collapses to `N`, same set,
        canonical name, which is what makes domains comparable across
        claims. Applied at resolve time; the declared text stays what
        the author wrote, and the caller renders the collapse
        explicitly.

    Notes:
        Returns `(canonical, declared_text | None)`: `declared_text` is
        the original bound's rendering when a collapse happened, `None`
        (with the bound unchanged) otherwise. Deliberately narrow: only
        the exact-`N` shape collapses; a bounded integer range
        (`[0, 10]:int`) is already tight, and a shifted ray
        (`[1, oo]:int`) has no standard single name. A domain carrying
        a missing-value piece keeps its shape (the missing policy is
        not part of the set algebra and must not be silently rewritten).
    """
    if not (isinstance(bound, Domain) and bound.base_type in ("Z", "N")):
        return bound, None
    value_pieces = [p for p in bound.pieces if not _sentinel_piece(p)]
    if len(value_pieces) != 1:
        return bound, None
    piece = value_pieces[0]
    if isinstance(piece, frozenset) or not isinstance(piece, tuple):
        return bound, None
    lo, hi = piece
    if not (lo == 0 and getattr(piece, "closed_lo", True)
            and hi == float("inf")):
        return bound, None
    declared = render_domain_bound(bound)
    return Domain(base_type="N",
                  pieces=tuple(p for p in bound.pieces if _sentinel_piece(p)),
                  excluded=bound.excluded, explicit_type=True,
                  absent=bound.absent, members=bound.members), declared


def missing_included(bound) -> bool:
    """Whether the declared bound admits a missing value of either kind:
    the absence of the object or a hole. A bound that does not state its
    policy admits both, the default of a parameter with no annotation;
    the prover states it in sketches, the renderer prints it, and
    neither re-detects it from the pieces."""
    absent, holes = admitted(bound)
    return absent or bool(holes)


def bound_pin(bound):
    """The single value a *degenerate* bound admits, `(True, value)`
    for `[v, v]` with both ends closed (or a `Domain` whose only piece
    is such an interval, with nothing excluded), `(False, None)`
    otherwise. The caller substitutes the value for the symbol outright
    (converting to an exact literal itself if it needs sympy exactness);
    a degenerate range that never pinned anything used to be a real,
    confusing adjudication gap."""
    if isinstance(bound, Domain):
        pieces = [p for p in bound.pieces if not _sentinel_piece(p)]
        if (len(pieces) == 1 and isinstance(pieces[0], tuple)
                and not isinstance(pieces[0], frozenset)
                and not numeric_excluded(bound)):
            return bound_pin(pieces[0])
        return (False, None)
    if (isinstance(bound, tuple) and not isinstance(bound, frozenset)
            and len(bound) == 2
            and getattr(bound, "closed_lo", True)
            and getattr(bound, "closed_hi", True)):
        try:
            if bound[0] == bound[1]:
                return (True, bound[0])
        except TypeError:
            return (False, None)
    return (False, None)


def split_bound_at(bound, cuts) -> list | None:
    """Intent:
        Partition an interval-shaped bound at the given cut values into
        sub-bounds that jointly cover it exactly: an open-ended piece
        between consecutive cuts, plus a degenerate `[c, c]` point piece
        at each cut the bound actually contains.

    Notes:
        Returns the sub-bounds in ascending order, or `None` when the
        bound isn't a single finite interval (a discrete set, a union,
        a bare type name, an unbounded end), no cut lands inside it, or
        more than three cuts do (a split that fine stops being a cheap
        marginalization). Interval pieces keep the original's `Domain`
        wrapper (base type, exclusions); a point piece is a plain
        `[c, c]` interval, since at a single value the type restriction
        adds nothing. A cut at an open endpoint, at an excluded value,
        or off the integer lattice of a Z/N-typed bound gets no point
        piece, the surrounding open intervals already exclude it from
        every sub-bound, exactly as the domain itself does.
    """
    wrapper, piece = None, bound
    if isinstance(bound, Domain):
        value_pieces = [p for p in bound.pieces if not _sentinel_piece(p)]
        if len(value_pieces) != 1 or isinstance(value_pieces[0], frozenset):
            return None
        wrapper, piece = bound, value_pieces[0]
    if (not isinstance(piece, tuple) or isinstance(piece, frozenset)
            or len(piece) != 2):
        return None
    lo, hi = piece
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (lo, hi)):
        return None
    if lo >= hi:
        return None
    closed_lo = getattr(piece, "closed_lo", True)
    closed_hi = getattr(piece, "closed_hi", True)

    def wrap(iv):
        if wrapper is None:
            return iv
        return Domain(base_type=wrapper.base_type, pieces=(iv,),
                      excluded=wrapper.excluded,
                      explicit_type=wrapper.explicit_type)

    def point_admitted(c):
        if wrapper is None:
            return True
        if c in wrapper.excluded:
            return False
        if wrapper.base_type in ("Z", "N") and c != int(c):
            return False
        if wrapper.base_type == "N" and c < 0:
            return False
        return True

    inside = sorted({float(c) for c in cuts
                     if lo <= c <= hi
                     and not (c == lo and not closed_lo)
                     and not (c == hi and not closed_hi)})
    if not inside or len(inside) > 3:
        return None
    pieces = []
    start, start_closed = lo, closed_lo
    for c in inside:
        if start < c:
            pieces.append(wrap(Interval(start, c, start_closed, False)))
        if point_admitted(c):
            pieces.append(Interval(c, c))
        start, start_closed = c, False
    if start < hi:
        pieces.append(wrap(Interval(start, hi, start_closed, closed_hi)))
    return pieces if len(pieces) >= 2 else None


def bound_assumptions(bound) -> dict | None:
    """The sympy `Symbol(name, **kwargs)` assumption keywords a declared
    bound soundly entails, `{"real": True}` plus `integer`/sign facts
    where the bound proves them, or `None` when nothing beyond the
    default real symbol is warranted (an unrecognized shape, a discrete
    set, a range or union that straddles zero). Symbol-level keywords
    are a fixed vocabulary with nothing for an upper bound; that side is
    `bound_context()`'s job instead. A degenerate bound should be pinned
    via `bound_pin()` first; this function doesn't special-case it."""
    if bound == "Z":
        return {"integer": True, "real": True}
    if bound == "N":
        return {"integer": True, "nonnegative": True, "real": True}
    if bound == "C":
        return {"complex": True}
    if isinstance(bound, str):
        # "Z"/"N" matched above; a bare "R" states only the default.
        _require_known_base_type(bound)
        return None
    if isinstance(bound, LanguageRef):
        return None
    if isinstance(bound, Domain):
        _require_known_base_type(bound.base_type)
        if bound.base_type == "L":
            # a string or structured value has no symbol-level reading
            return None
        if bound.base_type == "C":
            # a complex symbol, never real; interval sign facts have no
            # complex reading, so the type is the whole statement.
            return {"complex": True}
        is_int = bound.base_type in ("Z", "N")
        # MISSING never enters the sympy reading: a {∅} piece is the
        # missing-value policy (travels via missing_included()), not a
        # set-algebra member, so it must not demote a plain interval to
        # the assumption-free union branch below
        pieces = tuple(p for p in bound.pieces
                       if not (isinstance(p, frozenset)
                               and all(isinstance(v, _Sentinel) for v in p)))
        if len(pieces) == 1 and isinstance(pieces[0], tuple) \
                and not isinstance(pieces[0], frozenset):
            kwargs = _interval_sign_kwargs(pieces[0])
            if kwargs is None and not is_int:
                return None
            kwargs = dict(kwargs or {"real": True})
            if is_int:
                kwargs["integer"] = True
            return kwargs
        if not pieces and is_int:
            kwargs = {"integer": True, "real": True}
            if bound.base_type == "N":
                kwargs["nonnegative"] = True
            return kwargs
        # a genuine union of pieces, a discrete set, or a bare explicit
        # R: the pieces can straddle zero, so nothing sound to assume at
        # symbol level; bound_context() carries whatever is decidable.
        return None
    if isinstance(bound, tuple) and not isinstance(bound, frozenset) and len(bound) == 2:
        return _interval_sign_kwargs(bound)
    return None


def _interval_sign_kwargs(piece) -> dict | None:
    """`{"real": True}` plus the one sign keyword an interval piece
    proves (`positive`/`nonnegative`/`negative`/`nonpositive`), or
    `None` for a piece that straddles zero. Open endpoints sharpen the
    fact: `(0, hi]` is positive, `[0, hi]` only nonnegative."""
    lo, hi = piece
    closed_lo = getattr(piece, "closed_lo", True)
    closed_hi = getattr(piece, "closed_hi", True)
    if lo > 0 or (lo == 0 and not closed_lo):
        return {"real": True, "positive": True}
    if lo >= 0:
        return {"real": True, "nonnegative": True}
    if hi < 0 or (hi == 0 and not closed_hi):
        return {"real": True, "negative": True}
    if hi <= 0:
        return {"real": True, "nonpositive": True}
    return None


def bound_context(sym, bound):
    """The relational-predicate half of the projection: everything the
    declared bound states that no fixed symbol-assumption keyword can
    carry, as a sympy `And`/`Or` of `Q.ge`/`Q.gt`/`Q.le`/`Q.lt`
    (interval bounds, open ends strict), `Eq` (discrete-set
    membership), and `Q.ne` (excluded values) facts over `sym`, for
    use inside `sympy.assuming()`/`refine()`. `None` when the bound
    states nothing this vocabulary can express. `MISSING` never becomes
    a fact here: a real symbol can't equal a missing value, so the
    missing policy travels via `missing_included()`, not the algebra."""
    import sympy

    def interval_predicate(piece):
        lo, hi = piece
        lo_pred = (sympy.Q.gt(sym, lo) if not getattr(piece, "closed_lo", True)
                  else sympy.Q.ge(sym, lo))
        hi_pred = (sympy.Q.lt(sym, hi) if not getattr(piece, "closed_hi", True)
                  else sympy.Q.le(sym, hi))
        return sympy.And(lo_pred, hi_pred)

    if isinstance(bound, LanguageRef) or (
            isinstance(bound, Domain) and bound.base_type == "L"):
        # a language domain states nothing a real symbol can carry
        return None
    if isinstance(bound, Domain) and bound.base_type == "C":
        # ordering predicates have no complex reading; only exclusions
        # survive as facts.
        ne_clauses = [sympy.Q.ne(sym, v) for v in bound.excluded
                      if not isinstance(v, _Sentinel)]
        if not ne_clauses:
            return None
        return sympy.And(*ne_clauses) if len(ne_clauses) > 1 else ne_clauses[0]
    if isinstance(bound, Domain):
        piece_preds = []
        for piece in bound.pieces:
            if isinstance(piece, frozenset):
                eqs = [sympy.Eq(sym, v) for v in piece
                       if not isinstance(v, _Sentinel)]
                if eqs:
                    piece_preds.append(sympy.Or(*eqs) if len(eqs) > 1 else eqs[0])
            elif isinstance(piece, tuple):
                piece_preds.append(interval_predicate(piece))
        clause = (sympy.Or(*piece_preds) if len(piece_preds) > 1
                 else (piece_preds[0] if piece_preds else None))
        ne_clauses = [sympy.Q.ne(sym, v) for v in bound.excluded
                      if not isinstance(v, _Sentinel)]
        parts = ([clause] if clause is not None else []) + ne_clauses
        if not parts:
            return None
        return sympy.And(*parts) if len(parts) > 1 else parts[0]
    if isinstance(bound, tuple) and not isinstance(bound, frozenset) and len(bound) == 2:
        return interval_predicate(bound)
    return None


def _reach_piece(bound, lo_reach: float, hi_reach: float):
    """Intent:
        One interval with its infinite ends replaced by the reach
        (`domain.ReachInterval`, closed at a reach end), or the bound
        unchanged when it is not an interval with an infinite end.
    """
    if not (isinstance(bound, tuple) and not isinstance(bound, frozenset)
            and len(bound) == 2) or isinstance(bound, ReachInterval):
        return bound
    try:
        lo, hi = float(bound[0]), float(bound[1])
    except (TypeError, ValueError):
        return bound
    lo_inf, hi_inf = lo == -math.inf, hi == math.inf
    if not (lo_inf or hi_inf):
        return bound
    return ReachInterval(
        lo_reach if lo_inf else bound[0], hi_reach if hi_inf else bound[1],
        True if lo_inf else getattr(bound, "closed_lo", True),
        True if hi_inf else getattr(bound, "closed_hi", True),
        reach_lo=lo_inf, reach_hi=hi_inf)


def operational_domain(cj_domain: dict, reach: "tuple[float, float]",
                        bare=()):
    """Intent:
        The computation's reading of a claim's domain: every infinite
        interval end, including one inside a union of real pieces and the
        whole line of a bare `R`, replaced by the reach (the resolved
        pseudo-infinity, else the number representation's maximum), and
        every name in `bare` (a real parameter no domain was declared for)
        given the whole reach, marked as undeclared. Every finite end and
        every other bound stays as declared. Returns the rewritten copy
        and a rendering of each interval change.

    Notes:
        The probe stage's reading, and only the probe stage's: the
        operational infinity bounds the computation, never the
        mathematics (P1, P6), so a proof is over the declared domain
        with infinity as infinity. A real domain contains no infinity:
        the rewritten ends are finite, and the sampler draws an
        unbounded direction log-uniformly over the decades up to the
        reach (`_sampling._synth_scalar`). Integer and natural types
        and vector spaces are not rewritten.
    """
    from dataclasses import replace as _replace
    lo_reach, hi_reach = reach
    rewritten: dict = {}
    changes: list = []
    for p, bound in cj_domain.items():
        if isinstance(bound, Domain):
            if bound.base_type != "R" or bound.dims:
                rewritten[p] = bound
            elif not bound.pieces:
                rewritten[p] = _replace(bound, pieces=(ReachInterval(
                    lo_reach, hi_reach, reach_lo=True, reach_hi=True,
                    bare=True),))
            else:
                rewritten[p] = _replace(bound, pieces=tuple(
                    _reach_piece(piece, lo_reach, hi_reach)
                    for piece in bound.pieces))
            continue
        rewritten[p] = _reach_piece(bound, lo_reach, hi_reach)
        if rewritten[p] is not bound:
            changes.append(f"{p} in {rewritten[p]!r}")
    for p in bare:
        if rewritten.get(p) is None:
            rewritten[p] = ReachInterval(lo_reach, hi_reach, reach_lo=True,
                                         reach_hi=True, bare=True)
    return rewritten, changes


def unbounded_directions(names, cj_domain: dict, *,
                         unsure_unbounded: bool = False) -> list:
    """Intent:
        The names among `names` whose bound in `cj_domain` is unbounded
        in some direction: no bound at all, or an infinite end. A bound
        whose ends cannot be read counts as bounded, or as unbounded
        when `unsure_unbounded` is set.
    """
    out = []
    for n in names:
        b = (cj_domain or {}).get(n)
        if b is None:
            out.append(n)
            continue
        try:
            if isinstance(b, tuple) and not isinstance(b, frozenset):
                lo, hi = float(b[0]), float(b[1])
            else:
                sset = bound_to_sympy_set(b)
                lo, hi = float(sset.inf), float(sset.sup)
        except Exception:
            if unsure_unbounded:
                out.append(n)
            continue
        if math.isinf(lo) or math.isinf(hi) \
                or getattr(b, "reach_lo", False) or getattr(b, "reach_hi", False):
            out.append(n)
    return out


def bound_to_sympy_set(bound):
    """The declared bound as a sympy `Set` over the reals, intervals
    with exact open/closed endpoints, discrete sets as `FiniteSet`,
    `"Z"`/`"N"` (and a `Domain`'s integer `base_type`) via intersection
    with `S.Integers`/`S.Naturals0`, unions of pieces as `Union`, and
    exclusions as a `Complement`. `MISSING` never enters the set (it is
    not a real number); read the policy via `missing_included()`. An
    unrecognized bound *shape* comes back as `S.Reals` (the same
    "everywhere" default an unstated domain asserts), but an unknown
    base *type* name raises `InvalidDomain`; a stated type must never
    be silently read as real.

    Raises:
        InvalidDomain: for a base type outside `KNOWN_BASE_TYPES`, and
            for a language domain, which has no real-set reading at
            all (a caller settling a guard against `S.Reals` would be
            reasoning about strings as numbers)."""
    import sympy

    if bound == "L" or isinstance(bound, LanguageRef) or (
            isinstance(bound, Domain) and bound.base_type == "L"):
        raise InvalidDomain("a language domain (L[...]) has no real-set "
                            "reading")

    def piece_set(piece):
        if isinstance(piece, frozenset):
            return sympy.FiniteSet(*[v for v in piece
                                     if not isinstance(v, _Sentinel)])
        lo, hi = piece
        return sympy.Interval(lo, hi,
                              left_open=not getattr(piece, "closed_lo", True),
                              right_open=not getattr(piece, "closed_hi", True))

    if bound is None:
        return sympy.S.Reals
    if bound == "Z":
        return sympy.S.Integers
    if bound == "N":
        return sympy.S.Naturals0
    if bound == "C":
        return sympy.S.Complexes
    if isinstance(bound, str):
        _require_known_base_type(bound)
        return sympy.S.Reals   # a bare explicit "R"
    if isinstance(bound, frozenset):
        return sympy.FiniteSet(*[v for v in bound
                                 if not isinstance(v, _Sentinel)])
    if isinstance(bound, tuple) and len(bound) == 2:
        return piece_set(bound)
    if isinstance(bound, Domain):
        _require_known_base_type(bound.base_type)
        if bound.base_type == "C":
            # the sound over-approximation: pieces (a rectangle, a
            # segment) have no sympy real-set reading, and every
            # projection consumer treats the set as an upper bound on
            # where the parameter ranges.
            return sympy.S.Complexes
        base = {"R": sympy.S.Reals, "Z": sympy.S.Integers,
                "N": sympy.S.Naturals0}[bound.base_type]
        if bound.pieces:
            covered = sympy.Union(*[piece_set(p) for p in bound.pieces])
            result = sympy.Intersection(covered, base)
        else:
            result = base
        real_excluded = [v for v in bound.excluded
                         if not isinstance(v, _Sentinel)]
        if real_excluded:
            result = sympy.Complement(result, sympy.FiniteSet(*real_excluded))
        return result
    return sympy.S.Reals
