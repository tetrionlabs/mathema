# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A regular language written as KOINE terms, one head for each node
of a regular-language definition (`mathema.regular`).

Draft, not part of the public interface: the heads are named, the
shape of their arguments is provisional.

    language::empty                          no text
    language::epsilon                        the empty text alone
    language::literal([c, ...])              the one text of these code points
    language::characters([[lo, hi], ...])    one character from inclusive
                                             code point ranges
    language::concatenation(n, ...)          a text of each, in order
    language::union(n, ...)                  a text of any
    language::intersection(n, ...)           a text of every one
    language::complement(n)                  every text outside n
    language::repetition::bounded(n, min, max)
                                             min to max texts of n, joined
    language::repetition::unbounded(n, min)  min or more texts of n, joined
    language::regular::exact(n, alphabet::codepoints)
                                             the language of n over every
                                             code point

Each node term is the node of `mathema.regular` of the operation
`empty`, `epsilon`, `literal`, `chars`, `concat`, `union`, `inter`,
`complement` and `repeat` (`max` null for the unbounded head).
`from_node` and `to_node` map one onto the other argument for
argument, rewriting nothing, so a term states exactly the language its
node states and `regular.canonical` and `regular.term_hash` apply to
it through its node.

`operator::membership::in_language(e, language::regular::exact(n,
alphabet::codepoints))` is true exactly when the text `e` is in the
language of `n`, read over all code points as `regular.node_member`
reads a bare node.
"""
from __future__ import annotations

from .syntax import Int, List, Term

EMPTY = "language::empty"
EPSILON = "language::epsilon"
LITERAL = "language::literal"
CHARACTERS = "language::characters"
CONCATENATION = "language::concatenation"
UNION = "language::union"
INTERSECTION = "language::intersection"
COMPLEMENT = "language::complement"
REPETITION_BOUNDED = "language::repetition::bounded"
REPETITION_UNBOUNDED = "language::repetition::unbounded"
EXACT = "language::regular::exact"
ALPHABET_CODEPOINTS = "alphabet::codepoints"
IN_LANGUAGE = "operator::membership::in_language"

#: the heads of the three operations that take any number of nodes
_MANY = {CONCATENATION: "concat", UNION: "union", INTERSECTION: "inter"}
_MANY_HEAD = {op: head for head, op in _MANY.items()}
NODE_HEADS = frozenset({EMPTY, EPSILON, LITERAL, CHARACTERS, COMPLEMENT, REPETITION_BOUNDED,
                        REPETITION_UNBOUNDED, *_MANY})
HEADS = NODE_HEADS | {EXACT, ALPHABET_CODEPOINTS, IN_LANGUAGE}


class InvalidLanguageTerm(ValueError):
    """A term that is not a regular language written with the heads of
    this module, or a node `mathema.regular` does not define."""


def _whole(value, where: str) -> int:
    if not isinstance(value, Int):
        raise InvalidLanguageTerm(f"{where}: expected a whole number, got {value!r}")
    return value.value


def _shape(term, count: "int | None", where: str) -> tuple:
    """The positional arguments of a term that takes `count` of them
    (any number for None) and none by name."""
    if term.named:
        raise InvalidLanguageTerm(f"{where}: {term.head} takes no named argument")
    if count is not None and len(term.args) != count:
        raise InvalidLanguageTerm(f"{where}: {term.head} takes {count} argument(s), "
                                  f"got {len(term.args)}")
    return term.args


def to_node(term, where: str = "language") -> dict:
    """Intent:
        The regular-language node a `language::` node term states,
        argument for argument, with nothing rewritten.

    Raises:
        InvalidLanguageTerm: the term is not a node term of this
            module's shapes.
    """
    if not isinstance(term, Term) or term.head not in NODE_HEADS:
        raise InvalidLanguageTerm(f"{where}: not a language:: node term: {term!r}")
    head = term.head
    if head in (EMPTY, EPSILON):
        _shape(term, 0, where)
        return {"op": "empty" if head == EMPTY else "epsilon"}
    if head == LITERAL:
        (codes,) = _shape(term, 1, where)
        if not isinstance(codes, List):
            raise InvalidLanguageTerm(f"{where}: {head} takes a list of code points")
        return {"op": "literal", "codes": [_whole(c, where) for c in codes.items]}
    if head == CHARACTERS:
        (ranges,) = _shape(term, 1, where)
        if not isinstance(ranges, List) or not all(
                isinstance(r, List) and len(r.items) == 2 for r in ranges.items):
            raise InvalidLanguageTerm(f"{where}: {head} takes a list of [lo, hi] pairs")
        return {"op": "chars",
                "ranges": [[_whole(r.items[0], where), _whole(r.items[1], where)]
                           for r in ranges.items]}
    if head in _MANY:
        return {"op": _MANY[head],
                "args": [to_node(a, f"{where}.arg[{i}]")
                         for i, a in enumerate(_shape(term, None, where))]}
    if head == COMPLEMENT:
        (arg,) = _shape(term, 1, where)
        return {"op": "complement", "arg": to_node(arg, f"{where}.arg[0]")}
    if head == REPETITION_BOUNDED:
        arg, lo, hi = _shape(term, 3, where)
        return {"op": "repeat", "arg": to_node(arg, f"{where}.arg[0]"),
                "min": _whole(lo, where), "max": _whole(hi, where)}
    arg, lo = _shape(term, 2, where)
    return {"op": "repeat", "arg": to_node(arg, f"{where}.arg[0]"),
            "min": _whole(lo, where), "max": None}


def from_node(node) -> Term:
    """Intent:
        The `language::` node term of a regular-language node, argument
        for argument, with nothing rewritten.

    Raises:
        InvalidLanguageTerm: the node is not one `mathema.regular`
            defines.
    """
    op = node.get("op") if isinstance(node, dict) else None
    try:
        if op in ("empty", "epsilon"):
            return Term(EMPTY if op == "empty" else EPSILON)
        if op == "literal":
            return Term(LITERAL, (List(tuple(Int(c) for c in node["codes"])),))
        if op == "chars":
            return Term(CHARACTERS, (List(tuple(List((Int(lo), Int(hi)))
                                               for lo, hi in node["ranges"])),))
        if op in _MANY_HEAD:
            return Term(_MANY_HEAD[op], tuple(from_node(a) for a in node["args"]))
        if op == "complement":
            return Term(COMPLEMENT, (from_node(node["arg"]),))
        if op == "repeat":
            arg, lo, hi = from_node(node["arg"]), Int(node["min"]), node["max"]
            if hi is None:
                return Term(REPETITION_UNBOUNDED, (arg, lo))
            return Term(REPETITION_BOUNDED, (arg, lo, Int(hi)))
    except (KeyError, TypeError, ValueError) as e:
        raise InvalidLanguageTerm(f"not a regular-language node: {node!r}") from e
    raise InvalidLanguageTerm(f"not a regular-language node: {node!r}")


def exact(node_term: Term) -> Term:
    """The language of a node term over every code point:
    `language::regular::exact(node_term, alphabet::codepoints)`."""
    return Term(EXACT, (node_term, Term(ALPHABET_CODEPOINTS)))


def node_of_exact(term, where: str = "language") -> dict:
    """Intent:
        The regular-language node of a `language::regular::exact` term
        over the alphabet of code points.

    Raises:
        InvalidLanguageTerm: the term is not that wrapper, names
            another alphabet, or wraps a term that is no node term.
    """
    if not isinstance(term, Term) or term.head != EXACT:
        raise InvalidLanguageTerm(f"{where}: expected {EXACT}(node, {ALPHABET_CODEPOINTS}), "
                                  f"got {term!r}")
    node, alphabet = _shape(term, 2, where)
    if alphabet != Term(ALPHABET_CODEPOINTS):
        raise InvalidLanguageTerm(f"{where}: the alphabet must be {ALPHABET_CODEPOINTS}")
    return to_node(node, f"{where}.arg[0]")


def in_language(text, node: dict) -> Term:
    """The term true exactly when the text `text` is in the language of
    the regular-language node `node`, over every code point."""
    return Term(IN_LANGUAGE, (text, exact(from_node(node))))


__all__ = ["ALPHABET_CODEPOINTS", "CHARACTERS", "COMPLEMENT", "CONCATENATION", "EMPTY",
           "EPSILON", "EXACT", "HEADS", "INTERSECTION", "IN_LANGUAGE", "InvalidLanguageTerm",
           "LITERAL", "NODE_HEADS", "REPETITION_BOUNDED", "REPETITION_UNBOUNDED", "UNION",
           "exact", "from_node", "in_language", "node_of_exact", "to_node"]
