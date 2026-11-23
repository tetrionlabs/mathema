# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The terms a function of one JSON value is written in: a test of the
kind a value has, absence, the keys of a map, and membership of a text
in a regular language.

Draft, not part of the public interface: every name here is
provisional, and none is in `vocabulary`. A JSON value is null, a truth
value, a number, a text, a list, or a map from text keys to values, as
Python carries them (`None`, `bool`, `int` and `float`, `str`, `list`,
`dict`).

    kind::optional(K)
        the kind of a value that is absent or a value of kind K.
    value::is_absent(e)
        true exactly when e is absent. Absence has two members: a key
        that is unset, and null (a key holding null, or null itself).
    value::value_of_present(e)
        e's value where e is not absent; where it is absent the
        expression has no value, of the class `nonvalue::data::absent`.
    value::is_of_kind(e, kind::K)
        true exactly when e's value is of the tested kind K, one of:
        `kind::bool`, a truth value; `kind::int`, a whole number
        carried as an integer, never a truth value; `kind::scalar`, a
        number carried in floating point, so 1.0 is of this kind and 1
        is not; `kind::string`, a text; `kind::sequence`, a list;
        `kind::dict`, a map. A value is of at most one tested kind, an
        absent one of none. The term has a value for every operand.
    value::map::has_key(m, "k")
        true exactly when the map m holds the key k, whatever it holds
        there, null included.
    value::map::value_at_key(m, "k")
        the value m holds under k, of `kind::optional(kind::unknown)`:
        absent where k is unset and where k holds null.
    value::map::has_no_key_other_than(m, ["k1", ...])
        true exactly when every key m holds is one of those listed.
    operator::membership::in_language(e, language::regular::exact(n,
    alphabet::codepoints))
        true exactly when the text e is in the regular language n
        (`language_terms`).

A key is unset exactly when `has_key` is false; it holds null exactly
when `has_key` is true and the value at the key is absent. The three
`value::map::` terms have no value to give for an operand that is no
map, nor `in_language` for one that is no text: such a point is not
runnable, as an index past the end is not.

`validate` is `mathema.koine.validate` over `lower(document)`, in which
each term above is replaced by a term of `vocabulary` with the same
operand, so names and scope are checked as for any document, plus the
shape of each term. `interpret` is `mathema.koine.interpret` with each
term evaluated at the place it stands, its operand evaluated once and
in order.
"""
from __future__ import annotations

import hashlib

from .. import regular
from . import language_terms
from .document import Document
from .interpret import InterpretError, NoValue
from .interpret import interpret as _interpret
from .syntax import Int, List, Name, Str, Term, compact
from .validate import validate as _validate
from .vocabulary import KINDS, KOINE_VERSION

OPTIONAL = "kind::optional"
IS_ABSENT = "value::is_absent"
VALUE_OF_PRESENT = "value::value_of_present"
IS_OF_KIND = "value::is_of_kind"
HAS_KEY = "value::map::has_key"
VALUE_AT_KEY = "value::map::value_at_key"
HAS_NO_KEY_OTHER_THAN = "value::map::has_no_key_other_than"
IN_LANGUAGE = language_terms.IN_LANGUAGE
#: the terms of this module that are expressions
EXPRESSIONS = frozenset({IS_ABSENT, VALUE_OF_PRESENT, IS_OF_KIND, HAS_KEY, VALUE_AT_KEY,
                         HAS_NO_KEY_OTHER_THAN, IN_LANGUAGE})
HEADS = EXPRESSIONS | {OPTIONAL}

#: the kinds a kind test may name; a value is of at most one of them
TESTED_KINDS = ("kind::bool", "kind::int", "kind::scalar", "kind::string", "kind::sequence",
                "kind::dict")
ABSENT_CLASS = "nonvalue::data::absent"
#: the parameter of a function of one value
PARAMETER = "value"

#: the term of `vocabulary` each expression is read as by the validator:
#: one with the same single operand, a truth value or the operand's own
_STAND_IN = {IS_ABSENT: "operator::logic::not", IS_OF_KIND: "operator::logic::not",
             HAS_KEY: "operator::logic::not", HAS_NO_KEY_OTHER_THAN: "operator::logic::not",
             IN_LANGUAGE: "operator::logic::not",
             VALUE_OF_PRESENT: "operator::unary::identity",
             VALUE_AT_KEY: "operator::unary::identity"}
_CALL = "mathema.koine.record_terms#"


def kind_of(value) -> "str | None":
    """The tested kind of a JSON value as Python carries it, or None
    for null and for any other object."""
    if isinstance(value, bool):
        return "kind::bool"
    if isinstance(value, int):
        return "kind::int"
    if isinstance(value, float):
        return "kind::scalar"
    if isinstance(value, str):
        return "kind::string"
    if isinstance(value, (list, tuple)):
        return "kind::sequence"
    if isinstance(value, dict):
        return "kind::dict"
    return None


# ---- the shape of each term ---------------------------------------------

def _names_of(node) -> "list | None":
    """The texts of a list of distinct string literals, else None."""
    if not isinstance(node, List) or not all(isinstance(x, Str) for x in node.items):
        return None
    names = [x.value for x in node.items]
    return names if len(set(names)) == len(names) else None


def shape_problem(term: Term) -> "str | None":
    """What is wrong with the shape of one term of this module, or
    None."""
    head, args = term.head, term.args
    if term.named:
        return f"{head} takes no named argument"
    if head == OPTIONAL:
        if not (len(args) == 1 and isinstance(args[0], Term) and args[0].head in KINDS
                and not args[0].args and not args[0].named):
            return f"{head} takes one kind:: that is not itself optional"
        return None
    if head in (IS_ABSENT, VALUE_OF_PRESENT):
        return None if len(args) == 1 else f"{head} takes one operand"
    if head == IS_OF_KIND:
        if not (len(args) == 2 and isinstance(args[1], Term) and args[1].head in TESTED_KINDS
                and not args[1].args and not args[1].named):
            return f"{head} takes an operand and one of {', '.join(TESTED_KINDS)}"
        return None
    if head in (HAS_KEY, VALUE_AT_KEY):
        if not (len(args) == 2 and isinstance(args[1], Str)):
            return f"{head} takes a map and a key written as a string"
        return None
    if head == HAS_NO_KEY_OTHER_THAN:
        if not (len(args) == 2 and _names_of(args[1]) is not None):
            return f"{head} takes a map and a list of distinct keys written as strings"
        return None
    if len(args) != 2:
        return f"{head} takes a text and a {language_terms.EXACT} term"
    try:
        language_terms.node_of_exact(args[1])
    except language_terms.InvalidLanguageTerm as e:
        return str(e)
    return None


def _rewritten(node, rewrite):
    """`node` with every term replaced by `rewrite(term)`, the terms
    inside it first."""
    if isinstance(node, Term):
        inner = Term(node.head, tuple(_rewritten(a, rewrite) for a in node.args),
                     tuple((k, _rewritten(v, rewrite)) for k, v in node.named))
        return rewrite(inner)
    if isinstance(node, List):
        return List(tuple(_rewritten(x, rewrite) for x in node.items))
    return node


def _terms(node):
    """Every term inside `node`, `node` included, outermost first; the
    language of an `in_language` term is not entered."""
    if isinstance(node, Term):
        yield node
        inner = node.args[:1] if node.head == IN_LANGUAGE else node.args
        for a in inner:
            yield from _terms(a)
        for _, v in node.named:
            yield from _terms(v)
    elif isinstance(node, List):
        for x in node.items:
            yield from _terms(x)


def lower(document: Document) -> Document:
    """Intent:
        `document` with each well-shaped term of this module replaced
        by the term of `vocabulary` it is validated as: `kind::optional(K)`
        by K, every other by a term of its one operand. A term whose
        shape is wrong is left as it is.
    """
    def rewrite(term: Term):
        if term.head not in HEADS or shape_problem(term) is not None:
            return term
        if term.head == OPTIONAL:
            return term.args[0]
        return Term(_STAND_IN[term.head], term.args[:1])

    def top(term):
        # the language of an in_language term is no expression, so the
        # term is replaced before its arguments are walked
        return _rewritten(_without_languages(term), rewrite)
    return Document(tuple(top(t) for t in document.terms))


def _without_languages(node):
    """`node` with the language of each well-shaped `in_language` term
    dropped, leaving its operand."""
    if isinstance(node, Term):
        if node.head == IN_LANGUAGE and shape_problem(node) is None:
            return Term(_STAND_IN[IN_LANGUAGE], (_without_languages(node.args[0]),))
        return Term(node.head, tuple(_without_languages(a) for a in node.args),
                    tuple((k, _without_languages(v)) for k, v in node.named))
    if isinstance(node, List):
        return List(tuple(_without_languages(x) for x in node.items))
    return node


def validate(document) -> list:
    """Intent:
        Every way `document` fails KOINE with the terms of this module,
        as `where: what` strings; empty when valid. The problems are
        the shape of each term of this module, then those
        `mathema.koine.validate` reports of `lower(document)`.
    """
    if not isinstance(document, Document):
        return ["document: not a KOINE document"]
    out = []
    for i, top in enumerate(document.terms):
        for term in _terms(top):
            if term.head in HEADS:
                problem = shape_problem(term)
                if problem is not None:
                    out.append(f"[{i}]: {problem}")
    return out + _validate(lower(document))


# ---- the meaning of each term at a point ---------------------------------

class _Signal(BaseException):
    """An outcome reached inside a term of this module, carried out
    through the interpreter: a `NoValue`, or the `InterpretError` of a
    point that is not runnable."""

    def __init__(self, outcome) -> None:
        self.outcome = outcome


def _map(value, head: str) -> dict:
    if not isinstance(value, dict):
        raise _Signal(InterpretError(f"{head} of a value that is no map"))
    return value


def _meaning(term: Term):
    """The function of its operand's value a well-shaped expression of
    this module computes."""
    head = term.head
    if head == IS_ABSENT:
        return lambda x: x is None
    if head == VALUE_OF_PRESENT:
        def present(x):
            if x is None:
                raise _Signal(NoValue(ABSENT_CLASS, head))
            return x
        return present
    if head == IS_OF_KIND:
        kind = term.args[1].head
        return lambda x: kind_of(x) == kind
    if head == HAS_KEY:
        key = term.args[1].value
        return lambda m: key in _map(m, head)
    if head == VALUE_AT_KEY:
        key = term.args[1].value
        return lambda m: _map(m, head).get(key)
    if head == HAS_NO_KEY_OTHER_THAN:
        names = frozenset(_names_of(term.args[1]))
        return lambda m: all(k in names for k in _map(m, head))
    node = language_terms.node_of_exact(term.args[1])

    def in_language(x):
        if not isinstance(x, str):
            raise _Signal(InterpretError(f"{head} of a value that is no text"))
        try:
            return regular.contains(node, x)
        except regular.MatchBudget as e:
            raise _Signal(InterpretError(f"{head}: the matcher's budget is spent")) from e
    return in_language


def interpret(document: Document, point, calls: "dict | None" = None):
    """Intent:
        The outcome of `document`'s body at `point`, as
        `mathema.koine.interpret` gives it, each term of this module
        evaluated by the meaning the module states for it.

    Raises:
        InterpretError: the document is not runnable at this point: a
            `value::map::` term of a value that is no map, `in_language`
            of a value that is no text, a term whose shape is wrong, or
            any point `mathema.koine.interpret` does not run.
    """
    table: dict = {}

    def rewrite(term: Term):
        if term.head == OPTIONAL and shape_problem(term) is None:
            return term.args[0]
        if term.head not in EXPRESSIONS:
            return term
        if shape_problem(term) is not None:
            raise InterpretError(f"{term.head}: {shape_problem(term)}")
        key = f"{_CALL}{len(table)}"
        table[key] = _meaning(term)
        return Term("call::library", (Str(key), term.args[0]))

    runnable = Document(tuple(_languages_kept(t, rewrite) for t in document.terms))
    try:
        return _interpret(runnable, point, {**(calls or {}), **table})
    except _Signal as signal:
        if isinstance(signal.outcome, NoValue):
            return signal.outcome
        raise signal.outcome from None


def _languages_kept(node, rewrite):
    """`node` with every term replaced by `rewrite(term)`, the terms
    inside it first, the language of an `in_language` term left
    unread."""
    if isinstance(node, Term):
        if node.head == IN_LANGUAGE and len(node.args) == 2:
            return rewrite(Term(node.head, (_languages_kept(node.args[0], rewrite),
                                            node.args[1]), node.named))
        return rewrite(Term(node.head, tuple(_languages_kept(a, rewrite) for a in node.args),
                            tuple((k, _languages_kept(v, rewrite)) for k, v in node.named)))
    if isinstance(node, List):
        return List(tuple(_languages_kept(x, rewrite) for x in node.items))
    return node


# ---- a function of one value ----------------------------------------------

def function_of_one_value(expression, *, name: str = "f", key: "str | None" = None,
                          source: str = "koine") -> Document:
    """Intent:
        The document of the function of one JSON value, the parameter
        `value` of `kind::optional(kind::unknown)`, whose body returns
        `expression`. Its `source` line carries the SHA-256 of the
        expression's compact text in UTF-8, a surrogate on its own
        written as its three bytes, and its key is `key`, or the name
        and the first twelve digits of that hash.
    """
    digest = hashlib.sha256(compact(expression).encode("utf-8", "surrogatepass")).hexdigest()
    return Document((
        Term("koine", (Str(KOINE_VERSION),)),
        Term("lifter", (), (("language", Str("koine")),
                            ("name", Str("mathema.koine.record_terms")),
                            ("version", Str("0")))),
        Term("source", (), (("file", Str(source)), ("line", Int(1)), ("sha256", Str(digest)))),
        Term("function", (), (("name", Str(name)),
                              ("key", Str(key or f"{name}.{digest[:12]}")))),
        Term("parameter", (Name(PARAMETER), Term(OPTIONAL, (Term("kind::unknown"),)))),
        Term("returns", (Term("kind::bool"),)),
        Term("body", (Term("statement::return", (expression,),
                           (("at", Term("span", (Int(1), Int(1), Str(name)))),)),)),
    ))


__all__ = ["ABSENT_CLASS", "EXPRESSIONS", "HAS_KEY", "HAS_NO_KEY_OTHER_THAN", "HEADS",
           "IN_LANGUAGE", "IS_ABSENT", "IS_OF_KIND", "OPTIONAL", "PARAMETER", "TESTED_KINDS",
           "VALUE_AT_KEY", "VALUE_OF_PRESENT", "function_of_one_value", "interpret", "kind_of",
           "lower", "shape_problem", "validate"]
