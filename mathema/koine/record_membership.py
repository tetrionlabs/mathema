# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Membership of a record language, stated as a KOINE function.

Draft, not part of the public interface. `membership_expression(node,
operand)` is the truth of "the value `operand` is in the language of
the record-language node `node`" (`mathema.record_language`), written
in the terms of `record_terms`, node by node:

- `empty` is `false` and `any` is `true`;
- `choice` is the disjunction of one test for each value listed: null
  is `value::is_absent`; a truth value is a test of `kind::bool` and
  equality; a number is a test of `kind::int` or `kind::scalar` and
  equality of value, so the choice of 1 holds 1.0 and never `true`; a
  text is a test of `kind::string` and equality;
- `text` is a test of `kind::string` and `in_language` of the node's
  regular language;
- `complement`, `union` and `inter` are `operator::logic::not`, `or`
  and `and`;
- `record` is one conjunction: the value is of `kind::dict`; it has no
  key other than the field names; then one part for each field in the
  order written, for a required field "the key is set and the value at
  it is in the field's node", for an optional one "the key is unset or
  the value at it is in the field's node".

A union or an intersection of no node is `false` or `true`, and of one
node is that node's expression. A `list` node has no expression in this
version.

`membership_document(node)` is the document of the function of one
JSON value that returns that truth, and `membership_documents` the two
of a definition, one for each bound.
"""
from __future__ import annotations

import hashlib
import json

from ..regular import InvalidTerm
from . import language_terms as L
from . import record_terms as T
from .document import Document
from .syntax import Bool, Int, List, Name, Str, Term

KIND = "record_language"
VERSION = 1
NOT, AND, OR = "operator::logic::not", "operator::logic::and", "operator::logic::or"
EQUAL = "operator::comparison::equal"


class Declined(ValueError):
    """A record-language node with no membership expression in this
    version; the message names the node."""


def _kind(operand, kind: str) -> Term:
    return Term(T.IS_OF_KIND, (operand, Term(kind)))


def _present(operand) -> Term:
    return Term(T.VALUE_OF_PRESENT, (operand,))


def _joined(head: str, parts: list):
    """The conjunction (`AND`) or disjunction (`OR`) of `parts`: its
    unit for none, the part itself for one."""
    if not parts:
        return Bool(head == AND)
    return parts[0] if len(parts) == 1 else Term(head, tuple(parts))


def _is_constant(operand, value):
    """The truth of "`operand` is the scalar `value`", by kind and then
    by value."""
    if value is None:
        return Term(T.IS_ABSENT, (operand,))
    if isinstance(value, bool):
        return Term(AND, (_kind(operand, "kind::bool"),
                          Term(EQUAL, (_present(operand), Bool(value)))))
    if isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        a_number = Term(OR, (_kind(operand, "kind::int"), _kind(operand, "kind::scalar")))
        return Term(AND, (a_number, Term(EQUAL, (_present(operand), Int(int(value))))))
    if isinstance(value, str):
        return Term(AND, (_kind(operand, "kind::string"),
                          Term(EQUAL, (_present(operand), Str(value)))))
    raise InvalidTerm(f"a choice lists null, truth values, whole numbers and texts, "
                      f"not {value!r}")


def _field(of_map, field) -> Term:
    if not (isinstance(field, (list, tuple)) and len(field) == 3
            and isinstance(field[0], str) and isinstance(field[2], bool)):
        raise InvalidTerm(f"a field is written [name, node, required], not {field!r}")
    name, inner, required = field
    has = Term(T.HAS_KEY, (of_map, Str(name)))
    inside = membership_expression(inner, Term(T.VALUE_AT_KEY, (of_map, Str(name))))
    if required:
        return Term(AND, (has, inside))
    return Term(OR, (Term(NOT, (has,)), inside))


def membership_expression(node, operand):
    """Intent:
        The KOINE expression true exactly when the value of `operand`,
        an expression of `kind::optional(kind::unknown)`, is in the
        language of the record-language node `node`.

    Raises:
        InvalidTerm: the node is not of the record-language schema.
        Declined: the node is, or holds, a `list` node.
    """
    op = node.get("op") if isinstance(node, dict) else None
    try:
        if op == "empty":
            return Bool(False)
        if op == "any":
            return Bool(True)
        if op == "choice":
            return _joined(OR, [_is_constant(operand, v) for v in node["values"]])
        if op == "text":
            return Term(AND, (_kind(operand, "kind::string"),
                              L.in_language(_present(operand), node["language"])))
        if op == "complement":
            return Term(NOT, (membership_expression(node["arg"], operand),))
        if op in ("union", "inter"):
            return _joined(OR if op == "union" else AND,
                           [membership_expression(a, operand) for a in node["args"]])
        if op == "record":
            if node["rest"] != {"op": "empty"}:
                raise InvalidTerm("a record's rest is empty in this version")
            of_map = _present(operand)
            names = [f[0] if isinstance(f, (list, tuple)) and f else f for f in node["fields"]]
            return Term(AND, (
                _kind(operand, "kind::dict"),
                Term(T.HAS_NO_KEY_OTHER_THAN, (of_map, List(tuple(Str(n) for n in names)))),
                *[_field(of_map, f) for f in node["fields"]]))
    except (KeyError, TypeError) as e:
        raise InvalidTerm(f"not a record-language node: {node!r}") from e
    except L.InvalidLanguageTerm as e:
        raise InvalidTerm(str(e)) from e
    if op == "list":
        raise Declined("a list node has no membership expression in this version")
    raise InvalidTerm(f"not a record-language node: {node!r}")


def membership_document(node, *, name: str = "member") -> Document:
    """Intent:
        The document of the function of one JSON value that returns
        whether the value is in the language of `node`. Its key is the
        name and the first twelve digits of the SHA-256 of the node
        written as JSON with sorted keys.

    Raises:
        InvalidTerm: the node is not of the record-language schema.
        Declined: the node is, or holds, a `list` node.
    """
    expression = membership_expression(node, Name(T.PARAMETER))
    written = json.dumps(node, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(written.encode("ascii")).hexdigest()
    return T.function_of_one_value(expression, name=name, key=f"{KIND}.{name}.{digest[:12]}",
                                   source=KIND)


def membership_documents(definition) -> tuple:
    """Intent:
        The membership documents of a record-language definition, as
        `(at_most, at_least)`: of its language twice when it is exact,
        else of its two bounds.

    Raises:
        InvalidTerm: the definition is not of this kind and version, or
            states both a language and bounds, or neither.
        Declined: a node is, or holds, a `list` node.
    """
    if not (isinstance(definition, dict) and definition.get("kind") == KIND
            and definition.get("version") == VERSION
            and type(definition.get("version")) is int
            and isinstance(definition.get("exact"), bool)):
        raise InvalidTerm(f"not a {KIND} definition of version {VERSION}")
    stated = set(definition) - {"kind", "version", "exact", "source"}
    if definition["exact"]:
        if stated != {"language"}:
            raise InvalidTerm("an exact definition states its language and no bound")
        document = membership_document(definition["language"])
        return document, document
    if stated != {"at_least", "at_most"}:
        raise InvalidTerm("a definition that is not exact states at_least and at_most")
    return (membership_document(definition["at_most"], name="member_at_most"),
            membership_document(definition["at_least"], name="member_at_least"))


__all__ = ["Declined", "KIND", "VERSION", "membership_document", "membership_documents",
           "membership_expression"]
