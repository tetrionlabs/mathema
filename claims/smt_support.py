# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about `mathema.regular`, `mathema._validators`
and `mathema.domain_relations` are stated over: each takes numbers or
text a claim can quantify, builds the documents, functions or domain
texts the module under claim reads, and returns a value a claim can
compare.

`regular.py` and `_validators.py` import nothing from the rest of the
package, so they are loaded here from their files, under names of their
own: the claims over them can then be checked by any installed mathema,
a released one included, against the files in this tree."""
from __future__ import annotations

import importlib.util
import re
import sys
from fractions import Fraction
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent.parent / "mathema"


def _load(name: str):
    """The module in the file `mathema/<name>.py` of this tree, loaded
    once under the name `candidate_<name>`."""
    key = f"candidate_{name.lstrip('_')}"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, _PACKAGE / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


ALL = [[0, 0x10FFFF]]


def _document(node: dict, source: "dict | None" = None) -> dict:
    document = {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
                "language": node}
    if source is not None:
        document["source"] = source
    return document


def _span(lo: int, width: int) -> dict:
    return {"op": "chars", "ranges": [[int(lo), int(lo) + width]]}


# ---- mathema.regular --------------------------------------------------

def literal_hash(text: str, note: str) -> str:
    """The hash of the definition holding exactly `text`, compiled from
    a source described by `note`."""
    return _load("regular").term_hash(
        _document({"op": "literal", "text": text}, {"dialect": "by hand", "pattern": note}))


def canonical_twice_is_canonical(a: int, b: int, shape: int) -> bool:
    """Whether the canonical form of a nested node built from the code
    points `a` and `b` is its own canonical form. `shape` picks the
    nesting."""
    regular = _load("regular")
    lo, hi = sorted((int(a), int(b)))
    chars = {"op": "chars", "ranges": [[hi, hi], [lo, hi]]}
    letter = {"op": "literal", "text": chr(lo)}
    nodes = [
        {"op": "concat", "args": [letter, {"op": "concat", "args": [chars, {"op": "epsilon"}]}]},
        {"op": "union", "args": [chars, {"op": "union", "args": [letter, chars]}]},
        {"op": "inter", "args": [{"op": "repeat", "arg": chars, "min": 0, "max": None},
                                 {"op": "complement", "arg": letter}]},
        {"op": "concat", "args": [letter, {"op": "empty"}]},
    ]
    once = regular.canonical(nodes[int(shape) % len(nodes)])
    return regular.canonical(once) == once


def separating_status(a: int, b: int) -> str:
    """`member` or `none`: whether some one-character string lies in
    the code points `a` to `a + 3` and outside `b` to `b + 10`."""
    found = _load("regular").find_member(ALL, inside=[_span(a, 3)], outside=[_span(b, 10)])
    return found.status


def span_inside(a: int, b: int) -> str:
    """`none` when every whole number from `a` to `a + 3` lies in `b`
    to `b + 10`, else `member`, by arithmetic on the endpoints."""
    return "none" if int(b) <= int(a) and int(a) + 3 <= int(b) + 10 else "member"


def member_found_separates(a: int, b: int) -> bool:
    """Whether the string the solver returns for the question of
    `separating_status`, when it returns one, is one character in `a`
    to `a + 3` and outside `b` to `b + 10`."""
    found = _load("regular").find_member(ALL, inside=[_span(a, 3)], outside=[_span(b, 10)])
    if found.status != "member":
        return found.status == "none"
    code = ord(found.member) if len(found.member) == 1 else -1
    return int(a) <= code <= int(a) + 3 and not int(b) <= code <= int(b) + 10


# ---- mathema._validators ----------------------------------------------

_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*$")
_SLUG_FIXED = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


class _Lookalike:
    def fullmatch(self, text):
        return text == "ok"


_FAKE = _Lookalike()


def _refuses_dollar(text):
    if not _SLUG.match(text):
        raise ValueError(text)
    return text


def _refuses_fixed(text):
    if _SLUG_FIXED.fullmatch(text) is None:
        raise ValueError(text)
    return text


def _predicate_search(text):
    return bool(_SLUG.search(text))


def _predicate_negated(text):
    return _SLUG_FIXED.fullmatch(text) is None


def _inline(text):
    return re.fullmatch(r"[a-z]+", text, re.IGNORECASE) is not None


def _by_lookalike(text):
    return bool(_FAKE.fullmatch(text))


def _shadowed(re):  # noqa: A002
    return bool(re.fullmatch("a", re))


def _strips(text):
    return bool(_SLUG.fullmatch(text.strip()))


def _lowers(text):
    if not _SLUG.match(text):
        raise ValueError(text)
    return text.lower()


VALIDATORS = (_refuses_dollar, _refuses_fixed, _predicate_search, _predicate_negated, _inline)
NOT_VALIDATORS = (_by_lookalike, _shadowed, _strips, _lowers)
TEXTS = ("", "a", "a-b", "ab\n", "-a", "A", "a b", "9", "a\n\n", "Zz")


def reading_agrees_with_the_function(which: int, text_index: int) -> bool:
    """Whether the validator read from the function `VALIDATORS[which]`
    accepts `TEXTS[text_index]` exactly when the function itself does:
    a refusing validator returns it, a predicate returns True (False
    for a negated one)."""
    fn, text = VALIDATORS[int(which)], TEXTS[int(text_index)]
    read = _load("_validators").read_validator(fn)
    if isinstance(read, str):
        return False
    matched = read.accepts(text) is not None
    try:
        returned = fn(text)
    except ValueError:
        return read.raises is ValueError and not matched
    if read.raises is not None:
        return matched and returned == text
    return returned is (matched != read.negated)


def function_accepts(which: int, text_index: int) -> bool:
    """Whether the function `VALIDATORS[which]` accepts
    `TEXTS[text_index]`: returns it, or returns True."""
    try:
        returned = VALIDATORS[int(which)](TEXTS[int(text_index)])
    except ValueError:
        return False
    return returned is not False


def is_declined(which: int) -> bool:
    """Whether `NOT_VALIDATORS[which]` is declined, with a reason."""
    return isinstance(_load("_validators").read_validator(NOT_VALIDATORS[int(which)]), str)


# ---- mathema.domain_relations -----------------------------------------

RELATIONS = ("subset", "not subset", "=", "!=", "disjoint")


def interval_statement(relation: int, a: int, b: int, c: int, d: int) -> str:
    """`[a, b] <relation> [c, d]`, the equalities with the type clause
    that marks a bracket pair a domain."""
    word = RELATIONS[int(relation)]
    clause = " : real" if word in ("=", "!=") else ""
    return f"[{int(a)}, {int(b)}]{clause} {word} [{int(c)}, {int(d)}]{clause}"


def interval_verdict(relation: int, a: int, b: int, c: int, d: int) -> str:
    """The verdict `mathema.domain_relations` gives the statement."""
    from mathema import domain_relations
    stated = domain_relations.parse(interval_statement(relation, a, b, c, d))
    return domain_relations.decide(stated).verdict


def interval_truth(relation: int, a: int, b: int, c: int, d: int) -> str:
    """`proven` or `falsified` for the same statement, by testing every
    quarter step from -1 to 8 against the endpoints: between whole
    endpoints that settles every relation of two closed intervals."""
    points = [Fraction(n, 4) for n in range(-4, 33)]
    left = {p for p in points if a <= p <= b}
    right = {p for p in points if c <= p <= d}
    holds = {"subset": left <= right, "not subset": not left <= right, "=": left == right,
             "!=": left != right, "disjoint": not left & right}[RELATIONS[int(relation)]]
    return "proven" if holds else "falsified"


def interval_text_is_stable(relation: int, a: int, b: int, c: int, d: int) -> bool:
    """Whether the canonical text of the statement reads back as the
    same canonical text."""
    from mathema import domain_relations
    once = domain_relations.parse(interval_statement(relation, a, b, c, d)).text()
    return domain_relations.parse(once).text() == once
