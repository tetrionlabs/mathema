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
        if unicode:
            return f"{self.left.unicode} {WORDS[self.word]} {self.right.unicode}"
        return f"{self.left.text} {self.word} {self.right.text}"


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


def _bare_name(written: str) -> bool:
    """Whether a side is written as an ascii name (`Z`, `N`), which is
    also how a parameter is written."""
    return bool(re.fullmatch(r"[A-Za-z_]\w*", written.strip()))


def _relation(text: str, names: bool = False) -> "Relation | tuple | None":
    """Intent:
        One relation between two domains read from `text`; the pair of
        relations a `⊊` stands for; or None when `text` is not a
        relation between two domains.

    Notes:
        Two ascii names under `=` or `!=` (`N == Z`) are two values
        compared, not two domains, unless `names` is set.

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
    left = _term(unmask_strings(masked[:first.start()], literals))
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
    right = _term(unmask_strings(masked[first.end():], literals))
    if right is None:
        return None
    spelling = re.sub(r"\s+", " ", first.group(0))
    if not names and spelling in ("==", "=", "!=", "≠") \
            and _bare_name(masked[:first.start()]) and _bare_name(masked[first.end():]):
        return None
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


def parse(text: str) -> "Statement | None":
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
        read = _relation(text)
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
        one = _relation(part, names=bool(read))
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


def _literals(values) -> "dict | None":
    """The node holding exactly the strings in `values`, or None when a
    value is not a string."""
    if not all(isinstance(v, str) for v in values):
        return None
    if not values:
        return {"op": "empty"}
    return {"op": "union", "args": [{"op": "literal", "text": v}
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
    most, least, alphabet, hashes = [], [], [], {}
    for piece in pieces:
        if isinstance(piece, frozenset):
            node = _literals(piece)
            if node is None:
                return None
            most.append(node)
            least.append(node)
            continue
        if not isinstance(piece, LanguageRef):
            return None
        try:
            document = resolve_language(piece).to_json().get("definition")
            piece_most, piece_least = regular.bounds(document)
            alphabet.extend(regular.alphabet_of(document))
            hashes[repr(piece)] = regular.term_hash(document)
        except Exception:
            return None
        most.append(piece_most)
        least.append(piece_least)
    removed = _literals(excluded)
    if removed is None or not pieces:
        return None

    def joined(nodes):
        node = {"op": "union", "args": nodes + [{"op": "empty"}]}
        if excluded:
            node = {"op": "inter", "args": [node, {"op": "complement", "arg": removed}]}
        return node
    return _Defined(joined(most), joined(least),
                    alphabet or [[0, regular.MAX_CODE_POINT]], hashes)


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
            if all(domain_contains(member, t.bound) for t in inside) and \
                    not any(domain_contains(member, t.bound) for t in outside):
                witness = {"value": repr(member), "member": member,
                           "in": [t.text for t in inside],
                           "not in": [t.text for t in outside], "executed": True}
                decided = _from_counter_set(rel, False, witness)
                return Decision(decided.verdict, decided.reason, witness, "smt", definitions)
            why = why or UNCONFIRMED
    if empty is True:
        decided = _from_counter_set(rel, True, None)
        return Decision(decided.verdict, decided.reason, None, "smt", definitions)
    return Decision("unknown", why or UNCONFIRMED, None, "smt", definitions)


def decide_relation(rel: Relation) -> Decision:
    """Intent:
        Decide one relation between two domains: exactly for two number
        domains or two finite sets, `unknown` with the reason for a
        relation over a language.
    """
    import sympy
    if _finite(rel.left) is not None and _finite(rel.right) is not None:
        return _decide_finite(rel)
    if LANGUAGE in (rel.left.kind, rel.right.kind):
        return _decide_languages(rel)
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


def decide(statement: Statement) -> Decision:
    """Intent:
        Decide a statement: its one relation, or, for a proper subset,
        both of its relations (falsified when either is, proven when
        both are, the witness of the inequality kept).
    """
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
    return Decision("proven", "; ".join(d.reason for d in decisions), witness,
                    decisions[0].route, definitions or None)


__all__ = ["Decision", "InvalidDomainRelation", "LANGUAGE", "NO_LOWERING", "NUMBERS",
           "RELATION", "Relation", "Statement", "Term", "WORDS", "decide",
           "decide_relation", "parse"]
