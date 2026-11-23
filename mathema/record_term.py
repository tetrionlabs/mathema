# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Record-language terms: the document format a language of JSON values
is stated in, its canonical form and its hash. What a term means is
stated once, in KOINE, by `mathema.koine.record_membership`; this module
holds no meaning and asks no solver.

Draft, not part of the public interface: every name here is provisional.

A definition is a plain JSON document shaped as a regular-language
definition is: `{"kind": "record_language", "version": 1, "exact":
bool, ...}`. An exact definition carries its language under `language`;
one that is not exact carries two bounds in its place, `at_least` (a
language holding every member) and `at_most` (a language holding only
members). `source`, and any key beside the stated ones, is provenance
and no part of the meaning: `term_hash` reads the version, the exact
flag and the nodes, in canonical form, and nothing else.

A language is a node keyed by `op`:

- `empty`, no value, and `any`, every value;
- `choice`, exactly the scalar `values` listed (null, a truth value, a
  whole number, a text);
- `text`, the texts in the language of a regular-language node
  (`mathema.regular`), under `language`;
- `record`, the maps whose every key is one of its `fields`, each
  written `[name, node, required]`, and `rest`, which this version reads
  as empty only (a closed record);
- `list`, the lists of `item` values, of a length from `min` to `max`
  (`max` null for no end);
- `union`, `inter` and `complement`, the last over every JSON value.

The definitions built from definitions (`complement_of`, `union_of`,
`inter_of`, `record_of`, `list_of`) place each bound so the built
definition's `at_least` holds every member and its `at_most` only
members.
"""
from __future__ import annotations

import hashlib
import json

from . import regular
from .regular import InvalidTerm

KIND = "record_language"
VERSION = 1

_EMPTY = {"op": "empty"}
_ANY = {"op": "any"}
#: the keys each operation's node holds beside `op`, and no others
_NODE_KEYS = {"empty": (), "any": (), "choice": ("values",), "text": ("language",),
              "record": ("fields", "rest"), "list": ("item", "min", "max"),
              "union": ("args",), "inter": ("args",),
              "complement": ("arg",)}
_BOUNDS = ("at_least", "at_most")


# ---- values -----------------------------------------------------------

def _scalar_key(value) -> "tuple | None":
    """A scalar value as `(kind, value)`, numbers by their value, or
    None for a value that is no scalar a choice may list."""
    if value is None:
        return ("null", None)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, int):
        return ("number", value)
    if isinstance(value, float) and value.is_integer():
        return ("number", int(value))
    if isinstance(value, str):
        return ("text", value)
    return None


def _serial(value) -> str:
    """The one serialisation of a canonical value: JSON with sorted
    keys, no white space, ASCII only.

    Raises:
        InvalidTerm: the value holds a whole number too long for Python
            to write in decimal.
    """
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    except ValueError as e:
        raise InvalidTerm(f"a value this term cannot write: {e}") from None


def _no_surrogate(text: str, what: str) -> str:
    """`text`, when it holds no high surrogate followed by a low one.
    ASCII JSON writes such a pair as the same two escapes as the one
    character beyond the basic plane they encode, and reads those
    escapes back as that character, so a term holding the pair would not
    keep its meaning through its own canonical text. A surrogate on its
    own is written and read back as itself.

    Raises:
        InvalidTerm: the text holds such a pair.
    """
    for i in range(len(text) - 1):
        if "\ud800" <= text[i] <= "\udbff" and "\udc00" <= text[i + 1] <= "\udfff":
            raise InvalidTerm(f"{what} {text!r} holds the surrogate pair U+{ord(text[i]):04X} "
                              f"U+{ord(text[i + 1]):04X}, which JSON text reads back as one "
                              "character")
    return text


# ---- the canonical form and the hash ----------------------------------

def canonical(node) -> dict:
    """Intent:
        The canonical form of a node, its arguments made canonical
        first, by these rules and no others.

        1. `choice`: equal values kept once (a number by its value, so
           `1.0` is written `1`); sorted by their serialisation; no
           value is `empty`.
        2. `text`: the regular-language node canonical by
           `regular.canonical`; the empty regular language is `empty`.
        3. `record`: fields sorted by name; a required field whose node
           is `empty` makes `empty`; an optional field whose node is
           `empty` stays, and forbids the key.
        4. `union`: nested unions flattened; `empty` arguments dropped;
           an `any` argument makes `any`; equal arguments kept once;
           sorted by their serialisation; none left is `empty`; one
           left is that argument.
        5. `inter`: nested intersections flattened; `any` arguments
           dropped; an `empty` argument makes `empty`; equal arguments
           kept once; sorted; none left is `any`; one left is that
           argument.
        6. `list`: a `max` below its `min` makes `empty`; a `max` of 0,
           or an `empty` item with a `min` of 0, is the list of nothing,
           written with an `empty` item, `min` 0 and `max` 0; an `empty`
           item with a `min` above 0 makes `empty`.
        7. `complement`, `empty` and `any` are kept as they are.

        The rules read the form and not the meaning: two nodes with the
        same members may have two canonical forms.

    Raises:
        InvalidTerm: the node is not of the schema: an unknown `op`,
            keys other than the operation's own, a choice value that is
            no scalar, a field not written `[name, node, required]`, a
            name twice, a `rest` other than `empty`, or a list whose
            `min` or `max` is not a whole number of zero or more.
    """
    if not isinstance(node, dict) or not isinstance(node.get("op"), str) \
            or node["op"] not in _NODE_KEYS:
        raise InvalidTerm(f"not a record-language node: {node!r}")
    op = node["op"]
    if set(node) != {"op", *_NODE_KEYS[op]}:
        raise InvalidTerm(f"a {op} node holds op and {list(_NODE_KEYS[op])}, not {sorted(node)}")
    if op in ("empty", "any"):
        return {"op": op}
    if op == "choice":
        if not isinstance(node["values"], list):
            raise InvalidTerm("the values of a choice are a list")
        keys = []
        for value in node["values"]:
            key = _scalar_key(value)
            if key is None:
                raise InvalidTerm(f"{value!r} is not a value a choice may list (null, a "
                                  f"boolean, a whole number, a text)")
            if key[0] == "text":
                _no_surrogate(key[1], "the choice value")
            keys.append(key)
        by_text = {_serial(key[1]): key[1] for key in keys}
        values = [by_text[text] for text in sorted(by_text)]
        return {"op": "choice", "values": values} if values else dict(_EMPTY)
    if op == "text":
        language = _regular_canonical(node["language"])
        return dict(_EMPTY) if language == {"op": "empty"} else {"op": "text", "language": language}
    if op == "complement":
        return {"op": "complement", "arg": canonical(node["arg"])}
    if op == "record":
        return _canonical_record(node)
    if op == "list":
        return _canonical_list(node)
    if not isinstance(node["args"], list):
        raise InvalidTerm(f"the args of a {op} are a list")
    args: list = []
    for arg in map(canonical, node["args"]):
        args.extend(arg["args"] if arg["op"] == op else [arg])
    absorbing, unit = (_ANY, _EMPTY) if op == "union" else (_EMPTY, _ANY)
    if absorbing in args:
        return dict(absorbing)
    by_text = {_serial(a): a for a in args if a != unit}
    kept = [by_text[text] for text in sorted(by_text)]
    if not kept:
        return dict(unit)
    return kept[0] if len(kept) == 1 else {"op": op, "args": kept}


#: the canonical form of each regular-language node read, by its serialisation
_REGULAR: dict = {}


def _regular_canonical(node) -> dict:
    """`regular.canonical` of a text node's language, remembered by the
    node's serialisation, since one language is read under many
    records."""
    try:
        key = _serial(node)
    except (TypeError, ValueError):
        return regular.canonical(node)
    if key not in _REGULAR:
        if len(_REGULAR) > 4096:
            _REGULAR.clear()
        _REGULAR[key] = regular.canonical(node)
    return json.loads(_serial(_REGULAR[key]))


def _canonical_record(node: dict) -> dict:
    if not isinstance(node["fields"], list):
        raise InvalidTerm("the fields of a record are a list of [name, node, required]")
    if canonical(node["rest"]) != _EMPTY:
        raise InvalidTerm("this version reads a closed record only: rest is empty")
    fields = []
    for field in node["fields"]:
        if not isinstance(field, list) or len(field) != 3 or not isinstance(field[0], str) \
                or not isinstance(field[2], bool):
            raise InvalidTerm(f"{field!r} is not a field [name, node, required]")
        fields.append([_no_surrogate(field[0], "the field name"), canonical(field[1]), field[2]])
    names: list[str] = [name for name, _, _ in fields]
    if len(set(names)) != len(names):
        raise InvalidTerm(f"a record names a field once, not {sorted(names)}")
    if any(required and value == _EMPTY for _, value, required in fields):
        return dict(_EMPTY)
    return {"op": "record", "fields": sorted(fields, key=lambda f: f[0]), "rest": dict(_EMPTY)}


def _count(value, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidTerm(f"the {what} of a list is a whole number of zero or more, not "
                          f"{value!r}")
    return value


def _canonical_list(node: dict) -> dict:
    item = canonical(node["item"])
    lo = _count(node["min"], "min")
    hi = None if node["max"] is None else _count(node["max"], "max")
    if hi is not None and hi < lo:
        return dict(_EMPTY)
    if hi == 0 or (item == _EMPTY and lo == 0):
        return {"op": "list", "item": dict(_EMPTY), "min": 0, "max": 0}
    if item == _EMPTY:
        return dict(_EMPTY)
    return {"op": "list", "item": item, "min": lo, "max": hi}


def _meaning(document) -> tuple:
    """`(exact, at_most, at_least)` of a document's meaning, whatever
    kind and version it states, the nodes canonical."""
    if not isinstance(document, dict):
        raise InvalidTerm("a definition is an object")
    version = document.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise InvalidTerm(f"the version {version!r} is not a whole number")
    exact = document.get("exact")
    bounds = [key for key in _BOUNDS if key in document]
    if exact is True and "language" in document and not bounds:
        node = canonical(document["language"])
        return True, node, node
    if exact is False and len(bounds) == 2 and "language" not in document:
        return False, canonical(document["at_most"]), canonical(document["at_least"])
    raise InvalidTerm("an exact definition states 'language' and no bound; one that is not "
                      "exact states 'at_least' and 'at_most' and no 'language'")


def _read(document) -> tuple:
    """`_meaning` of a definition this module answers questions about:
    of this kind and version."""
    meaning = _meaning(document)
    if document.get("kind") != KIND:
        raise InvalidTerm(f"not a {KIND} definition")
    if document["version"] != VERSION:
        raise InvalidTerm(f"{KIND} version {document['version']!r} is not read; this reads "
                          f"version {VERSION}")
    return meaning


def canonical_text(document) -> str:
    """Intent:
        The text a definition's hash is taken of: the serialisation
        (JSON, sorted keys, no white space, ASCII only) of its version,
        its exact flag and its canonical node or two bounds. `kind`,
        `source` and any other key are not in it.

    Raises:
        InvalidTerm: the document is not of the schema.
    """
    exact, at_most, at_least = _meaning(document)
    meaning: dict = {"version": document["version"], "exact": exact}
    if exact:
        meaning["language"] = at_most
    else:
        meaning["at_least"], meaning["at_most"] = at_least, at_most
    return _serial(meaning)


def validate(document) -> None:
    """Intent:
        Nothing when `document` is a well-formed definition of any kind
        and version. `is_definition` says whether this module answers
        questions about it, which also needs this kind and version.

    Raises:
        InvalidTerm: naming the rule the document breaks.
    """
    canonical_text(document)


def term_hash(document) -> str:
    """Intent:
        The identity of a definition's meaning: the SHA-256, in lower
        case hex, of its `canonical_text`.

    Raises:
        InvalidTerm: the document is not of the schema.
    """
    return hashlib.sha256(canonical_text(document).encode("ascii")).hexdigest()


def is_definition(document) -> bool:
    """Whether `document` is a record-language definition this module
    reads."""
    try:
        _read(document)
    except InvalidTerm:
        return False
    return True


def bounds(document) -> tuple:
    """Intent:
        `(at_most, at_least)` for a definition, as canonical nodes: a
        language holding only members, and one holding every member.
        They are one node when the definition is exact.

    Raises:
        InvalidTerm: the document is not a definition of this kind and
            version.
    """
    _, at_most, at_least = _read(document)
    return at_most, at_least


# ---- definitions built from definitions --------------------------------

def _definition(at_most: dict, at_least: dict, exact: bool) -> dict:
    if exact:
        return {"kind": KIND, "version": VERSION, "exact": True, "language": at_most}
    return {"kind": KIND, "version": VERSION, "exact": False, "at_least": at_least,
            "at_most": at_most}


def complement_of(document) -> dict:
    """Intent:
        The definition of every value outside a definition's language.
        Its `at_most` is the complement of the definition's `at_least`
        and its `at_least` the complement of the `at_most`: what is
        certainly outside is what is outside every possible member. It
        is exact when the definition is.

    Raises:
        InvalidTerm: the document is not a definition this module reads.
    """
    exact, at_most, at_least = _read(document)
    return _definition({"op": "complement", "arg": at_least},
                       {"op": "complement", "arg": at_most}, exact)


def _joined(op: str, documents) -> dict:
    read = [_read(d) for d in documents]
    return _definition(canonical({"op": op, "args": [r[1] for r in read]}),
                       canonical({"op": op, "args": [r[2] for r in read]}),
                       all(r[0] for r in read))


def union_of(*documents) -> dict:
    """The definition of the values in any of the definitions' languages,
    bound by bound; exact when each of them is."""
    return _joined("union", documents)


def inter_of(*documents) -> dict:
    """The definition of the values in every one of the definitions'
    languages, bound by bound; exact when each of them is."""
    return _joined("inter", documents)


def record_of(fields) -> dict:
    """Intent:
        The definition of the closed records over `fields`, each given
        as `(name, definition, required)`: its `at_most` holds each
        field's `at_most` and its `at_least` each field's `at_least`.
        It is exact when each field's definition is.

    Raises:
        InvalidTerm: a definition is not one this module reads, or a
            name is given twice.
    """
    read = [(name, _read(d), required) for name, d, required in fields]

    def over(side: int) -> dict:
        return canonical({"op": "record", "rest": dict(_EMPTY),
                          "fields": [[name, r[side], required] for name, r, required in read]})
    return _definition(over(1), over(2), all(r[0] for _, r, _ in read))


def list_of(document, lo: int = 0, hi: "int | None" = None) -> dict:
    """The definition of the lists of `lo` to `hi` values of a
    definition's language (`hi` None for no end), bound by bound; exact
    when the definition is."""
    exact, at_most, at_least = _read(document)

    def over(item: dict) -> dict:
        return canonical({"op": "list", "item": item, "min": lo, "max": hi})
    return _definition(over(at_most), over(at_least), exact)


__all__ = ["InvalidTerm", "KIND", "VERSION", "bounds", "canonical", "canonical_text",
           "complement_of", "inter_of", "is_definition", "list_of", "record_of", "term_hash",
           "union_of", "validate"]
