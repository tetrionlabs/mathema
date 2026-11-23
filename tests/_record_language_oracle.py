# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The record-language oracle: the written meaning of a record-language
term, and a search for a member over a small universe of values, with
no solver. It is a test helper, so no module of the package imports it.

The document format (validate, canonical form, canonical text, hash, the
definitions built from definitions) is `mathema.record_term`'s, read
here under the same names; this module adds what a term means.

The values a language is of are the JSON values: null, the two
booleans, numbers, texts, lists, and maps from text keys to values. A
boolean is never a number, and a number is read by its value, so `1`
and `1.0` are one value, as are `0`, `0.0` and `-0.0`, while `True` is
not `1` and `False` is not `0`. Two values are compared by kind and
then by value, never by Python's `==`, under which `True == 1`. A key a
map does not hold is unset; a key holding null holds a value like any
other.

`member(document, value)` reads a node as it is written, once the
format accepts it: `empty` holds nothing and `any` everything; a choice
holds the scalars it lists; a text node the texts of its regular
language; a closed record the maps whose every key is one of its
fields, each set key's value in its field's node and each required key
set; a list node the lists of its item's values, of a length from `min`
to `max`; `union`, `inter` and `complement` (over every JSON value) are
or, and and not.

`find_by_enumeration(inside, outside)` looks for a value in every node
of `inside` and in no node of `outside` among `universe(nodes)`. The
universe holds, at each place of the question (the value itself, and
the value under each key a record there names, to any depth): every
constant a choice there lists; one value no choice lists and no node
there reads by its kind (the number 0.5); when a record stands there,
the maps that set each key a record there names or leave it unset, with
each value of the universe at that key's place, with and without one
key no record names; when a text node stands there, a shortest text in
each cell the languages of the text nodes and the listed texts there
cut the texts into; and when a list node
stands there, the empty list and the lists of one and two values of the
universe at the item's place.

When no node of the question is a text or a list node, the membership
of a value in every node depends only on its class at each place: which
listed constant it equals, if any (a choice compares by kind and then
by value); a value that equals none, and is not a map where a record
stands, is in one class with every other such value; and a map where a
record stands is in the class given by each named key, unset or the
class of its value there, and by whether some other key is set. The
universe holds one value of every class, so a question with a member
has one in it, and `none` is then a proof: the result says so
(`complete`). With a text or a list node the classes are not finite in
this way, and `none` says only that the universe holds no member.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from mathema import regular
from mathema.record_term import (KIND, VERSION, InvalidTerm, bounds, canonical, canonical_text,
                                 complement_of, inter_of, is_definition, list_of, record_of,
                                 term_hash, union_of, validate)

_BOUNDS = ("at_least", "at_most")
#: the most values `universe` builds at one place before it stops, the
#: result then not complete
LIMIT = 50_000
#: the longest text `universe` looks for in or outside a text node's language
TEXT_LIMIT = 24
#: the most regular languages at one place whose every cell `universe`
#: looks into
CELLS = 6


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


# ---- membership of one value -------------------------------------------

def _holds(node: dict, value) -> bool:
    op = node["op"]
    if op == "empty":
        return False
    if op == "any":
        return True
    if op == "choice":
        return _scalar_key(value) in [_scalar_key(v) for v in node["values"]]
    if op == "text":
        return isinstance(value, str) and regular.contains(node["language"], value)
    if op == "complement":
        return not _holds(node["arg"], value)
    if op == "union":
        return any(_holds(arg, value) for arg in node["args"])
    if op == "inter":
        return all(_holds(arg, value) for arg in node["args"])
    if op == "list":
        return (isinstance(value, list) and node["min"] <= len(value)
                and (node["max"] is None or len(value) <= node["max"])
                and all(_holds(node["item"], item) for item in value))
    if not isinstance(value, dict):
        return False
    named = {name for name, _, _ in node["fields"]}
    if any(key not in named for key in value):
        return False
    for name, inner, required in node["fields"]:
        if name in value:
            if not _holds(inner, value[name]):
                return False
        elif required:
            return False
    return True


def _written(document, bound: "str | None") -> dict:
    """The node a definition writes for `bound`, as written, once the
    format accepts the definition."""
    exact = document["exact"]
    bounds(document)
    if bound is None:
        if not exact:
            raise InvalidTerm("the definition is not exact: name its at_least or its at_most "
                              "bound")
        return document["language"]
    if bound not in _BOUNDS:
        raise InvalidTerm(f"a bound is at_least or at_most, not {bound!r}")
    return document["language"] if exact else document[bound]


def member(document, value, *, bound: "str | None" = None) -> bool:
    """Intent:
        Whether the JSON value `value` is in the language a definition
        states, or, with `bound` (`at_least` or `at_most`), in that
        bound of a definition that is not exact; a bare node (an object
        with an `op`) is read as the language it is. The node is read as
        it is written, once `mathema.record_term` accepts it.

    Raises:
        InvalidTerm: the format refuses the document or node, the bound
            is neither bound, or the definition is not exact and no
            bound is named.
    """
    if isinstance(document, dict) and "op" in document:
        canonical(document)
        return _holds(document, value)
    return _holds(_written(document, bound), value)


# ---- a member over a small universe -------------------------------------

@dataclass(frozen=True)
class Enumerated:
    """What `find_by_enumeration` found: `status` is `member` (with the
    value) or `none`; `complete` says whether `none` is a proof (no text
    or list node in the question, and the universe built in full)."""
    status: str
    member: object = None
    complete: bool = False


def _gather(node: dict, path: tuple, places: dict) -> None:
    """What the nodes standing at each place write: their constants, the
    names their records give, whether a text or a list node stands
    there, and the texts of its languages a value there could hold."""
    place = places.setdefault(path, {"constants": [], "names": set(), "open": False,
                                     "texts": [], "records": False})
    op = node["op"]
    if op == "choice":
        place["constants"].extend(node["values"])
    elif op == "text":
        place["open"] = True
        place["texts"].append(node["language"])
    elif op == "list":
        place["open"] = True
        _gather(node["item"], (*path, None), places)
    elif op == "complement":
        _gather(node["arg"], path, places)
    elif op in ("union", "inter"):
        for arg in node["args"]:
            _gather(arg, path, places)
    elif op == "record":
        place["records"] = True
        for name, inner, _ in node["fields"]:
            place["names"].add(name)
            _gather(inner, (*path, name), places)


def _texts_of(languages: list) -> list:
    """A shortest text, of at most `TEXT_LIMIT` characters, of each cell
    the regular `languages` cut the texts into: in some of them and
    outside the others, for every choice of which (each language alone
    when there are more than `CELLS` of them)."""
    document = {"kind": regular.KIND, "version": regular.VERSION,
                "alphabet": [[0, regular.MAX_CODE_POINT]], "exact": True}
    if len(languages) <= CELLS:
        signs = itertools.product((True, False), repeat=len(languages))
        cells = [[n if inside else {"op": "complement", "arg": n}
                  for n, inside in zip(languages, chosen)] for chosen in signs]
    else:
        cells = [[n] for n in languages] + [[{"op": "complement", "arg": n}] for n in languages]
    out = []
    for parts in cells:
        node = {"op": "inter", "args": parts} if parts else {"op": "epsilon"}
        found = regular.shortest_member({**document, "language": node}, limit=TEXT_LIMIT)
        if found is not None:
            out.append(found)
    return out


def _values_at(path: tuple, places: dict, limit: int) -> tuple:
    """`(values, complete)`: the universe at one place, and whether it
    was built in full with no text or list node standing there or below."""
    place = places.get(path, {"constants": [], "names": set(), "open": False, "texts": [],
                              "records": False})
    complete = not place["open"]
    seen: dict = {}

    def add(value):
        key = repr((type(value).__name__, value))
        seen.setdefault(key, value)
    for value in [*place["constants"], 0.5]:
        add(value)
    if place["texts"]:
        literals = [{"op": "literal", "codes": [ord(c) for c in v]}
                    for v in place["constants"] if isinstance(v, str)]
        for text in _texts_of(place["texts"] + literals):
            add(text)
    if (*path, None) in places:
        add([])
        items, _ = _values_at((*path, None), places, limit)
        for length in (1, 2):
            for chosen in itertools.islice(itertools.product(items, repeat=length), limit):
                add(list(chosen))
    names = sorted(place["names"])
    if not place["records"]:
        return list(seen.values()), complete
    per_key = []
    for name in names:
        under, inner_complete = _values_at((*path, name), places, limit)
        complete = complete and inner_complete
        per_key.append([_UNSET, *under])
    other = "\x00"
    while other in place["names"]:
        other += "\x00"
    count = 0
    for chosen in itertools.product(*per_key):
        for extra in (False, True):
            value = {name: v for name, v in zip(names, chosen) if v is not _UNSET}
            if extra:
                value[other] = None
            add(value)
            count += 1
            if count >= limit:
                return list(seen.values()), False
    return list(seen.values()), complete


_UNSET = object()


def universe(nodes) -> tuple:
    """Intent:
        `(values, complete)`: the universe of a question over `nodes`,
        as the module states it, and whether it is complete for them.

    Raises:
        InvalidTerm: the format refuses a node.
    """
    places: dict = {}
    for node in nodes:
        canonical(node)
        _gather(node, (), places)
    return _values_at((), places, LIMIT)


def find_by_enumeration(inside, outside=()) -> Enumerated:
    """Intent:
        A value of `universe(inside + outside)` in every node of
        `inside` and in no node of `outside`: `member` with the value,
        or `none`, complete when the universe is.

    Raises:
        InvalidTerm: the format refuses a node.
    """
    inside, outside = list(inside), list(outside)
    values, complete = universe(inside + outside)
    for value in values:
        if all(_holds(n, value) for n in inside) and not any(_holds(n, value) for n in outside):
            return Enumerated("member", value, complete)
    return Enumerated("none", None, complete)


__all__ = ["Enumerated", "InvalidTerm", "KIND", "CELLS", "LIMIT", "TEXT_LIMIT", "VERSION", "bounds", "canonical",
           "canonical_text", "complement_of", "find_by_enumeration", "inter_of",
           "is_definition", "list_of", "member", "record_of", "term_hash", "union_of",
           "universe", "validate"]
