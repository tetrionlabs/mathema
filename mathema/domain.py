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
from dataclasses import dataclass

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


#: dimension names of a space exponent: a single name, or a product
#: (`m*n`/`m×n`). Names are identifiers; a bare integer is allowed for a
#: fixed dimension (`R^3`).
_DIM_EXPONENT = re.compile(
    r"^(?:[A-Za-z_]\w*|\d+)(?:\s*[*×]\s*(?:[A-Za-z_]\w*|\d+))*$")


_SUPERSCRIPT_RUN = re.compile(
    "[" + "".join(re.escape(c) for c in _SUPERSCRIPT.values()) + "]+")


def _desuperscript(text: str) -> str:
    """Any run of superscript characters rewritten as an explicit
    `^<plain>` power, so the unicode space form (`ℝⁿ`, `[0,1]ᵏ`) and
    the ascii form (`R^n`, `[0,1]^k`) reach the same parse. A multi-
    token exponent is parenthesised (`ℝᵐˣⁿ` -> `R^(m×n)`) so the top-
    level caret split reads it as one exponent."""
    def repl(m):
        plain = _from_superscript(m.group(0))
        return f"^({plain})" if any(c in "×*" for c in plain) else f"^{plain}"
    return _SUPERSCRIPT_RUN.sub(repl, text)


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
    """A space exponent (`n`, `m*n`, `(m×n)`, superscript forms) as a
    tuple of dimension tokens, or None when it is not a dimension
    exponent at all (so an ordinary numeric power is left alone)."""
    exp = _from_superscript(exponent).strip()
    if exp.startswith("(") and exp.endswith(")"):
        exp = exp[1:-1].strip()
    if not _DIM_EXPONENT.match(exp):
        return None
    parts = re.split(r"\s*[*×]\s*", exp)
    return tuple(p.strip() for p in parts if p.strip())


class InvalidDomain(ValueError):
    """Raised by `split_quantifier()` when text that clearly started a
    quantifier (`for ... :`) has a binding that doesn't parse, a real,
    specific reason (which part, what's wrong with it), never a silent
    empty domain that leaves an author guessing why their claim's own
    declared bounds didn't take effect. Never raised for text that
    doesn't look like a quantifier at all (no leading `for ... :`);
    that's legitimately "no domain here", not a syntax error."""


_FOR_PREFIX = re.compile(r"^\s*for\s+", re.DOTALL)
# "x in D" / "x ∈ D" / "x \in D" / "x \elem D", all one membership
# operator, matched up front so every binding shape below only ever has
# to key on the literal word "in" internally.
_MEMBERSHIP_OPS = r"(?:in|\\elem|\\in|∈)"
# the name may be dotted (`self.rate`, `cfg.a`): a bundled parameter's
# field is quantified exactly like a scalar parameter
_MEMBERSHIP_PREFIX = re.compile(rf"^\s*(?P<name>\w+(?:\.\w+)?)\s+{_MEMBERSHIP_OPS}\s+")
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
# The rendered missing-value clause, union side (`∪ {∅}` / `| {missing}`).
# Missing is included by default, so this states the resolved policy
# rather than changing it, but it has to be peeled off before the
# union split, or `ℕ ∪ {∅}` reads as two pieces (a named set unioned
# with a set containing the missing sentinel) instead of "ℕ, missing
# allowed", and `[0,1] \ {1} ⊂ ℝ ∪ {∅}` folds the clause into the
# exclusion set and fails to parse at all. The exclusion side
# (`\ {∅}`) is deliberately NOT matched here: excluding missing is a
# real narrowing and belongs in `_EXCLUDE_SUFFIX`'s hands.
#
# Two spellings, because rendering has two: the unicode set clause
# (`∪ {∅}`) and the ascii annotation-fused one (`:float|missing`, or a
# bare `N|missing`). The ascii form matters as much as the unicode one;
# `|` is also the union operator, so an unstripped `N|missing` reads
# as "the named set N unioned with a set called missing".
_UNION_MISSING_SUFFIX = re.compile(
    r"\s*(?:(?:\||∪)\s*\{\s*(?:∅|missing|NA|nan|None)\s*\}"
    r"|\|\s*(?:missing|NA|nan|None))\s*$")
# One union piece: an interval (either spelling, `(0, 1]` bracket
# semantics as ever), a discrete set, or a bare named set (R/Z/N),
# the same three shapes `split_quantifier()` always supported, just
# without the "name in" prefix, since a piece after the first `|`/`∪`
# never repeats it.
_PIECE_RANGE = re.compile(r"^([\[\(])\s*([^,]+?)\s*,\s*\.\.\.\s*,\s*(.+?)\s*([\]\)])$")
_PIECE_INTERVAL = re.compile(r"^([\[\(])\s*([^,]+?)\s*,\s*(.+?)\s*([\]\)])$")
_PIECE_SET = re.compile(r"^\{\s*(.*?)\s*\}$")
_PIECE_NAMED = re.compile(r"^(R|Z|N|C|ℝ|ℤ|ℕ|ℂ)$")
# Sampling-intensity modifiers, not a parameter binding at all: `n=500`
# in the same comma-list sets domain["n"] (how many draws/rows, not a
# bound on any variable); domain means scope *and* intensity of
# verification, not just numeric range.
_BINDING_INTENSITY = re.compile(r"^\s*n\s*=\s*(\d+)\s*$")
_BOUND_CONSTS = {"pi": math.pi, "-pi": -math.pi, "e": math.e,
                 "oo": math.inf, "-oo": -math.inf,
                 "infinity": math.inf, "-infinity": -math.inf}
# a discrete-set member written as a whole number, which stays an int
# rather than going through _bound()'s float(), see _set_value()
_INTEGER_MEMBER = re.compile(r"^[+-]?\d+$")


def _set_value(s: str):
    """One element of a discrete-set domain (`x in {...}`): the missing-
    value sentinel (`∅`/`missing`/`NA`/`nan`/`None`, checked first since
    none of these could plausibly mean anything else in this position),
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
    if s in _MISSING_TOKENS:
        return MISSING
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


class _MissingType:
    """The one canonical sentinel for a missing/null value inside a
    domain's `excluded`/unioned set, spelled `∅`/`missing`/`NA`/`nan`
    on input, always this one object internally (identity-compared, so
    `MISSING in dom.excluded` is a plain membership test regardless of
    which spelling produced it)."""
    def __repr__(self) -> str:
        return "∅"

    def __eq__(self, other) -> bool:
        return self is other

    def __hash__(self) -> int:
        return hash("mathema.MISSING")


MISSING = _MissingType()
_MISSING_TOKENS = {"∅", "missing", "NA", "nan", "None"}
# Type names of known missing-value sentinels that aren't themselves
# IEEE-754 NaN-like (pandas' pd.NA/pd.NaT: `pd.NA != pd.NA` is itself a
# non-boolean NA, not a clean True/False, so the self-inequality check
# below can't see them), checked by name only, no import of the
# library that defines them, so this stays extensible (another
# library's own null type name is one more string here) without ever
# turning pandas, or anything else, into a hard dependency of core.
_MISSING_TYPE_NAMES = frozenset({"NAType", "NaTType"})


def is_missing(value) -> bool:
    """A value is missing if it's `None`, this module's own `MISSING`
    sentinel, IEEE-754 NaN (self-inequality catches a Python `float`, a
    numpy `float64`, and a pandas float uniformly, all three being
    ordinary IEEE-754 under the hood, with no import of any of them
    needed), or one of a small, extensible set of known missing-
    sentinel type names checked by name alone."""
    if value is None or value is MISSING:
        return True
    try:
        if value != value:
            return True
    except Exception:
        pass
    return type(value).__name__ in _MISSING_TYPE_NAMES


# transitional alias: is_missing was _is_missing until the 2026-08
# refactor; slated for removal once nothing references the old name.
_is_missing = is_missing


@dataclass(frozen=True)
class Domain:
    """A domain that's more than one bare `Interval`/`"Z"`/`"N"`/
    `frozenset` (`split_quantifier()`'s original three shapes): a union
    of one or more `pieces` (each an `Interval` or a discrete-value
    `frozenset`), restricted to `base_type` (`"R"`/`"Z"`/`"N"`), minus
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


# the closed vocabulary of base types a Domain may carry. Every
# function that projects a domain into sympy or answers membership
# checks against this set and refuses an unknown name loudly, an
# unrecognized type silently treated as real is a wrong proof waiting
# to happen, not a default.
KNOWN_BASE_TYPES = frozenset({"R", "Z", "N", "C"})


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
        A bare "Z"/"N" string carries no missing-value exclusion by
        default, the same as parse_binding() applies for grammar-parsed
        text; missing is included unless a binding's own text
        explicitly excludes it. A hand-built Domain object is returned
        unchanged.
    """
    if bound is None:
        return Domain()
    if isinstance(bound, Domain):
        return bound
    if isinstance(bound, str):
        return Domain(base_type=bound, explicit_type=True)
    if isinstance(bound, frozenset):
        return Domain(pieces=(bound,))
    if isinstance(bound, tuple):
        return Domain(pieces=(bound,))
    return Domain()


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


def finite_members(bound, limit: int):
    """Intent:
        Every value the domain `bound` admits, as a sorted tuple, when
        there are finitely many of them and no more than `limit`. `None`
        when the domain is infinite, is not enumerable, or is larger
        than `limit`.

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
        so it is declined. `excluded` is honoured, and `MISSING` in it
        is ignored here because it is a policy for absent values rather
        than a member of the value set.
    """
    if isinstance(bound, frozenset):
        members = sorted(bound, key=_member_sort_key)
        return tuple(members) if len(members) <= limit else None
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
    out -= {v for v in bound.excluded if not isinstance(v, _MissingType)}
    if not out or len(out) > limit:
        # an empty region is not something to sweep: a clean pass over
        # no points is vacuous, and the convention for an empty region
        # is to say nothing rather than to prove everything (the same
        # rule `_tighten_domain_by_assumption` follows).
        return None
    return tuple(sorted(out, key=_member_sort_key))


def domain_contains(value, bound) -> bool:
    """Is `value` a member of the domain `bound` describes, the single
    source of truth every consumer (`authoring.enforce_domain`, the
    derive route's concrete checks, domain-aware probing) calls through,
    rather than each re-deriving membership logic inline (which is
    exactly how `enforce_domain`'s own interval check went silently
    blind to `Interval.closed_lo`/`closed_hi`, checked identically to a
    closed bound for years). Missingness is checked
    first, before any bound/piece comparison at all: a missing value is
    exempt (never evaluated against `pieces`/`base_type`) unless
    `MISSING` is itself in `excluded`, included by default, the same
    as `parse_binding()` resolves at parse time, unless the domain's
    own text explicitly excluded it."""
    dom = _as_domain(bound)
    _require_known_base_type(dom.base_type)
    if is_missing(value):
        return MISSING not in dom.excluded
    if value in dom.excluded:
        return False
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
    value, then strings alphabetically, then the missing sentinel.
    Ordering by `str` alone would put `{1, 10, 2}` in that order and
    would interleave the sentinel with real values."""
    if v is MISSING:
        return (2, 0.0, "")
    if isinstance(v, str):
        return (1, 0.0, v)
    return (0, float(v), "")


def _render_set_member(v, *, ascii_mode: bool) -> str:
    """One discrete-set member in the spelling the input grammar reads
    back: the sentinel as `∅` (`missing` in ascii), a string always
    double-quoted, everything else as its own literal. `_set_value`
    accepts either quote style on the way in and keeps neither, so one
    spelling comes back out.

    A member whose own text contains a quote or a comma is outside what
    a set binding can express; `_split_commas` is not quote-aware, so
    such a value cannot be read back whatever it is rendered as."""
    if v is MISSING:
        return "missing" if ascii_mode else "∅"
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)


def _render_piece(piece, *, ascii_mode: bool, as_int: bool = False) -> str:
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
    """A space exponent for `dims`: `^n`/`^(m*n)` in ascii, and the
    unicode superscript (`ⁿ`/`ᵐˣⁿ`) when every character has a
    superscript form, else the parenthesised `^(m×n)` spelling."""
    if not dims:
        return ""
    if ascii_mode:
        body = "*".join(dims)
        return f"^{body}" if len(dims) == 1 else f"^({body})"
    body = "×".join(dims)
    sup = _to_superscript(body)
    return sup if sup is not None else f"^({body})"


def render_domain(bound, *, show_missing: bool = True, ascii_mode: bool | None = None,
                  always_show_type: bool = True) -> str:
    """A domain -> the canonical set-notation text a person would type
    for it, always in the same glyph vocabulary the input grammar
    itself accepts, never a natural-language paraphrase of it, input
    stays terse (nothing to type for the common case, no type ever
    required), but a rendered domain never leaves a real,
    differently-meaningful default unstated: a bounded interval always
    states its resolved type (`R` by default, same as any explicit
    `Z`/`N`), even when the input that produced it never mentioned one.
    A domain with no real restriction at all (unbounded on both sides,
    `(-inf, inf)`, whichever spelling produced it) collapses to just the
    bare type name/glyph instead of an infinite-looking interval,
    `R`/`ℝ`, not `(-oo, oo) subset R`/`(-oo, oo) ⊂ ℝ`. `always_show_type`
    is this behavior's own off switch: `render_domain_bound()`'s own,
    narrower surface (an always-hand-typed docstring `Domain:` block,
    not a caller-facing claim rendering) passes `False`, keeping its
    own longstanding terse-when-unstated spelling.

    `show_missing` defaults to `True`: a claim is the one place
    mathematics and code meet, so a rendered domain never leaves the
    resolved missing-value policy unstated by default, explicitly
    opt out (`show_missing=False`) only for a surface that's never
    meant to state it at all, like `render_domain_bound()`'s own
    docstring-block spelling. Renders the *resolved* missing-value
    policy explicitly, whether or not the caller's domain text ever
    mentioned it. In unicode mode this is the
    same trailing `∪ {∅}`/`\\ {∅}` clause input already uses; in ascii
    mode it instead fuses directly onto the type annotation, Python
    union-type style, `[0, 1000]:float|missing` when a missing value
    is allowed, plain `[0, 1000]:float` (no suffix at all) when it
    isn't; since the ascii type spelling is already its own compact,
    Python-flavored annotation (see `_ASCII_TYPE_ANNOTATION` below),
    matching that same style for the missing-value state is more
    consistent than reusing the unicode set-builder clause verbatim.

    `ascii_mode` renders `R`/`Z`/`N` plain rather than as `ℝ`/`ℤ`/`ℕ`.
    A bounded interval's own type clause additionally prefers a
    Python-style annotation over the worded one in ascii mode,
    `[1, 100]:float`/`[1, 100]:int` rather than `[1, 100] subset R`/
    `[1, 100] subset Z` (`N` has no matching Python type name, so it
    keeps the worded `subset N` form in ascii too); both spellings are
    valid input either way (`parse_binding()` accepts both, see
    `_SUBSET_ANYWHERE`). Left unstated (`None`, the default), `ascii_mode`
    follows the global `get_unicode_output()` preference instead of
    committing to one on its own, pass it explicitly to pin one
    spelling regardless of that global setting. A `Z`/`N`-typed bound's
    own interval endpoints render without a `.0` when they're whole
    numbers (`[1, 100]:int`, not `[1.0, 100.0]:int`), a genuinely
    fractional endpoint (`[0.5, 100]:int`, however that came to be
    declared) still shows its fractional part, never silently
    truncated."""
    if ascii_mode is None:
        ascii_mode = not get_unicode_output()
    dom = _as_domain(bound)
    real_pieces = [p for p in dom.pieces
                  if not (isinstance(p, frozenset) and set(p) <= {MISSING})]
    # an explicitly enumerated domain states its own members, so it
    # carries no inferred element type: a set of strings is not a subset
    # of the reals. The sentinel is never listed among the members;
    # it rides the same trailing `∪ {∅}` union clause every other shape
    # uses, so one spelling states the missing-value policy everywhere
    enumerated = bool(real_pieces) and all(
        isinstance(p, frozenset) for p in real_pieces)
    enumerated_missing = enumerated and any(
        MISSING in p for p in real_pieces)
    if enumerated_missing:
        real_pieces = [frozenset(p - {MISSING}) for p in real_pieces]
        real_pieces = [p for p in real_pieces if p]
    numeric_excluded = dom.excluded - {MISSING}
    fully_unbounded = (
        len(real_pieces) == 1 and not numeric_excluded
        and not isinstance(real_pieces[0], (str, frozenset))
        and real_pieces[0][0] == float("-inf") and real_pieces[0][1] == float("inf"))
    missing_included = show_missing and MISSING not in dom.excluded
    exp = _render_dims(getattr(dom, "dims", ()), ascii_mode)
    if not real_pieces or fully_unbounded:
        text = dom.base_type if ascii_mode else _TYPE_GLYPH.get(dom.base_type, dom.base_type)
        text += exp
        if numeric_excluded:
            # a bare-type domain can still carry exclusions (N \ {3});
            # dropping them here would render a wider set than the one
            # actually declared
            text += " \\ " + _render_piece(
                frozenset(numeric_excluded), ascii_mode=ascii_mode,
                as_int=dom.base_type in ("Z", "N"))
        if show_missing and ascii_mode:
            text += "|missing" if missing_included else ""
    else:
        as_int = dom.base_type in ("Z", "N")
        text = " ∪ ".join(_render_piece(p, ascii_mode=ascii_mode, as_int=as_int)
                          for p in real_pieces)
        text += exp
        if numeric_excluded:
            text += " \\ " + _render_piece(frozenset(numeric_excluded), ascii_mode=ascii_mode,
                                           as_int=as_int)
        if (always_show_type or dom.base_type != "R") and not (
                enumerated and not dom.explicit_type):
            text += _type_annotation_suffix(dom.base_type, ascii_mode)
            if show_missing and ascii_mode and missing_included and not enumerated:
                text += "|missing"
    if enumerated:
        if show_missing and enumerated_missing:
            text += "|missing" if ascii_mode else " ∪ {∅}"
    elif show_missing and not ascii_mode:
        text += " \\ {∅}" if not missing_included else " ∪ {∅}"
    return text


# every bounded domain's own resolved type is always stated in rendered
# output (never left implicit, even for the common default "R" case),
# matching this grammar's own terse-input/explicit-output split, input
# never has to say "float"/"subset R" to mean an ordinary real interval,
# but a rendered claim always does. ASCII prefers a Python-style type
# annotation (`[1, 100]:float`/`[1, 100]:int`, no leading space) over the
# `subset`-worded clause, matching the input spelling `parse_binding()`'s
# own `_SUBSET_ANYWHERE` accepts for it; `N` has no matching Python
# type name, so it keeps the worded `subset N` clause in ascii too.
_ASCII_TYPE_ANNOTATION = {"R": ":float", "Z": ":int", "C": ":complex"}


def _type_annotation_suffix(base_type: str, ascii_mode: bool) -> str:
    if ascii_mode:
        return _ASCII_TYPE_ANNOTATION.get(base_type, f" subset {base_type}")
    return f" ⊂ {_TYPE_GLYPH.get(base_type, base_type)}"


# the one JSON-safe stand-in for MISSING inside a stored `excluded`/`set`
# list, any real string value in a discrete set is user-authored text
# straight out of `_set_value()`, which never itself produces this exact
# token, so there's no real collision to guard against.
_MISSING_JSON_TOKEN = "__mathema_missing__"


def _json_value(v):
    return _MISSING_JSON_TOKEN if v is MISSING else v


def _value_from_json(v):
    return MISSING if v == _MISSING_JSON_TOKEN else v


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
               "excluded": sorted((_json_value(v) for v in b.excluded), key=str),
               "explicit_type": b.explicit_type}
        if b.dims:
            out["dims"] = list(b.dims)
        return out
    if isinstance(b, str):
        return b
    if isinstance(b, frozenset):
        return {"set": sorted((_json_value(v) for v in b), key=str)}
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
    if "base_type" in v:
        return Domain(base_type=v["base_type"],
                      pieces=tuple(domain_bound_from_json(p) for p in v["pieces"]),
                      excluded=frozenset(_value_from_json(x) for x in v["excluded"]),
                      explicit_type=v.get("explicit_type", False),
                      dims=tuple(str(d) for d in v.get("dims", ())))
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
    (this is the docstring-`Domain:`-block round-trip path, `to_domain_
    block()`, where a bare `x: [0, 1]` line has never needed to say
    anything about missing values and shouldn't start now), its type
    names spelled plain (`Z`, not `ℤ`), and its resolved type left
    unstated for the common, unrefined case (`[0, 1]`, not
    `[0, 1]:float`), a hand-editable surface, typeable without
    reaching for a Unicode glyph or a type annotation neither was ever
    required before."""
    return render_domain(b, show_missing=False, ascii_mode=True, always_show_type=False)


def _parse_piece(text: str):
    """One union-piece's text (an interval, either spelling; a discrete
    set; a bare named set; or a bare missing-value token) -> `Interval` |
    `frozenset` | `"R"`/`"Z"`/`"N"` | `None` when it's none of those. No
    "name in" prefix here, a piece after the first `|`/`∪` in a
    binding never repeats it. A bare `missing`/`∅`/`NA`/`nan`/`None`
    (no braces) is shorthand for the same singleton `{∅}` the
    brace-wrapped discrete-set spelling already produces, reusing the
    existing `|`/`∪` union operator rather than inventing a second,
    conflicting meaning for `|` (already this grammar's own ascii
    spelling for `∪`), so `[0, 100]:float|missing` means exactly
    `[0, 100]:float ∪ {missing}`, parsed the same way, not a new,
    separate mechanism."""
    text = text.strip()
    if text in _MISSING_TOKENS:
        return frozenset({MISSING})
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
            return frozenset(_set_value(v) for v in _split_commas(m.group(1)) if v.strip())
        except ValueError:
            return None
    m = _PIECE_NAMED.match(text)
    if m is not None:
        return _SUBSET_ASCII.get(m.group(1), m.group(1))
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


def _parse_binding(part: str):
    """Intent:
        The one implementation behind `parse_binding()`: `(name, value)`
        on success, or a specific human-readable failure reason (a
        `str`) naming the first stage that didn't check out, so
        `split_quantifier()` can raise `InvalidDomain` with a clear,
        actionable message from the very parse that failed, never a
        separate re-walk that must be kept in lockstep by hand (the old
        `_explain_binding_failure`, retired).
    """
    text = _desuperscript(part.strip())
    type_explicit = None

    # the union-side missing clause first: it is a statement of the
    # resolved default, not part of the set expression, and every other
    # clause below would otherwise absorb it. Whether it was actually
    # written is remembered: on an enumerated domain the sentinel is a
    # member of the set, so the clause folds back into it below
    stripped = _UNION_MISSING_SUFFIX.sub("", text).strip()
    missing_declared = stripped != text
    text = stripped

    m = _SUBSET_ANYWHERE.search(text)
    if m is not None:
        type_explicit = _SUBSET_ASCII.get(m.group("type"), m.group("type"))
        text = (text[:m.start()] + " " + text[m.end():]).strip()
    # a `⊂ TYPE` clause can sit between the domain and the missing
    # clause (`[0,1] ⊂ ℝ ∪ {∅}`), so look again once it is gone
    stripped = _UNION_MISSING_SUFFIX.sub("", text).strip()
    missing_declared = missing_declared or stripped != text
    text = stripped

    excluded_text = None
    m = _EXCLUDE_SUFFIX.search(text)
    if m is not None:
        excluded_text = m.group("set")
        text = text[:m.start()].rstrip()

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
    split = _split_top_caret(rest)
    if split is not None:
        parsed_dims = _parse_dims(split[1])
        if parsed_dims is not None:
            rest, space_dims = split[0], parsed_dims
    piece_texts = _UNION_SPLIT.split(rest)
    pieces = []
    for pt in piece_texts:
        if not pt or _parse_piece(pt) is None:
            return (f"{part!r}: {pt!r} isn't a recognized interval, discrete "
                    f"set, or named set (R/Z/N) for {name!r}")
        pieces.append(_parse_piece(pt))

    # a single bare named-set piece ("x in Z", "x in R") sets the base
    # type directly, the same as an explicit ⊂ clause would; it isn't
    # really a "piece" (there's no interval/discrete-set to union
    # alongside), and stating it at all is just as deliberate a type
    # choice as ⊂ Z.
    if len(pieces) == 1 and isinstance(pieces[0], str):
        bare_type = pieces[0]
        if type_explicit is not None and type_explicit != bare_type:
            return (f"{part!r}: states two different types ({bare_type} and "
                    f"⊂ {type_explicit}) for {name!r}")
        type_explicit = bare_type
        pieces = []

    excluded = set()
    if excluded_text is not None:
        try:
            for v in _split_commas(excluded_text):
                if v.strip():
                    excluded.add(_set_value(v))
        except ValueError:
            return (f"{part!r}: an excluded value in {{{excluded_text}}} isn't "
                    f"a recognized number, string, boolean, or missing sentinel")

    # missing is included by default, always, stating a type
    # (⊂ Z/N/R, or the bare Z/N/R spelling above) never excludes it as a
    # side effect. A domain excludes a missing value only when the
    # binding's own text says so directly (the `\{...}` clause parsed
    # above, into `excluded`); an unverified default has to be the
    # wider, safer one: "missing excluded" is not something a claim's
    # own domain text gets to assert true by stating it, only something
    # a real proof against the function can earn.

    def _complex_cornered(piece):
        return (isinstance(piece, tuple) and not isinstance(piece, frozenset)
                and any(isinstance(v, complex) for v in piece))

    if any(_complex_cornered(p) for p in pieces):
        # complex corner literals name a rectangle of the plane: the
        # type is C whether or not the binding spelled it, and a stated
        # real type contradicts the corners outright.
        if type_explicit not in (None, "C"):
            return (f"{part!r}: complex interval corners contradict the "
                    f"stated type {type_explicit}")
        type_explicit = "C"

    base_type = type_explicit or "R"

    # an enumerated domain carries the sentinel as a member of the set,
    # so a written `∪ {∅}` clause folds back in here. That is what makes
    # `{"a"} ∪ {∅}` and `{"a", missing}` one domain with one rendering,
    # and what lets the rendered form parse back to what produced it.
    if (missing_declared and pieces
            and all(isinstance(pc, frozenset) for pc in pieces)):
        pieces = [frozenset(pieces[0] | {MISSING})] + list(pieces[1:])

    # collapse to the OLD raw shape only when the type was never stated
    # at all and nothing else new was used either, a *stated* type
    # always needs the richer Domain shape to carry its own missing-
    # value policy, even with no pieces/exclusions beyond it. A space
    # power (`^n`) always needs the Domain shape, to carry its dims.
    if (type_explicit is None and not excluded and len(pieces) == 1
            and not space_dims):
        return name, pieces[0]

    return name, Domain(base_type=base_type, pieces=tuple(pieces),
                       excluded=frozenset(excluded),
                       explicit_type=type_explicit is not None,
                       dims=space_dims)


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
    if len(bound.pieces) != 1:
        return bound, None
    piece = bound.pieces[0]
    if isinstance(piece, frozenset) or not isinstance(piece, tuple):
        return bound, None
    lo, hi = piece
    if not (lo == 0 and getattr(piece, "closed_lo", True)
            and hi == float("inf")):
        return bound, None
    declared = render_domain_bound(bound)
    return Domain(base_type="N", pieces=(), excluded=bound.excluded,
                  explicit_type=True), declared


def missing_included(bound) -> bool:
    """Whether the declared bound admits a missing value (None/NaN/the
    `MISSING` sentinel). Missing is included by default for every bound
    shape; only an explicit `\\ {∅}`-style exclusion on a `Domain`
    narrows it. This is the one place that policy is read from, the
    prover states it in sketches, the renderer prints it, and neither
    re-detects it from the pieces."""
    if isinstance(bound, Domain):
        return not any(v is MISSING for v in bound.excluded)
    return True


def bound_pin(bound):
    """The single value a *degenerate* bound admits, `(True, value)`
    for `[v, v]` with both ends closed (or a `Domain` whose only piece
    is such an interval, with nothing excluded), `(False, None)`
    otherwise. The caller substitutes the value for the symbol outright
    (converting to an exact literal itself if it needs sympy exactness);
    a degenerate range that never pinned anything used to be a real,
    confusing adjudication gap."""
    if isinstance(bound, Domain):
        if (len(bound.pieces) == 1 and isinstance(bound.pieces[0], tuple)
                and not isinstance(bound.pieces[0], frozenset)
                and not bound.excluded):
            return bound_pin(bound.pieces[0])
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
        if len(bound.pieces) != 1 or isinstance(bound.pieces[0], frozenset):
            return None
        wrapper, piece = bound, bound.pieces[0]
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
    if isinstance(bound, Domain):
        _require_known_base_type(bound.base_type)
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
                               and all(v is MISSING for v in p)))
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

    if isinstance(bound, Domain) and bound.base_type == "C":
        # ordering predicates have no complex reading; only exclusions
        # survive as facts.
        ne_clauses = [sympy.Q.ne(sym, v) for v in bound.excluded if v is not MISSING]
        if not ne_clauses:
            return None
        return sympy.And(*ne_clauses) if len(ne_clauses) > 1 else ne_clauses[0]
    if isinstance(bound, Domain):
        piece_preds = []
        for piece in bound.pieces:
            if isinstance(piece, frozenset):
                eqs = [sympy.Eq(sym, v) for v in piece if v is not MISSING]
                if eqs:
                    piece_preds.append(sympy.Or(*eqs) if len(eqs) > 1 else eqs[0])
            elif isinstance(piece, tuple):
                piece_preds.append(interval_predicate(piece))
        clause = (sympy.Or(*piece_preds) if len(piece_preds) > 1
                 else (piece_preds[0] if piece_preds else None))
        ne_clauses = [sympy.Q.ne(sym, v) for v in bound.excluded if v is not MISSING]
        parts = ([clause] if clause is not None else []) + ne_clauses
        if not parts:
            return None
        return sympy.And(*parts) if len(parts) > 1 else parts[0]
    if isinstance(bound, tuple) and not isinstance(bound, frozenset) and len(bound) == 2:
        return interval_predicate(bound)
    return None


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
        InvalidDomain: for a base type outside `KNOWN_BASE_TYPES`."""
    import sympy

    def piece_set(piece):
        if isinstance(piece, frozenset):
            return sympy.FiniteSet(*[v for v in piece if v is not MISSING])
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
        return sympy.FiniteSet(*[v for v in bound if v is not MISSING])
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
        real_excluded = [v for v in bound.excluded if v is not MISSING]
        if real_excluded:
            result = sympy.Complement(result, sympy.FiniteSet(*real_excluded))
        return result
    return sympy.S.Reals
