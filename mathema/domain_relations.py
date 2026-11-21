# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Relations between two domains: `A subset B`, `A = B`, `A != B`,
`A not subset B`, `A disjoint B`, and the proper subset written as the
conjunction `A subset B and A != B`. A domain is a set of values, a
number domain (`[0, 1]`, `Z`, `{1, 2}`) or a language (`L[ascii]`), and
a relation holds between two of one kind.

Each relation has one canonical spelling. `B supset A` reads as
`A subset B`, `not (A subset B)` as `A not subset B`, `A ⊊ B` as the
conjunction, and `A = ∅` as `A = {}`. The domains render as the domain
grammar renders them, so two spellings of one set that render apart
(`R`, `(-inf, inf)`) are two claims.

A relation between number domains is decided in exact arithmetic on
the sets the domains denote, endpoints as written. A universal one
(`subset`, `=`, `disjoint`) is proven when the set that would hold a
counterexample is empty, and falsified by a member of that set. A
negative one (`not subset`, `!=`) is proven by such a member. Every
member reported is first executed against both domains' own membership
test. Two finite sets of any values are compared member by member. A
relation over a language is decided from the regular-language
definitions the two sides state (`mathema.regular`): no string
separating them is a proof, and a string the solver finds is executed
against both sides before it counts. A language stating no definition
leaves the relation undecided.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from ._scan import mask_strings, unmask_strings
from .domain import (Domain, InvalidDomain, LanguageRef, _Sentinel,
                     _sentinel_piece, bound_to_sympy_set, domain_contains,
                     parse_binding, render_domain)

#: the relation a claim between two domains carries in `Conjecture.relation`
RELATION = "domains"

#: the canonical relation words, ascii and unicode
WORDS = {"subset": "⊆", "not subset": "⊈", "=": "=", "!=": "≠",
         "disjoint": "disjoint"}

NUMBERS = "a set of numbers"
LANGUAGE = "a language"

#: every accepted spelling of a relation between domains, read to
#: `(canonical word, operands swapped)`; `⊊` and `⊂` are handled apart
_SPELLINGS = {
    "subset": ("subset", False), "⊆": ("subset", False),
    "supset": ("subset", True), "⊇": ("subset", True),
    "not subset": ("not subset", False), "⊈": ("not subset", False),
    "disjoint": ("disjoint", False),
    "==": ("=", False), "=": ("=", False),
    "!=": ("!=", False), "≠": ("!=", False),
}

_OPERATOR = re.compile(
    r"(?<=\s)not\s+subset(?=\s)|(?<=\s)(?:subset|supset|disjoint)(?=\s)"
    r"|[⊆⊇⊈⊊⊂≠]|==|!=|(?<![<>=!:])=(?![=:])")

_EMPTY = ("{}", "∅")
_UNSETTLED = "the sets the two domains denote were not compared exactly"
NO_LOWERING = "a relation over a language has no solver lowering yet"


class InvalidDomainRelation(ValueError):
    """A statement that reads as a relation between two domains and is
    not one this grammar holds, with the spelling to write instead."""


@dataclass(frozen=True)
class Term:
    """One side of a relation: the parsed domain `bound`, its canonical
    ascii and unicode text, and its kind (`NUMBERS`, `LANGUAGE`, or
    None for the empty set, which is of either kind)."""
    bound: object
    text: str
    unicode: str
    kind: "str | None"


@dataclass(frozen=True)
class Relation:
    """`left <word> right`, `word` one of `WORDS`."""
    left: Term
    word: str
    right: Term

    def text(self, unicode: bool = False) -> str:
        word = WORDS[self.word] if unicode else self.word
        if self.word in ("=", "!="):
            return f"{_stated(self.left, unicode)} {word} {_stated(self.right, unicode)}"
        return (f"{self.left.unicode} {word} {self.right.unicode}" if unicode
                else f"{self.left.text} {word} {self.right.text}")


@dataclass(frozen=True)
class Statement:
    """A claim relating domains: one relation, or the two a proper
    subset is the conjunction of."""
    relations: tuple

    def text(self, unicode: bool = False) -> str:
        return " and ".join(r.text(unicode) for r in self.relations)


@dataclass(frozen=True)
class Decision:
    """How a statement was decided: `verdict` is `proven`, `falsified`
    or `unknown`; `reason` says why in a sentence; `witness` is the
    member the verdict rests on, when it rests on one, as `{"value":
    text, "in": [domain texts], "not in": [domain texts], "executed":
    True}`."""
    verdict: str
    reason: str
    witness: "dict | None" = None
    #: how it was decided: `domain_sets` (exact set arithmetic, or two
    #: finite sets member by member) or `smt` (the languages'
    #: definitions, asked of the solver)
    route: str = "domain_sets"
    #: the hash of each regular-language definition read, by domain text
    definitions: "dict | None" = None
    #: for a verdict that rests on definitions: one entry per definition
    #: read, as `check_definition` returns it
    assumptions: "list | None" = None


# ---- reading ----------------------------------------------------------

def _top_level(masked: str, pattern: "re.Pattern") -> list:
    """Every match of `pattern` in `masked` that starts outside all
    brackets, left to right, never overlapping."""
    found, depth, i = [], 0, 0
    while i < len(masked):
        ch = masked[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            m = pattern.match(masked, i)
            if m is not None:
                found.append(m)
                i = m.end()
                continue
        i += 1
    return found


def _balanced(masked: str) -> bool:
    """Whether every bracket in `masked` closes one opened inside it."""
    depth = 0
    for ch in masked:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _kind(bound) -> "str | None":
    """The kind of values a parsed domain holds."""
    if isinstance(bound, frozenset):
        if not bound:
            return None
        numbers = all(isinstance(v, (int, float, Fraction))
                      and not isinstance(v, bool) for v in bound)
        return NUMBERS if numbers else LANGUAGE
    if isinstance(bound, Domain) and bound.base_type == "L":
        return LANGUAGE
    return NUMBERS


def _states_more_than_values(bound) -> "str | None":
    """What a parsed domain states beyond a set of values, or None: a
    missing value admitted or removed, or the shape of a container."""
    if isinstance(bound, frozenset):
        return "a missing value" if any(isinstance(v, _Sentinel) for v in bound) else None
    if not isinstance(bound, Domain):
        return None
    if bound.dims:
        return "a shape"
    sentinels = (bound.absent or any(isinstance(v, _Sentinel) for v in bound.excluded)
                 or any(_sentinel_piece(p) for p in bound.pieces)
                 or any(isinstance(p, frozenset) and any(isinstance(v, _Sentinel) for v in p)
                        for p in bound.pieces))
    return "a missing value" if sentinels else None


_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?(?![\w.])")
_STATEMENT_SYNTAX = re.compile(
    r"\b(?:inf|subset|supset|not|disjoint|and|R|Z|N)\b|:\s*(?:int|integer|real|float)\b"
    r"|==|!=|[=⊆⊇⊈⊊≠ℝℤℕ∅∪∞\[\](){},|\\\s+-]")


def not_as_written(statement: str) -> "str | None":
    """Intent:
        Why the numbers in a relation between number domains, as its
        author wrote it, are not the numbers the domains hold, or None
        when they are. A decimal or a magnitude that is not exactly a
        double is kept by an interval as the nearest double, and so is
        a whole number past 2**53 written as an interval's endpoint; an
        endpoint written as an expression (`1/3`, `pi`) is evaluated in
        floating point. A whole number listed in a finite set is kept
        exactly.
    """
    masked, _ = mask_strings(statement)
    braces = [m.span() for m in re.finditer(r"\{[^{}]*\}", masked)]

    def exact_in_a_set(m) -> bool:
        return any(lo <= m.start() < hi for lo, hi in braces) \
            and re.fullmatch(r"[-+]?\d+", m.group(0)) is not None
    for m in _NUMBER.finditer(masked):
        token = m.group(0)
        if exact_in_a_set(m):
            continue
        try:
            written = Fraction(token)
            held = float(token)
        except (ValueError, ZeroDivisionError):
            return f"`{token}` is not read as a number"
        if held in (float("inf"), float("-inf")) or Fraction(held) != written:
            return (f"`{token}` is not held exactly by the domain (it is kept as the "
                    f"nearest double), so the relation is not decided on it")
    rest = _STATEMENT_SYNTAX.sub("", _NUMBER.sub("", masked))
    if rest:
        return (f"an endpoint in `{statement.strip()}` is written as an expression, which "
                f"the domain evaluates in floating point, so the relation is not decided "
                f"on it")
    return None


def _term(text: str) -> "Term | None":
    """Intent:
        `text` as one side of a relation, or None when it is not a
        domain at all (an expression, a name, a call).

    Raises:
        InvalidDomainRelation: the domain states a missing value or a
            shape, which a relation between sets of values does not
            compare.
    """
    text = text.strip()
    if not text:
        return None
    if text in _EMPTY:
        bound: object = frozenset()
    else:
        try:
            parsed = parse_binding(f"member in {text}")
        except (InvalidDomain, ValueError):
            return None
        if not isinstance(parsed, tuple) or parsed[0] != "member":
            return None
        bound = parsed[1]
    more = _states_more_than_values(bound)
    if more is not None:
        raise InvalidDomainRelation(
            f"a relation between domains compares sets of values, and "
            f"`{text}` states {more}")
    ascii_text = render_domain(bound, show_missing=False, always_show_type=False,
                               ascii_mode=True)
    if isinstance(bound, Domain) and bound.clause:
        # the integer clause keeps its colon spelling, since `⊂` between
        # two domains is a relation of its own
        unicode_text = ascii_text.replace(" | ", " ∪ ")
    else:
        unicode_text = render_domain(bound, show_missing=False, always_show_type=False,
                                     ascii_mode=False)
    return Term(bound, ascii_text, unicode_text, _kind(bound))


_SET_NAMES = ("R", "Z", "N", "Q", "C")
_TYPE_CLAUSE = re.compile(r":\s*(?:int|integer|real|float)\b")
_EQUALITY = ("==", "=", "!=", "≠")


def _reading(written: str, term: "Term | None", bound: frozenset) -> str:
    """Intent:
        How one side of `==` or `!=` reads: `value`, `domain`, or
        `open` when its text could be either. A name bound in the claim
        is a value, and so is anything that is no domain at all (a
        call, a number, a list of other than two items). A language, a
        half-open bracket, a type clause, a set glyph, a set name, a
        brace set with members, a union or an exclusion can only be a
        domain. A bracket pair alone, `[0, 1]` or `(0, 1)`, is open (a
        two-item list or tuple, or an interval), and so is `{}`.
    """
    written = written.strip()
    if written in bound or term is None:
        return "value"
    if written in _EMPTY:
        return "open"
    if isinstance(term.bound, tuple) and not _TYPE_CLAUSE.search(mask_strings(written)[0]):
        piece = term.bound
        if getattr(piece, "closed_lo", True) == getattr(piece, "closed_hi", True):
            return "open"
    return "domain"


def _stated(term: Term, unicode: bool) -> str:
    """A side of `=` or `!=` as its canonical text there: a bracket
    pair carries the type clause that marks it a domain."""
    text = term.unicode if unicode else term.text
    bound = term.bound
    brackets = isinstance(bound, tuple) or (
        isinstance(bound, Domain) and bound.base_type == "R"
        and any(isinstance(p, tuple) for p in bound.pieces))
    return f"{text} : real" if brackets else text


def _relation(text: str, bound: frozenset = frozenset()) -> "Relation | tuple | None":
    """Intent:
        One relation between two domains read from `text`; the pair of
        relations a `⊊` stands for; or None when `text` is not a
        relation between two domains.

    Notes:
        Under `==` and `!=` each side is read first (`_reading`): a
        side that is a value makes the statement a comparison of
        values, which is not a relation between domains; a side that
        can only be a domain decides a bracket pair beside it; and two
        bracket pairs alone are refused, since the text does not say
        whether they are lists or intervals. `bound` holds the names
        the claim binds, which are values.

    Raises:
        InvalidDomainRelation: `⊂`, two relations in a row, or two
            domains of different kinds.
    """
    masked, literals = mask_strings(text.strip())
    negated = re.fullmatch(r"not\s*\((.*)\)", masked, flags=re.DOTALL)
    if negated is not None and _balanced(negated.group(1)):
        inner = _relation(unmask_strings(negated.group(1), literals))
        if isinstance(inner, Relation) and inner.word == "subset":
            return Relation(inner.left, "not subset", inner.right)
        return None
    found = _top_level(masked, _OPERATOR)
    if not found:
        return None
    first = found[0]
    left_written = unmask_strings(masked[:first.start()], literals)
    if left_written.strip() in bound:
        return None
    left = _term(left_written)
    if left is None:
        return None
    if len(found) > 1:
        whole = _term(unmask_strings(masked[first.end():], literals))
        last = _term(unmask_strings(masked[found[-1].end():], literals))
        if whole is None and last is None:
            return None
        raise InvalidDomainRelation(
            f"{text.strip()!r} holds more than one relation between two domains; "
            f"state one (an integer range is written `[0, 5] : int`)")
    right_written = unmask_strings(masked[first.end():], literals)
    if right_written.strip() in bound:
        return None
    right = _term(right_written)
    if right is None:
        return None
    spelling = re.sub(r"\s+", " ", first.group(0))
    if spelling in _EQUALITY:
        readings = (_reading(left_written, left, bound), _reading(right_written, right, bound))
        if "value" in readings:
            return None
        if left_written.strip() in _EMPTY and right_written.strip() in _EMPTY:
            readings = ("domain", "domain")
        if readings == ("open", "open"):
            sign = "!=" if spelling in ("!=", "≠") else "=="
            meant = Relation(left, "!=" if sign == "!=" else "=", right).text()
            meant = meant.replace(" = ", " == ", 1) if sign == "==" else meant
            raise InvalidDomainRelation(
                f"`{text.strip()}` reads two ways: two lists of two numbers, or two "
                f"intervals. Did you mean the intervals, `{meant}`? A bracket pair is "
                f"an interval where it carries a type clause (`: real`, `: int`) "
                f"and a list of values where the claim binds or calls beside it")
    if left.kind is not None and right.kind is not None and left.kind != right.kind:
        raise InvalidDomainRelation(
            f"a relation between domains compares two of one kind: "
            f"`{left.text}` is {left.kind} and `{right.text}` is {right.kind}")
    if spelling == "⊂":
        raise InvalidDomainRelation(
            f"`⊂` reads two ways: write `{left.text} subset {right.text}` for "
            f"every member of {left.text} is in {right.text}, equality "
            f"included, or `{left.text} subset {right.text} and {left.text} "
            f"!= {right.text}` for a proper subset")
    if spelling == "⊊":
        return (Relation(left, "subset", right), Relation(left, "!=", right))
    word, swapped = _SPELLINGS[spelling]
    return Relation(right, word, left) if swapped else Relation(left, word, right)


def parse(text: str, bound: frozenset = frozenset()) -> "Statement | None":
    """Intent:
        The relation between domains a normalized claim statement
        states, or None when it states something else.

    Raises:
        InvalidDomainRelation: the statement relates two domains in a
            way this grammar refuses; the message names the spelling
            to write.
    """
    masked, literals = mask_strings(text.strip())
    cuts = _top_level(masked, re.compile(r"(?<=\s)and(?=\s)"))
    if not cuts:
        read = _relation(text, bound)
        if read is None:
            return None
        return Statement(read if isinstance(read, tuple) else (read,))
    parts, start = [], 0
    for m in cuts:
        parts.append(unmask_strings(masked[start:m.start()], literals))
        start = m.end()
    parts.append(unmask_strings(masked[start:], literals))
    read = []
    for part in parts:
        one = _relation(part, bound)
        if not isinstance(one, Relation):
            return None
        read.append(one)
    proper = (len(read) == 2 and read[0].word == "subset" and read[1].word == "!="
              and (read[0].left.text, read[0].right.text)
              == (read[1].left.text, read[1].right.text))
    if not proper:
        raise InvalidDomainRelation(
            "the one conjunction of relations between domains is the proper "
            "subset, `A subset B and A != B`; state any other relation as a "
            "claim of its own")
    return Statement(tuple(read))


# ---- deciding ---------------------------------------------------------

def _value_set(bound):
    """The exact set a number domain denotes, or None when the domain
    has no exact real-set reading here (a complex region, a named set
    used as a union piece)."""
    if isinstance(bound, Domain):
        if bound.base_type not in ("R", "Z", "N"):
            return None
        if any(isinstance(p, str) for p in bound.pieces):
            return None
    try:
        return bound_to_sympy_set(bound)
    except (InvalidDomain, TypeError, ValueError):
        return None


def _candidates(s, depth: int = 0) -> list:
    """Numbers worth trying as a member of the sympy set `s`: the
    members of a finite set, an interval's ends, a point inside it and
    the whole numbers beside those, and the same for every part of a
    compound set."""
    import sympy
    out: list = []
    if depth > 6:
        return out
    if isinstance(s, sympy.FiniteSet):
        out.extend(sorted((a for a in s.args if a.is_number and a.is_real),
                          key=lambda a: a))
    elif isinstance(s, sympy.Interval):
        lo, hi = s.start, s.end
        if lo.is_finite and hi.is_finite:
            out.extend([hi, lo, (lo + hi) / 2])
        elif lo.is_finite:
            out.extend([lo, lo + 1])
        elif hi.is_finite:
            out.extend([hi, hi - 1])
        else:
            out.extend([sympy.Integer(0), sympy.Rational(1, 2)])
    elif isinstance(s, sympy.Range):
        for i, v in enumerate(s):
            out.append(sympy.Integer(v))
            if i >= 3:
                break
    elif s in (sympy.S.Integers, sympy.S.Naturals0, sympy.S.Naturals):
        out.extend([sympy.Integer(0), sympy.Integer(1), sympy.Integer(-1)])
    elif s is sympy.S.Reals:
        out.extend([sympy.Integer(0), sympy.Rational(1, 2), sympy.Integer(-1)])
    else:
        for arg in getattr(s, "args", ()):
            if isinstance(arg, sympy.Set):
                out.extend(_candidates(arg, depth + 1))
    wider: list = []
    for c in out:
        wider.append(c)
        if c.is_finite:
            for near in (sympy.floor(c), sympy.ceiling(c), sympy.floor(c) - 1,
                         sympy.ceiling(c) + 1, c + sympy.Rational(1, 2),
                         c - sympy.Rational(1, 2)):
                wider.append(near)
    return wider


def _python_number(value):
    """A sympy number as the Python number holding exactly that value,
    or None when no int or float does."""
    import sympy
    if value.is_Integer:
        return int(value)
    if value.is_Rational:
        as_float = float(Fraction(int(value.p), int(value.q)))
        return as_float if sympy.Rational(repr(as_float)) == value else None
    return None


def _number_text(value) -> str:
    return str(int(value)) if isinstance(value, int) or float(value).is_integer() \
        else repr(float(value))


def _member(s, inside: tuple, outside: tuple) -> "dict | None":
    """Intent:
        A member of the sympy set `s`, executed: a number the terms in
        `inside` hold and the terms in `outside` do not, each by its
        domain's own membership test. None when no candidate passes.
    """
    import sympy
    seen: set = set()
    for candidate in _candidates(s):
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            if s.contains(candidate) is not sympy.true:
                continue
        except TypeError:
            continue
        value = _python_number(candidate)
        if value is None:
            continue
        if all(domain_contains(value, t.bound) for t in inside) and \
                not any(domain_contains(value, t.bound) for t in outside):
            return {"value": _number_text(value), "in": [t.text for t in inside],
                    "not in": [t.text for t in outside], "executed": True}
    return None


def _settled(question) -> "bool | None":
    """The answer of an exact set question (a subset or disjointness
    test), or None when exact arithmetic does not settle it."""
    try:
        answer = question()
    except (TypeError, ValueError, NotImplementedError):
        return None
    return answer if isinstance(answer, bool) else None


def _said(witness: dict) -> str:
    said = f"{witness['value']} is in " + " and ".join(witness["in"])
    if witness["not in"]:
        said += " and not in " + " and ".join(witness["not in"])
    return said


def _finite(term: Term) -> "frozenset | None":
    return term.bound if isinstance(term.bound, frozenset) else None


def _decide_finite(rel: Relation) -> Decision:
    """A relation between two finite sets of any values, member by
    member."""
    a: frozenset = frozenset(rel.left.bound)  # type: ignore[call-overload]
    b: frozenset = frozenset(rel.right.bound)  # type: ignore[call-overload]

    def shown(v) -> str:
        return render_domain(frozenset({v}), show_missing=False, ascii_mode=True)[1:-1]

    def witness(values, inside, outside):
        v = sorted(values, key=repr)[0]
        return {"value": shown(v), "in": [t.text for t in inside],
                "not in": [t.text for t in outside], "executed": True}
    apart = {"subset": (a - b, (rel.left,), (rel.right,)),
             "not subset": (a - b, (rel.left,), (rel.right,)),
             "disjoint": (a & b, (rel.left, rel.right), ())}
    if rel.word in apart:
        values, inside, outside = apart[rel.word]
    elif a - b:
        values, inside, outside = a - b, (rel.left,), (rel.right,)
    else:
        values, inside, outside = b - a, (rel.right,), (rel.left,)
    return _from_counter_set(rel, not values,
                             witness(values, inside, outside) if values else None)


def _from_counter_set(rel: Relation, empty: "bool | None",
                      witness: "dict | None") -> Decision:
    """Intent:
        The decision for `rel` from the set that separates its two
        domains (the members of the left outside the right for a
        subset, of either outside the other for an equality, of both
        for a disjointness): whether that set is `empty`, and an
        executed member of it when one was found.
    """
    negative = rel.word in ("not subset", "!=")
    if witness is not None:
        if negative:
            return Decision("proven", _said(witness), witness)
        return Decision("falsified", _said(witness), witness)
    if empty is True:
        nothing = {"subset": f"no member of {rel.left.text} is outside {rel.right.text}",
                   "not subset": f"every member of {rel.left.text} is in {rel.right.text}",
                   "=": f"{rel.left.text} and {rel.right.text} hold the same members",
                   "!=": f"{rel.left.text} and {rel.right.text} hold the same members",
                   "disjoint": f"{rel.left.text} and {rel.right.text} share no member"}
        return Decision("falsified" if negative else "proven", nothing[rel.word])
    return Decision("unknown", _UNSETTLED)


UNCONFIRMED = ("the solver found a string the languages' own membership does "
               "not confirm, so their definitions decide nothing here")


@dataclass(frozen=True)
class _Defined:
    """A language domain read from its regular-language definitions:
    `at_most` (a node holding only members), `at_least` (a node holding
    every member), the alphabet they are over, and the hash of each
    definition read, by the text of the piece stating it."""
    at_most: dict
    at_least: dict
    alphabet: list
    hashes: dict
    #: each language piece read: `(text, language, at_most, at_least)`
    read: tuple = ()
    #: the strings the domain writes out: its listed members and the
    #: strings it excludes
    literals: tuple = ()


def _literals(values) -> "dict | None":
    """The node holding exactly the strings in `values`, or None when a
    value is not a string."""
    if not all(isinstance(v, str) for v in values):
        return None
    if not values:
        return {"op": "empty"}
    return {"op": "union", "args": [{"op": "literal", "codes": [ord(c) for c in v]}
                                    for v in sorted(values)] + [{"op": "empty"}]}


def _defined(term: Term) -> "_Defined | None":
    return defined_bound(term.bound)


def defined_bound(bound) -> "_Defined | None":
    """Intent:
        The domain `bound` as regular-language nodes, or None when a
        piece states no definition: a language piece gives the
        definition its persisted form carries, a finite set of strings
        the union of its members, a union of pieces their union, and an
        exclusion the strings it removes.
    """
    from . import regular
    from .languages import resolve_language
    if isinstance(bound, LanguageRef):
        bound = Domain(base_type="L", pieces=(bound,))
    if not isinstance(bound, (frozenset, Domain)):
        return None
    pieces = (bound,) if isinstance(bound, frozenset) else tuple(bound.pieces)
    excluded = frozenset() if isinstance(bound, frozenset) else bound.excluded
    most: list = []
    least: list = []
    alphabet: list = []
    hashes: dict = {}
    read: list = []
    written: dict = {v: None for v in excluded if isinstance(v, str)}
    for piece in pieces:
        if isinstance(piece, frozenset):
            node = _literals(piece)
            if node is None:
                return None
            most.append(node)
            least.append(node)
            written.update((v, None) for v in sorted(piece))
            # a listed string is a member whatever alphabet a language
            # beside it states, so its characters join the question's
            alphabet.extend([ord(c), ord(c)] for v in piece for c in v)
            continue
        if not isinstance(piece, LanguageRef):
            return None
        try:
            document = resolve_language(piece).to_json().get("definition")
            language = resolve_language(piece)
            piece_most, piece_least = regular.bounds(document)
            alphabet.extend(regular.alphabet_of(document))
            hashes[repr(piece)] = regular.term_hash(document)
            read.append((repr(piece), language, piece_most, piece_least))
        except Exception:
            return None
        most.append(piece_most)
        least.append(piece_least)
    removed = _literals(excluded)
    if removed is None or not pieces:
        return None
    alphabet.extend([ord(c), ord(c)] for v in excluded for c in v)

    def joined(nodes):
        node = {"op": "union", "args": nodes + [{"op": "empty"}]}
        if excluded:
            node = {"op": "inter", "args": [node, {"op": "complement", "arg": removed}]}
        return node
    return _Defined(joined(most), joined(least), alphabet, hashes, tuple(read),
                    tuple(written))


#: how many values a guard draws from a language's own sampler
GUARD_DRAWS = 48
#: how many strings over one character per atom a guard enumerates at
#: most; the length bound is the longest whose strings all fit
GUARD_ENUMERATED = 3000
#: the characters a guard also tries every string of up to two of: the
#: printable ASCII characters, a tab and a newline
GUARD_CHARACTERS = "".join(chr(c) for c in range(0x20, 0x7F)) + "\t\n"
#: how many drawn members a guard takes near misses of
GUARD_NEAR_MISSES = 12
#: how many skipped strings a guard's artefact names
GUARD_SKIPPED_SHOWN = 8


def _guard_seed(text: str) -> int:
    """The seed a guard draws with for a language: fixed by the
    language's text, so the same check can be run again."""
    import hashlib
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _guard_strings(language, at_most: dict, at_least: dict, alphabet: list,
                   seed: int, literals: tuple = ()) -> tuple:
    """Intent:
        The strings a definition is compared with its language on, and
        what was enumerated: every string up to a length bound over one
        character per atom of the definition's character sets; every
        string of up to two of `GUARD_CHARACTERS`; the language's
        hazards and the values its sampler draws; and, for the shortest
        drawn members, each with one character removed, and with one
        atom character put in or put in place of a character, at every
        position; then the `literals` the claim writes. Returns
        `(strings, members drawn, length bound, atoms)`. Nothing here asks a solver, so the same call gives the
        same strings on any machine.
    """
    import itertools
    import random

    from . import regular
    atoms = regular.representatives([at_most, at_least], alphabet or None)
    bound, total = 0, 1
    while atoms and bound < 6 and total + len(atoms) ** (bound + 1) <= GUARD_ENUMERATED:
        bound += 1
        total += len(atoms) ** bound
    strings: dict = {}
    for n in range(bound + 1):
        for letters in itertools.product(atoms, repeat=n):
            strings["".join(letters)] = None
    for n in (1, 2):
        for letters in itertools.product(GUARD_CHARACTERS, repeat=n):
            strings["".join(letters)] = None
    rng = random.Random(seed)
    drawn: list = []
    try:
        drawn.extend(h.value for h in language.hazards())
    except Exception:
        pass
    for _ in range(GUARD_DRAWS):
        try:
            drawn.append(language.sample(rng))
        except Exception:
            break
    drawn = [v for v in drawn if isinstance(v, str)]
    members = sorted({v for v in drawn if _is_member(language, v)}, key=lambda v: (len(v), v))
    for value in drawn:
        strings[value] = None
    for value in members[:GUARD_NEAR_MISSES]:
        for i in range(len(value) + 1):
            if i < len(value):
                strings[value[:i] + value[i + 1:]] = None
            for letter in atoms:
                strings[value[:i] + letter + value[i:]] = None
                if i < len(value):
                    strings[value[:i] + letter + value[i + 1:]] = None
    strings.update((v, None) for v in literals if isinstance(v, str))
    return list(strings), len(members), bound, len(atoms)


def check_definition(text: str, language, at_most: dict, at_least: dict,
                     alphabet: list, literals: tuple = ()) -> dict:
    """Intent:
        Check a language's stated definition against the language's own
        membership on a fixed set of strings (`_guard_strings`, with
        the `literals` the claim writes among them): a
        string the term `at_most` holds must be a member by `contains`,
        and a member must be held by `at_least`, each term read by the
        derivative matcher. For an exact definition the two are one
        term, so the term and `contains` must agree on every string;
        for a pair the membership must lie between them. Returns the
        assumption a verdict rests on: the `statement` (`<text> == its
        stated definition`), its `status`, and the `artefact` to run it
        again (the seed, the members drawn, the length bound, the
        number of atoms, the number of strings compared and skipped,
        and the first `GUARD_SKIPPED_SHOWN` skipped strings).

        A string on which `contains` raises is skipped: the definition
        is not compared there. The status is `checked` when every
        string was compared and agreed; `assumed` when a string was
        skipped or none was compared; and `refuted`, with the
        `disagreement` naming the string, when the definition and the
        membership part. When the matcher runs out of its budget the
        result carries `unfinished` and no status is claimed.
    """
    from . import regular
    seed = _guard_seed(text)
    out = {"language": text, "statement": f"{text} == its stated definition",
           "status": "assumed", "artefact": {"seed": seed}}
    strings, drawn, bound, atoms = _guard_strings(language, at_most, at_least, alphabet,
                                                  seed, literals)
    in_most, in_least = regular.matcher(at_most), regular.matcher(at_least)
    compared = 0
    skipped: list = []
    try:
        for value in strings:
            try:
                is_member = bool(language.contains(value))
            except Exception:
                skipped.append(value)
                continue
            compared += 1
            if is_member and not in_least(value):
                return {**out, "status": "refuted",
                        "disagreement": f"{value!r} is a member of {text} and is "
                                        f"outside its stated definition"}
            if not is_member and in_most(value):
                return {**out, "status": "refuted",
                        "disagreement": f"{value!r} is in the stated definition of "
                                        f"{text} and is not a member"}
    except regular.MatchBudget:
        return {**out, "unfinished": f"the check of the definition of {text} did not finish"}
    out["artefact"].update({"members drawn": drawn, "length bound": bound, "atoms": atoms,
                            "strings compared": compared, "strings skipped": len(skipped),
                            "skipped": [repr(v) for v in skipped[:GUARD_SKIPPED_SHOWN]]})
    if compared and not skipped:
        out["status"] = "checked"
    return out


def _is_member(language, value) -> bool:
    try:
        return bool(language.contains(value))
    except Exception:
        return False


def check_definitions(*defined: "_Defined", literals: tuple = ()) -> tuple:
    """`(assumptions, disagreement)` for every language piece the given
    domains read, each checked once, on the strings every given domain
    writes and the `literals` besides: the assumptions as
    `check_definition` returns them, and the first disagreement found
    (a sentence) or None."""
    written = tuple(dict.fromkeys([*literals, *(v for d in defined for v in d.literals)]))
    seen: dict = {}
    for domain in defined:
        for text, language, most, least in domain.read:
            if text not in seen:
                seen[text] = check_definition(text, language, most, least, domain.alphabet,
                                              written)
    refuted = next((a.get("disagreement") or a.get("unfinished") for a in seen.values()
                    if a["status"] == "refuted" or a.get("unfinished")), None)
    return list(seen.values()), refuted


def standard_assumptions() -> dict:
    """The assumptions every proof on the solver route rests on, named
    once with their versions: the solver's answer and the canonical
    form of a regular-language term."""
    from . import regular
    try:
        import z3
        solver = z3.get_version_string()
    except ImportError:
        solver = None
    return {"z3": {"statement": "z3 answers 'no string exists' only when none does",
                   "version": solver, "status": "assumed"},
            "canonical form": {"statement": "the canonical form of a term holds the "
                                            "strings the term holds",
                               "version": f"{regular.KIND} {regular.VERSION}",
                               "status": "assumed"}}


def assuming_text(assumptions: list, verdict: str = "proven") -> str:
    """`proven, assuming A (checked), B (assumed)` for the definitions a
    verdict rests on (`falsified, assuming ...` for a falsified one);
    the verdict word alone when it read none."""
    if not assumptions:
        return verdict
    return f"{verdict}, assuming " + ", ".join(
        f"{a['statement']} ({a['status']})" for a in assumptions)


def _decide_languages(rel: Relation) -> Decision:
    """Intent:
        Decide a relation where a side is a language, from the
        regular-language definitions the two sides state. No string in
        the separating set of the wider bounds is a proof. A string the
        solver finds counts only once both domains' own membership
        confirms it. `unknown` when a side states no definition, the
        bounds are too wide to decide, or the solver gives no answer.
    """
    from . import regular
    left, right = _defined(rel.left), _defined(rel.right)
    if left is None or right is None:
        return Decision("unknown", NO_LOWERING)
    definitions = {**left.hashes, **right.hashes}
    alphabet = left.alphabet + right.alphabet

    def separating(a: _Defined, b: _Defined, a_term: Term, b_term: Term):
        # (inside, outside) over the wider bounds, then over the narrower
        return ((([a.at_least], [b.at_most]), ([a.at_most], [b.at_least])),
                (a_term,), (b_term,))
    if rel.word in ("subset", "not subset"):
        parts = [separating(left, right, rel.left, rel.right)]
    elif rel.word == "disjoint":
        parts = [((([left.at_least, right.at_least], []), ([left.at_most, right.at_most], [])),
                  (rel.left, rel.right), ())]
    else:
        parts = [separating(left, right, rel.left, rel.right),
                 separating(right, left, rel.right, rel.left)]
    empty, why = True, ""
    for (wide, narrow), inside, outside in parts:
        found = regular.find_member(alphabet, *wide)
        if found.status == "none":
            continue
        empty = None
        for question in (wide, narrow):
            if question is narrow:
                found = regular.find_member(alphabet, *narrow)
            if found.status == "unknown":
                why = why or found.reason
            if found.status != "member":
                continue
            member = found.member
            if not regular.places(member, *question):
                # the matcher reads the solver's string otherwise than
                # the solver did, so the string settles nothing
                why = why or UNCONFIRMED
                continue
            if all(domain_contains(member, t.bound) for t in inside) and \
                    not any(domain_contains(member, t.bound) for t in outside):
                witness = {"value": repr(member), "member": member,
                           "in": [t.text for t in inside],
                           "not in": [t.text for t in outside], "executed": True}
                decided = _from_counter_set(rel, False, witness)
                return Decision(decided.verdict, decided.reason, witness, "smt", definitions)
            why = why or UNCONFIRMED
    if empty is True:
        # the answer "no string separates them" rests on the definitions,
        # so each is checked against its language's own membership first
        assumptions, refuted = check_definitions(left, right)
        if refuted is not None:
            return Decision("unknown", f"{refuted}, so the definitions decide nothing here",
                            None, "smt", definitions)
        decided = _from_counter_set(rel, True, None)
        return Decision(decided.verdict, decided.reason, None, "smt", definitions,
                        assumptions)
    return Decision("unknown", why or UNCONFIRMED, None, "smt", definitions)


def decide_relation(rel: Relation) -> Decision:
    """Intent:
        Decide one relation between two domains: exactly for two number
        domains or two finite sets, `unknown` with the reason for a
        relation over a language.
    """
    if LANGUAGE in (rel.left.kind, rel.right.kind):
        if _finite(rel.left) is not None and _finite(rel.right) is not None:
            return _decide_finite(rel)
        return _decide_languages(rel)
    if _finite(rel.left) is not None and _finite(rel.right) is not None:
        return _decide_finite(rel)
    try:
        decided = _decide_number_sets(rel)
    except Exception as e:
        return Decision("unknown", f"{_UNSETTLED} ({type(e).__name__})")
    # a member found among the finite numbers settles the relation
    # whatever an infinity does; only the answer "no finite number
    # separates them" is put in doubt by an infinity that does
    none_found = decided.witness is None and decided.verdict in ("proven", "falsified")
    apart = _infinity_apart(rel) if none_found else None
    return Decision("unknown", apart) if apart is not None else decided


def _infinity_apart(rel: Relation) -> "str | None":
    """Intent:
        Why a relation between number domains is not decided on the
        sets they denote, or None: an infinity is a member of one side
        by the domain's own membership test in a way that bears on the
        relation (in the left and not the right, in both for a
        disjointness, in exactly one for an equality), while the sets
        compared hold only finite numbers.
    """
    for value, said in ((float("inf"), "inf"), (float("-inf"), "-inf")):
        try:
            left = domain_contains(value, rel.left.bound)
            right = domain_contains(value, rel.right.bound)
        except Exception:
            continue
        bears = {"subset": left and not right, "not subset": left and not right,
                 "disjoint": left and right, "=": left != right, "!=": left != right}
        if bears[rel.word]:
            return (f"the infinity {said} is a member of "
                    f"{rel.left.text if left else rel.right.text} by its membership test, "
                    f"which the comparison of the sets of finite numbers does not hold")
    return None


def _decide_number_sets(rel: Relation) -> Decision:
    """The decision of a relation between two number domains on the
    exact sets they denote."""
    import sympy
    a, b = _value_set(rel.left.bound), _value_set(rel.right.bound)
    if a is None or b is None:
        return Decision("unknown", _UNSETTLED)
    left_outside = (sympy.Complement(a, b, evaluate=True), (rel.left,), (rel.right,),
                    lambda: a.is_subset(b))
    right_outside = (sympy.Complement(b, a, evaluate=True), (rel.right,), (rel.left,),
                     lambda: b.is_subset(a))
    shared = (sympy.Intersection(a, b), (rel.left, rel.right), (),
              lambda: a.is_disjoint(b))
    parts: list
    if rel.word in ("subset", "not subset"):
        parts = [left_outside]
    elif rel.word == "disjoint":
        parts = [shared]
    else:
        parts = [left_outside, right_outside]
    empties = []
    for counter, inside, outside, is_empty in parts:
        witness = _member(counter, inside, outside)
        if witness is not None:
            return _from_counter_set(rel, False, witness)
        empties.append(counter is sympy.S.EmptySet or _settled(is_empty))
    return _from_counter_set(rel, True if all(e is True for e in empties) else None, None)


def decide(statement: Statement, written: "str | None" = None) -> Decision:
    """Intent:
        Decide a statement: its one relation, or, for a proper subset,
        both of its relations (falsified when either is, proven when
        both are, the witness of the inequality kept). `written` is the
        statement as its author wrote it; a relation between number
        domains whose written numbers the domains do not hold exactly
        (`not_as_written`) is not decided.
    """
    numbers = any(NUMBERS in (r.left.kind, r.right.kind) for r in statement.relations)
    inexact = not_as_written(written) if written and numbers else None
    if inexact is not None:
        return Decision("unknown", inexact)
    decisions = [decide_relation(r) for r in statement.relations]
    for d in decisions:
        if d.verdict == "falsified":
            return d
    for d in decisions:
        if d.verdict == "unknown":
            return d
    if len(decisions) == 1:
        return decisions[0]
    witness = next((d.witness for d in decisions if d.witness), None)
    definitions = {k: v for d in decisions for k, v in (d.definitions or {}).items()}
    assumptions = [a for d in decisions for a in (d.assumptions or [])]
    return Decision("proven", "; ".join(d.reason for d in decisions), witness,
                    decisions[0].route, definitions or None, assumptions or None)


def parameter_named_as_a_set(statement: Statement, written: str, parameters) -> "str | None":
    """Intent:
        Why a relation under `=` or `!=` cannot be read over a function
        with these parameters, or None: a side written as a set name
        (`Z`) is also one of the function's parameters, so the text
        does not say whether the inputs or the sets are compared. The
        message offers both spellings. A side written as a glyph (`ℤ`)
        is the set.
    """
    glyphs = {"R": "ℝ", "Z": "ℤ", "N": "ℕ", "Q": "ℚ", "C": "ℂ"}
    for rel in statement.relations:
        if rel.word not in ("=", "!="):
            continue
        clash = [t.text for t in (rel.left, rel.right)
                 if t.text in _SET_NAMES and t.text in parameters
                 and glyphs[t.text] not in written]
        if clash:
            name = clash[0]
            sets = rel.text(unicode=True)
            return (f"`{rel.text()}`: {name} is a parameter of the function and also "
                    f"names a set. To compare the inputs, bind them, `for {name} in "
                    f"..., {rel.text()}`; to relate the sets, write the glyphs, `{sets}`")
    return None


__all__ = ["Decision", "InvalidDomainRelation", "LANGUAGE", "NO_LOWERING", "NUMBERS",
           "RELATION", "Relation", "Statement", "Term", "WORDS", "assuming_text",
           "check_definition", "check_definitions", "decide", "not_as_written",
           "standard_assumptions",
           "decide_relation", "parse"]
