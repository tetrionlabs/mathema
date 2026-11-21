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

A node is read only when it is of the record-language schema, by the
same rules `check_node` states: each operation has exactly its own
keys; a choice lists null, truth values, numbers that are whole and
texts; a field is a list `[name, node, required]` with a text name
written once in its record; `values`, `args` and `fields` are lists; a
text's language is a regular-language node; a list's `min` and `max`
are whole numbers of zero or more; and a record's `rest` is empty in
canonical form, so `union []` or a choice of nothing closes a record as
`empty` does. A whole number whose decimal text is longer than the
interpreter writes is refused.

`membership_document(node)` is the document of the function of one
JSON value that returns that truth, and `membership_documents` the two
of a definition, one for each bound.
"""
from __future__ import annotations

import hashlib
import json

from .. import regular
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


#: the keys each operation's node holds beside `op`, and no others
_NODE_KEYS = {"empty": (), "any": (), "choice": ("values",), "text": ("language",),
              "record": ("fields", "rest"), "list": ("item", "min", "max"),
              "union": ("args",), "inter": ("args",), "complement": ("arg",)}
_EMPTY = {"op": "empty"}


def _is_whole_number(value) -> bool:
    return (isinstance(value, int) and not isinstance(value, bool)) \
        or (isinstance(value, float) and value.is_integer())


def _check_scalar(value) -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if not _is_whole_number(value):
        raise InvalidTerm(f"{value!r} is not a value a choice may list (null, a truth value, "
                          f"a whole number, a text)")
    try:
        str(int(value))
    except ValueError as e:
        raise InvalidTerm("a whole number in a choice is longer than this interpreter "
                          "writes") from e


def _check_count(value, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidTerm(f"the {what} of a list is a whole number of zero or more, not "
                          f"{value!r}")
    return value


def _check_language(node) -> None:
    try:
        regular.canonical(node)
    except regular.InvalidTerm:
        raise
    except (TypeError, KeyError, AttributeError, IndexError, ValueError) as e:
        raise InvalidTerm(f"the language of a text is no regular-language node: "
                          f"{node!r}") from e


def check_node(node) -> None:
    """Intent:
        Nothing when `node` is a record-language node of the schema the
        module states, its nodes inside it included.

    Raises:
        InvalidTerm: naming the rule the node breaks.
    """
    op = node.get("op") if isinstance(node, dict) else None
    if not isinstance(op, str) or op not in _NODE_KEYS:
        raise InvalidTerm(f"not a record-language node: {node!r}")
    if set(node) != {"op", *_NODE_KEYS[op]}:
        raise InvalidTerm(f"a {op} node holds op and {list(_NODE_KEYS[op])}, not "
                          f"{sorted(map(str, node))}")
    if op == "choice":
        if not isinstance(node["values"], list):
            raise InvalidTerm("the values of a choice are a list")
        for value in node["values"]:
            _check_scalar(value)
    elif op == "text":
        _check_language(node["language"])
    elif op == "complement":
        check_node(node["arg"])
    elif op in ("union", "inter"):
        if not isinstance(node["args"], list):
            raise InvalidTerm(f"the args of a {op} are a list")
        for arg in node["args"]:
            check_node(arg)
    elif op == "list":
        check_node(node["item"])
        _check_count(node["min"], "min")
        if node["max"] is not None:
            _check_count(node["max"], "max")
    elif op == "record":
        if not isinstance(node["fields"], list):
            raise InvalidTerm("the fields of a record are a list of [name, node, required]")
        check_node(node["rest"])
        if not _canonically_empty(node["rest"]):
            raise InvalidTerm("this version reads a closed record only: rest is empty")
        names = []
        for field in node["fields"]:
            if not (isinstance(field, list) and len(field) == 3 and isinstance(field[0], str)
                    and isinstance(field[2], bool)):
                raise InvalidTerm(f"{field!r} is not a field [name, node, required]")
            check_node(field[1])
            names.append(field[0])
        if len(set(names)) != len(names):
            raise InvalidTerm(f"a record names a field once, not {sorted(names)}")


def _canonically_empty(node: dict) -> bool:
    """Whether a node that `check_node` accepts is `empty` in canonical
    form: `empty`; a choice of nothing; a text of the empty regular
    language; a record with a required field of such a node; a list
    whose `max` is below its `min`, or whose item is such a node and
    whose length cannot be 0; a union all of whose arguments are such
    nodes (none included); an intersection one of whose arguments is
    one. A complement and `any` never are."""
    op = node["op"]
    if op == "empty":
        return True
    if op == "choice":
        return not node["values"]
    if op == "text":
        return regular.canonical(node["language"]) == {"op": "empty"}
    if op == "record":
        return any(required and _canonically_empty(inner)
                   for _, inner, required in node["fields"])
    if op == "list":
        lo, hi = node["min"], node["max"]
        if hi is not None and hi < lo:
            return True
        return hi != 0 and lo != 0 and _canonically_empty(node["item"])
    if op == "union":
        return all(_canonically_empty(a) for a in node["args"])
    if op == "inter":
        return any(_canonically_empty(a) for a in node["args"])
    return False


def _field(of_map, field) -> Term:
    name, inner, required = field
    has = Term(T.HAS_KEY, (of_map, Str(name)))
    inside = _expression(inner, Term(T.VALUE_AT_KEY, (of_map, Str(name))))
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
        Declined: the node is, or holds, a `list` node outside a rest.
    """
    check_node(node)
    return _expression(node, operand)


def _expression(node: dict, operand):
    op = node["op"]
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
        return Term(NOT, (_expression(node["arg"], operand),))
    if op in ("union", "inter"):
        return _joined(OR if op == "union" else AND,
                       [_expression(a, operand) for a in node["args"]])
    if op == "record":
        of_map = _present(operand)
        names = [f[0] for f in node["fields"]]
        return Term(AND, (
            _kind(operand, "kind::dict"),
            Term(T.HAS_NO_KEY_OTHER_THAN, (of_map, List(tuple(Str(n) for n in names)))),
            *[_field(of_map, f) for f in node["fields"]]))
    raise Declined("a list node has no membership expression in this version")


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
        InvalidTerm: the definition is not of this kind and version,
            states both a language and bounds or neither, or a node is
            not of the schema. Any other key, `source` among them, is
            not read.
        Declined: a node is, or holds, a `list` node outside a rest.
    """
    if not isinstance(definition, dict):
        raise InvalidTerm("a definition is an object")
    version = definition.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise InvalidTerm(f"the version {version!r} is not a whole number")
    exact = definition.get("exact")
    bounds = [key for key in ("at_least", "at_most") if key in definition]
    if exact is True and "language" in definition and not bounds:
        nodes = (definition["language"],)
    elif exact is False and len(bounds) == 2 and "language" not in definition:
        nodes = (definition["at_most"], definition["at_least"])
    else:
        raise InvalidTerm("an exact definition states 'language' and no bound; one that is "
                          "not exact states 'at_least' and 'at_most' and no 'language'")
    for node in nodes:
        check_node(node)
    if definition.get("kind") != KIND or version != VERSION:
        raise InvalidTerm(f"not a {KIND} definition of version {VERSION}")
    if exact:
        document = membership_document(definition["language"])
        return document, document
    return (membership_document(definition["at_most"], name="member_at_most"),
            membership_document(definition["at_least"], name="member_at_least"))


__all__ = ["Declined", "KIND", "VERSION", "check_node", "membership_document",
           "membership_documents", "membership_expression"]
