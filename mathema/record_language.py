# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Record-language terms: the solver-neutral definition a language of
JSON values states, and the one question asked about such terms.

A definition is a plain JSON document shaped as a regular-language
definition is: `{"kind": "record_language", "version": 1, "exact":
bool, ...}`. An exact definition carries its language under `language`;
one that is not exact carries two bounds in its place, `at_least` (a
language holding every member) and `at_most` (a language holding only
members). `source` is provenance and no part of the meaning:
`term_hash` reads the version, the exact flag and the nodes, in
canonical form, and nothing else.

The values a language is of are the JSON values: null, the two
booleans, numbers, texts, lists, and maps from text keys to values. A
boolean is never a number, and a number is read by its value, so `1`
and `1.0` are one value. A key a map does not hold is unset; a key
holding null holds a value like any other.

A language is a node keyed by `op`:

- `empty`, no value, and `any`, every value;
- `choice`, exactly the scalar `values` listed (null, a boolean, a whole
  number, a text);
- `text`, the texts in the language of a regular-language node
  (`mathema.regular`), under `language`;
- `record`, the maps whose every key is one of its `fields`, each
  written `[name, node, required]`: a key that is set holds a value of
  its node, and a required key is set. `rest` is the language of the
  value under any other key; this version reads `empty` there only, a
  closed record;
- `union`, `inter` and `complement`, the last over every JSON value.

Lists, numbers that are not whole and maps with other keys are values no
node of this version tells apart from one another: they are members of
`any` and of a complement, and of no choice, text or record.

`find_member` asks whether some value lies inside every one of a list
of nodes and outside every one of another, which is how inclusion,
equality and disjointness of two languages are all decided. The `z3`
dependency is the optional `mathema[smt]` extra.
"""
from __future__ import annotations

import hashlib
import json

from . import regular
from .regular import Found, InvalidTerm

KIND = "record_language"
VERSION = 1

_EMPTY = {"op": "empty"}
_ANY = {"op": "any"}
#: the keys each operation's node holds beside `op`, and no others
_NODE_KEYS = {"empty": (), "any": (), "choice": ("values",), "text": ("language",),
              "record": ("fields", "rest"), "union": ("args",), "inter": ("args",),
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
    keys, no white space, ASCII only."""
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


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
        6. `complement`, `empty` and `any` are kept as they are.

        The rules read the form and not the meaning: two nodes with the
        same members may have two canonical forms.

    Raises:
        InvalidTerm: the node is not of the schema: an unknown `op`,
            keys other than the operation's own, a choice value that is
            no scalar, a field not written `[name, node, required]`, a
            name twice, or a `rest` other than `empty`.
    """
    if not isinstance(node, dict) or node.get("op") not in _NODE_KEYS:
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
            keys.append(key)
        values = [json.loads(text) for text in sorted({_serial(key[1]) for key in keys})]
        return {"op": "choice", "values": values} if values else dict(_EMPTY)
    if op == "text":
        language = _regular_canonical(node["language"])
        return dict(_EMPTY) if language == {"op": "empty"} else {"op": "text", "language": language}
    if op == "complement":
        return {"op": "complement", "arg": canonical(node["arg"])}
    if op == "record":
        return _canonical_record(node)
    if not isinstance(node["args"], list):
        raise InvalidTerm(f"the args of a {op} are a list")
    args: list = []
    for arg in map(canonical, node["args"]):
        args.extend(arg["args"] if arg["op"] == op else [arg])
    absorbing, unit = (_ANY, _EMPTY) if op == "union" else (_EMPTY, _ANY)
    if absorbing in args:
        return dict(absorbing)
    kept = [json.loads(text) for text in sorted({_serial(a) for a in args if a != unit})]
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
        fields.append([field[0], canonical(field[1]), field[2]])
    names = [name for name, _, _ in fields]
    if len(set(names)) != len(names):
        raise InvalidTerm(f"a record names a field once, not {sorted(names)}")
    if any(required and value == _EMPTY for _, value, required in fields):
        return dict(_EMPTY)
    return {"op": "record", "fields": sorted(fields, key=lambda f: f[0]), "rest": dict(_EMPTY)}


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
        return isinstance(value, str) and regular.node_member(node["language"], value)
    if op == "complement":
        return not _holds(node["arg"], value)
    if op == "union":
        return any(_holds(arg, value) for arg in node["args"])
    if op == "inter":
        return all(_holds(arg, value) for arg in node["args"])
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


def member(document, value, *, bound: "str | None" = None) -> bool:
    """Intent:
        Whether the JSON value `value` is in the language a definition
        states, or, with `bound` (`at_least` or `at_most`), in that
        bound of a definition that is not exact. No solver is asked. A
        bare node (an object with an `op`) is read as the language it
        is.

    Raises:
        InvalidTerm: the document is not a definition of this kind and
            version, the bound is neither bound, or the definition is
            not exact and no bound is named.
    """
    if isinstance(document, dict) and "op" in document:
        return _holds(canonical(document), value)
    exact, at_most, at_least = _read(document)
    if bound is None:
        if not exact:
            raise InvalidTerm("the definition is not exact: name its at_least or its at_most "
                              "bound")
        return _holds(at_most, value)
    if bound not in _BOUNDS:
        raise InvalidTerm(f"a bound is at_least or at_most, not {bound!r}")
    return _holds(at_least if bound == "at_least" else at_most, value)


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


# ---- lowering to z3 ---------------------------------------------------

#: the kinds of value a solver variable may be; the last stands for every
#: value no node of this version tells apart: a list, a number that is
#: not whole
_KINDS = ("null", "boolean", "number", "text", "map", "other")
#: a key no field of the question carries
_OTHER_KEY = "\x00"


class _Value:
    """One value of the question as solver variables: its kind, the
    boolean, whole number or text it is when of that kind, and, when a
    map, for each field name the question uses at this place whether
    the key is set and the value under it, and whether it holds a key
    that is no such name."""

    def __init__(self, z3, path: str) -> None:
        self.z3, self.path = z3, path
        self.kind = z3.Int(f"{path} kind")
        self.boolean = z3.Bool(f"{path} boolean")
        self.number = z3.Int(f"{path} number")
        self.text = z3.String(f"{path} text")
        self.other_key = z3.Bool(f"{path} other key")
        self.keys: dict = {}

    def is_(self, kind: str):
        return self.kind == _KINDS.index(kind)

    def key(self, name: str) -> tuple:
        if name not in self.keys:
            self.keys[name] = (self.z3.Bool(f"{self.path}.{name} set"),
                               _Value(self.z3, f"{self.path}.{name}"))
        return self.keys[name]


def _texts(node: dict, into: list) -> None:
    """Every regular-language node a record-language node reads a text
    by: the language of each `text` node and the literal of each text a
    `choice` lists."""
    op = node["op"]
    if op == "text":
        into.append(node["language"])
    elif op == "choice":
        into.extend(_literal(v) for v in node["values"] if isinstance(v, str))
    elif op == "complement":
        _texts(node["arg"], into)
    elif op in ("union", "inter"):
        for arg in node["args"]:
            _texts(arg, into)
    elif op == "record":
        for _, inner, _ in node["fields"]:
            _texts(inner, into)


def _literal(text: str) -> dict:
    return regular.canonical({"op": "literal", "codes": [ord(c) for c in text]})


def _names(node: dict, into: dict, path: tuple = ()) -> None:
    """The field names record nodes use at each place: `into[path]` is
    the set of names of the records that may stand at `path`."""
    op = node["op"]
    if op == "record":
        for name, inner, _ in node["fields"]:
            into.setdefault(path, set()).add(name)
            _names(inner, into, (*path, name))
    elif op == "complement":
        _names(node["arg"], into, path)
    elif op in ("union", "inter"):
        for arg in node["args"]:
            _names(arg, into, path)


class _Lowering:
    """One question's nodes as formulas over one value."""

    def __init__(self, z3, nodes: list) -> None:
        self.z3 = z3
        texts: list = []
        self.names: dict = {}
        for node in nodes:
            _texts(node, texts)
            _names(node, self.names)
        self.texts = regular._Lowering(z3, [[0, regular.MAX_CODE_POINT]], texts)
        self.root = _Value(z3, "value")
        self.shape: list = []
        self._shaped(self.root, ())

    def _shaped(self, value: _Value, path: tuple) -> None:
        """Every variable a model must give a meaning to: a kind that
        is one of the kinds, a text over the question's symbols, and
        the same of the value under each name used at this place."""
        z3 = self.z3
        self.shape.append(z3.And(value.kind >= 0, value.kind < len(_KINDS)))
        self.shape.append(z3.InRe(value.text, self.texts.everything))
        for name in sorted(self.names.get(path, ())):
            _, inner = value.key(name)
            self._shaped(inner, (*path, name))

    def holds(self, node: dict, value: _Value, path: tuple = ()):
        z3, op = self.z3, node["op"]
        if op == "empty":
            return z3.BoolVal(False)
        if op == "any":
            return z3.BoolVal(True)
        if op == "choice":
            return z3.Or(*[self._is(value, v) for v in node["values"]])
        if op == "text":
            return z3.And(value.is_("text"), z3.InRe(value.text, self.texts.regex(node["language"])))
        if op == "complement":
            return z3.Not(self.holds(node["arg"], value, path))
        if op in ("union", "inter"):
            parts = [self.holds(arg, value, path) for arg in node["args"]]
            return (z3.Or if op == "union" else z3.And)(*parts)
        own = {name: (inner, required) for name, inner, required in node["fields"]}
        parts = [value.is_("map"), z3.Not(value.other_key)]
        for name in sorted(self.names.get(path, ())):
            is_set, under = value.key(name)
            if name not in own:
                parts.append(z3.Not(is_set))
                continue
            inner, required = own[name]
            inside = self.holds(inner, under, (*path, name))
            parts.append(z3.And(is_set, inside) if required else z3.Implies(is_set, inside))
        return z3.And(*parts)

    def _is(self, value: _Value, constant):
        z3 = self.z3
        if constant is None:
            return value.is_("null")
        if isinstance(constant, bool):
            return z3.And(value.is_("boolean"), value.boolean == constant)
        if isinstance(constant, int):
            return z3.And(value.is_("number"), value.number == constant)
        return z3.And(value.is_("text"), z3.InRe(value.text, self.texts.regex(_literal(constant))))

    def read(self, model, value: "_Value | None" = None, path: tuple = ()):
        """The JSON value a model gives the question's value."""
        value = self.root if value is None else value
        kind = _KINDS[model.eval(value.kind, model_completion=True).as_long()]
        if kind == "null":
            return None
        if kind == "boolean":
            return bool(model.eval(value.boolean, model_completion=True))
        if kind == "number":
            return model.eval(value.number, model_completion=True).as_long()
        if kind == "text":
            return self.texts.decode(model.eval(value.text, model_completion=True).as_string())
        if kind == "other":
            return []
        out = {}
        for name in sorted(self.names.get(path, ())):
            is_set, under = value.key(name)
            if bool(model.eval(is_set, model_completion=True)):
                out[name] = self.read(model, under, (*path, name))
        if bool(model.eval(value.other_key, model_completion=True)):
            out[_OTHER_KEY] = None
        return out


def find_member(inside, outside, *, timeout_ms: int = 5000) -> Found:
    """Intent:
        A JSON value that every node in `inside` holds and no node in
        `outside` holds: `member` with the value, `none` when no such
        value exists, or `unknown` with the reason.

    Raises:
        InvalidTerm: a node is not of the schema.

    Notes:
        `none` is a proof for this version's nodes: no node tells apart
        two values the solver's value stands for alike. A value the
        solver gives is returned only when `member` places it inside
        and outside as asked; otherwise the answer is `unknown`.
    """
    inside = [canonical(n) for n in inside]
    outside = [canonical(n) for n in outside]
    try:
        import z3
    except ImportError:
        return Found("unknown", reason="z3 is not installed (the mathema[smt] extra)")
    lowering = _Lowering(z3, inside + outside)
    solver = z3.Solver()
    solver.set("timeout", int(timeout_ms))
    solver.add(*lowering.shape)
    for node in inside:
        solver.add(lowering.holds(node, lowering.root))
    for node in outside:
        solver.add(z3.Not(lowering.holds(node, lowering.root)))
    import threading
    watchdog = threading.Timer(timeout_ms / 1000.0 + 1.0, solver.ctx.interrupt)
    watchdog.daemon = True
    watchdog.start()
    try:
        outcome = solver.check()
    finally:
        watchdog.cancel()
    if outcome == z3.unsat:
        return Found("none")
    if outcome != z3.sat:
        return Found("unknown", reason=f"z3 gave no answer within {timeout_ms} ms "
                                       f"({solver.reason_unknown()})")
    value = lowering.read(solver.model())
    if all(_holds(n, value) for n in inside) and not any(_holds(n, value) for n in outside):
        return Found("member", member=value)
    return Found("unknown", reason=f"the solver's value {value!r} is not placed by member as "
                                   f"asked")


__all__ = ["Found", "InvalidTerm", "KIND", "VERSION", "bounds", "canonical", "canonical_text",
           "complement_of", "find_member", "inter_of", "is_definition", "member", "record_of",
           "term_hash", "union_of", "validate"]
