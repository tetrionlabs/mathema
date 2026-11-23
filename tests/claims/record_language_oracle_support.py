# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about the record-language oracle are stated over.

Each takes whole numbers a claim can quantify: indices into `TERMS`, a
fixed catalogue of record-language nodes (every node kind, nested
records, optional and required fields, shapes of a nested configuration record),
into `VALUES`, a fixed catalogue of JSON values (scalars, texts with and
without a trailing newline, maps with missing, extra and wrong-kind
keys, a list, a number that is not whole), and into `DOCUMENTS`,
definitions exact and not. Each returns the truth of one statement
about the module, so a claim reads `f(t, v) == True`.

The oracle is `tests/_record_language_oracle.py`, loaded here from its
file, so the claims are checked against the module in this tree and the
`mathema.regular` the run imports. `generated_term` and
`generated_value` draw further terms and values from a seed, for the
same statements over more than the catalogue."""
from __future__ import annotations

import importlib
import importlib.util
import json
import random
import sys
from pathlib import Path

_ORACLE = Path(__file__).resolve().parent.parent / "_record_language_oracle.py"


def _load():
    """The oracle module in `tests/_record_language_oracle.py`, loaded
    once from its file."""
    name = "record_language_oracle"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, _ORACLE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _rl():
    return _load()


# ---- the catalogues ----------------------------------------------------

def _lit(text: str) -> dict:
    return {"op": "literal", "codes": [ord(c) for c in text]}


def _chars(*spans: str) -> dict:
    return {"op": "chars", "ranges": [[ord(s[0]), ord(s[-1])] for s in spans]}


def _rep(node: dict, lo: int, hi: "int | None") -> dict:
    return {"op": "repeat", "arg": node, "min": lo, "max": hi}


#: the texts `/wt` and `/wt/<name>` and so on, and the same under `/wt/task-7`
_SEGMENT = {"op": "concat", "args": [_lit("/"), _rep(_chars("az", "09", "--"), 1, None)]}
SHALLOW = {"op": "concat", "args": [_lit("/wt"), _rep(_SEGMENT, 0, None)]}
DEEP = {"op": "concat", "args": [_lit("/wt/task-7"), _rep(_SEGMENT, 0, None)]}
#: a pattern ending in `$`: the text, or the text and one newline
DOLLAR = {"op": "concat", "args": [_lit("a"), _rep(_lit("\n"), 0, 1)]}

EMPTY = {"op": "empty"}
ANY = {"op": "any"}


def choice(*values) -> dict:
    return {"op": "choice", "values": list(values)}


def text(language: dict) -> dict:
    return {"op": "text", "language": language}


def record(*fields) -> dict:
    return {"op": "record", "fields": [list(f) for f in fields], "rest": {"op": "empty"}}


def union(*args) -> dict:
    return {"op": "union", "args": list(args)}


def inter(*args) -> dict:
    return {"op": "inter", "args": list(args)}


def complement(arg: dict) -> dict:
    return {"op": "complement", "arg": arg}


FLAG = choice(True, False)
OFF = choice(False)
_CHILD_SHELL = record(("git", choice("status", "diff"), True))
_PARENT_SHELL = record(("git", choice("status", "diff", "commit"), True))
#: a nested configuration record, a wider one, and the child with `publish` widened
CHILD = record(("edit", FLAG, True), ("publish", OFF, True), ("root", text(DEEP), True),
               ("shell", _CHILD_SHELL, False))
PARENT = record(("edit", FLAG, True), ("publish", FLAG, True), ("root", text(SHALLOW), True),
                ("shell", _PARENT_SHELL, False))
WIDENED = record(("edit", FLAG, True), ("publish", FLAG, True), ("root", text(DEEP), True),
                 ("shell", _CHILD_SHELL, False))

#: an astral character written as the two surrogates that encode it in UTF-16
_PAIR = chr(0xD83D) + chr(0xDE00)

TERMS = [
    EMPTY, ANY, choice(None), choice(True), FLAG, choice(1), choice(1, True, "1"),
    choice("a", "b"), choice(), text(_lit("a")), text(DOLLAR), text(SHALLOW), text(DEEP),
    text({"op": "empty"}),
    record(), record(("x", FLAG, True)), record(("x", FLAG, False)),
    record(("x", EMPTY, True)), record(("x", EMPTY, False)),
    record(("x", FLAG, True), ("y", choice("a", "b"), False)),
    record(("y", choice("a"), False), ("x", OFF, True)),
    record(("x", record(("z", choice(None, 0), True)), True)),
    union(choice("a"), FLAG), inter(FLAG, choice(True, 1)), union(), inter(),
    complement(FLAG), complement(record(("x", FLAG, True))), complement(complement(text(DOLLAR))),
    union(record(("x", OFF, True)), complement(record(("x", FLAG, True)))),
    CHILD, PARENT, WIDENED,
    # field names a path-like reading of names would confuse, and a
    # character outside the basic plane
    record(("a.b", choice(1), True), ("a", record(("b", choice(2), True)), True)),
    record(("x[0]", choice(4), True),
           ("x", {"op": "list", "item": choice(3), "min": 1, "max": 1}, True)),
    record(("\x00", FLAG, True), ("", choice(1), False)),
    choice("\U0001F600", "a"),
]

VALUES = [
    None, True, False, 0, 1, 1.0, 2, -1, 1.5, "", "a", "a\n", "b", "1", "/wt", "/wt/task-7",
    "/wt/task-7/src", "/wt/other", "/wt/task-7\n", [], [True], {}, {"x": True}, {"x": False},
    {"x": None}, {"x": 1}, {"x": True, "y": "a"}, {"x": False, "y": "c"}, {"y": "a"},
    {"x": True, "w": 1}, {"x": {"z": None}}, {"x": {"z": 0}}, {"x": {}}, {"x": [True]},
    {"edit": True, "publish": False, "root": "/wt/task-7/src"},
    {"edit": False, "publish": False, "root": "/wt/task-7", "shell": {"git": "diff"}},
    {"edit": True, "publish": True, "root": "/wt/task-7"},
    {"edit": True, "publish": False, "root": "/wt/elsewhere", "shell": {"git": "commit"}},
    {"edit": True, "publish": False, "root": "/etc"},
    {"edit": True, "publish": False},
    {"a.b": 1, "a": {"b": 2}}, {"a.b": 2, "a": {"b": 1}}, {"x[0]": 4, "x": [3]},
    {"\x00": True}, {"\x00": False, "": 1}, "\U0001F600", _PAIR,
]


def _exact(node: dict, **more) -> dict:
    return {"kind": "record_language", "version": 1, "exact": True, "language": node, **more}


def _pair(at_least: dict, at_most: dict) -> dict:
    return {"kind": "record_language", "version": 1, "exact": False, "at_least": at_least,
            "at_most": at_most}


#: definitions: exact ones, and pairs whose at_most lies inside their at_least
DOCUMENTS = [_exact(t) for t in (FLAG, text(DOLLAR), record(("x", FLAG, True)), CHILD, ANY, EMPTY)] + [
    _pair(text(DOLLAR), text(_lit("a"))),
    _pair(record(("r", text(DOLLAR), True)), record(("r", text(_lit("a")), True))),
    _pair(ANY, EMPTY),
    _pair(union(FLAG, choice("a")), OFF),
]

VALID = [_exact(t) for t in TERMS] + DOCUMENTS + [
    _exact(FLAG, source={"written": "by hand"}),
    {"kind": "other", "version": 1, "exact": True, "language": FLAG},
    {"kind": "record_language", "version": 2, "exact": True, "language": FLAG},
]

INVALID = [
    None, [], {}, {"language": FLAG},
    {**_exact(FLAG), "version": True}, {**_exact(FLAG), "version": "1"},
    {**_exact(FLAG), "exact": 1},
    {**_exact(FLAG), "exact": False},
    {**_exact(FLAG), "at_least": FLAG, "at_most": FLAG},
    {**_pair(FLAG, FLAG), "language": FLAG},
    {**_pair(FLAG, FLAG), "exact": True},
    {k: v for k, v in _pair(FLAG, FLAG).items() if k != "at_most"},
    _exact({"op": "set"}), _exact({"op": "empty", "extra": 1}), _exact({"values": [1]}),
    _exact({"op": "choice", "values": (1, 2)}), _exact({"op": "choice", "values": [1.5]}),
    _exact({"op": "choice", "values": [[1]]}), _exact({"op": "choice", "values": [{"a": 1}]}),
    _exact({"op": "choice", "values": [float("nan")]}),
    _exact({"op": "text", "language": {"op": "chars", "ranges": [[5, 1]]}}),
    _exact({"op": "text", "language": FLAG}),
    _exact({"op": "record", "fields": [["x", FLAG, True]]}),
    _exact({"op": "record", "fields": [["x", FLAG, True]], "rest": {"op": "any"}}),
    _exact({"op": "record", "fields": [["x", FLAG, True], ["x", OFF, True]], "rest": EMPTY}),
    _exact({"op": "record", "fields": [["x", FLAG, 1]], "rest": EMPTY}),
    _exact({"op": "record", "fields": [[1, FLAG, True]], "rest": EMPTY}),
    _exact({"op": "record", "fields": [["x", FLAG]], "rest": EMPTY}),
    _exact({"op": "record", "fields": {"x": FLAG}, "rest": EMPTY}),
    _exact({"op": "union", "args": FLAG}), _exact({"op": "union", "args": [FLAG, 1]}),
    _exact({"op": "complement", "args": [FLAG]}),
    _exact(choice(_PAIR)), _exact(record((_PAIR, FLAG, True))),
    _exact({"op": "choice", "values": [10 ** 5000]}), _exact({"op": ["choice"], "values": [1]}),
]


def _m(t: int, v: int) -> bool:
    return _rl().member(TERMS[int(t)], VALUES[int(v)])


def _members(node: dict) -> list:
    return [v for v in VALUES if _rl().member(node, v)]


# ---- validate ----------------------------------------------------------

def valid_is_accepted(i: int) -> bool:
    """Whether `validate` accepts the valid document `i`, before and
    after its nodes are made canonical."""
    rl, document = _rl(), VALID[int(i)]
    rl.validate(document)
    again = {**document, **{k: rl.canonical(document[k]) for k in ("language", "at_least", "at_most")
                            if k in document}}
    rl.validate(again)
    return True


def invalid_is_refused(i: int) -> bool:
    """Whether `validate`, `canonical_text` and `term_hash` each refuse
    the malformed document `i` with `InvalidTerm`."""
    rl = _rl()
    for read in (rl.validate, rl.canonical_text, rl.term_hash):
        try:
            read(INVALID[int(i)])
        except rl.InvalidTerm:
            continue
        return False
    return True


def is_definition_reads_kind_and_version(i: int) -> bool:
    """Whether `is_definition` is true of the valid document `i` exactly
    when it states this kind and this version."""
    rl, document = _rl(), VALID[int(i)]
    return rl.is_definition(document) == (document["kind"] == "record_language"
                                          and document["version"] == 1)


# ---- canonical ---------------------------------------------------------

def canonical_is_idempotent(t: int) -> bool:
    rl = _rl()
    once = rl.canonical(TERMS[int(t)])
    return rl.canonical(once) == once


def canonical_keeps_membership(t: int, v: int) -> bool:
    rl = _rl()
    return rl.member(rl.canonical(TERMS[int(t)]), VALUES[int(v)]) == _m(t, v)


def canonical_ignores_order_and_repetition(t: int, u: int) -> bool:
    """Whether a union and an intersection of terms `t` and `u` have
    the canonical form of the same written the other way round, and
    whether a term united or met with itself is the term."""
    rl, a, b = _rl(), TERMS[int(t)], TERMS[int(u)]
    return (rl.canonical(union(a, b)) == rl.canonical(union(b, a))
            and rl.canonical(inter(a, b)) == rl.canonical(inter(b, a))
            and rl.canonical(union(a, a)) == rl.canonical(a)
            and rl.canonical(inter(a, a)) == rl.canonical(a))


def canonical_has_its_units(t: int) -> bool:
    """Whether uniting term `t` with `empty` or meeting it with `any`
    gives the term, uniting it with `any` gives `any`, and meeting it
    with `empty` gives `empty`."""
    rl, a = _rl(), TERMS[int(t)]
    form = rl.canonical(a)
    return (rl.canonical(union(a, EMPTY)) == form and rl.canonical(inter(a, ANY)) == form
            and rl.canonical(union(a, ANY)) == ANY and rl.canonical(inter(a, EMPTY)) == EMPTY)


def canonical_ignores_field_order(t: int) -> bool:
    """Whether a record with its fields written in the reverse order has
    the canonical form of the record as written (true of every term that
    is no record)."""
    rl, a = _rl(), TERMS[int(t)]
    if a["op"] != "record":
        return True
    return rl.canonical({**a, "fields": a["fields"][::-1]}) == rl.canonical(a)


def a_required_empty_field_empties_the_record(t: int) -> bool:
    """Whether a record requiring a field that holds term `t` is `empty`
    in canonical form exactly when the term's canonical form is, and the
    same record with the field optional never is."""
    rl, a = _rl(), TERMS[int(t)]
    gone = rl.canonical(a) == EMPTY
    return ((rl.canonical(record(("k", a, True))) == EMPTY) == gone
            and rl.canonical(record(("k", a, False))) != EMPTY)


def complement_is_left_as_written(t: int) -> bool:
    """Whether the canonical form of a complement is the complement of
    the argument's canonical form, nothing folded."""
    rl, a = _rl(), TERMS[int(t)]
    return rl.canonical(complement(a)) == complement(rl.canonical(a))


# ---- canonical_text and term_hash --------------------------------------

def hash_is_the_canonical_text(t: int, u: int) -> bool:
    """Whether terms `t` and `u` have one hash exactly when they have
    one canonical text."""
    rl, a, b = _rl(), _exact(TERMS[int(t)]), _exact(TERMS[int(u)])
    return (rl.term_hash(a) == rl.term_hash(b)) == (rl.canonical_text(a) == rl.canonical_text(b))


def hash_reads_neither_kind_nor_source(t: int) -> bool:
    rl, a = _rl(), TERMS[int(t)]
    return (rl.term_hash(_exact(a)) == rl.term_hash(_exact(a, source={"note": "x"}))
            == rl.term_hash({**_exact(a), "kind": "other"}))


def canonical_text_reads_back(t: int) -> bool:
    """Whether the canonical text of term `t` is ASCII and reads back as
    the version, the exact flag and the canonical node."""
    rl, a = _rl(), TERMS[int(t)]
    written = rl.canonical_text(_exact(a))
    return written.isascii() and json.loads(written) == {
        "version": 1, "exact": True, "language": rl.canonical(a)}


def exact_is_in_the_meaning(t: int) -> bool:
    """Whether the exact definition of term `t` and the pair with both
    bounds equal to it have different hashes."""
    rl, a = _rl(), TERMS[int(t)]
    return rl.term_hash(_exact(a)) != rl.term_hash(_pair(a, a))


# ---- member ------------------------------------------------------------

def complement_holds_what_the_term_does_not(t: int, v: int) -> bool:
    return _rl().member(complement(TERMS[int(t)]), VALUES[int(v)]) == (not _m(t, v))


def double_complement_is_the_term(t: int, v: int) -> bool:
    return _rl().member(complement(complement(TERMS[int(t)])), VALUES[int(v)]) == _m(t, v)


def union_holds_what_either_does(t: int, u: int, v: int) -> bool:
    return _rl().member(union(TERMS[int(t)], TERMS[int(u)]), VALUES[int(v)]) == (_m(t, v) or _m(u, v))


def inter_holds_what_both_do(t: int, u: int, v: int) -> bool:
    return _rl().member(inter(TERMS[int(t)], TERMS[int(u)]), VALUES[int(v)]) == (_m(t, v) and _m(u, v))


def de_morgan(t: int, u: int, v: int) -> bool:
    rl, a, b, value = _rl(), TERMS[int(t)], TERMS[int(u)], VALUES[int(v)]
    return (rl.member(complement(union(a, b)), value)
            == rl.member(inter(complement(a), complement(b)), value)
            and rl.member(complement(inter(a, b)), value)
            == rl.member(union(complement(a), complement(b)), value))


def empty_holds_nothing_and_any_everything(v: int) -> bool:
    rl, value = _rl(), VALUES[int(v)]
    return not rl.member(EMPTY, value) and rl.member(ANY, value)


def a_choice_holds_its_values_by_kind(v: int) -> bool:
    """Whether value `v` is in the choice of `True` alone exactly when
    it is `True`, in the choice of `1` alone exactly when it is the
    number one (so `1.0` is and `True` is not), and in the choice of
    the text `1` exactly when it is that text."""
    rl, value = _rl(), VALUES[int(v)]
    number = isinstance(value, (int, float)) and not isinstance(value, bool) and value == 1
    return (rl.member(choice(True), value) == (value is True)
            and rl.member(choice(1), value) == number
            and rl.member(choice("1"), value) == (isinstance(value, str) and value == "1"))


def a_closed_record_refuses_another_key(t: int, v: int) -> bool:
    """Whether value `v` with one more key, a name no term uses, is
    outside term `t` when the term is a record (true of every other
    term and of every value that is no map)."""
    a, value = TERMS[int(t)], VALUES[int(v)]
    if a["op"] != "record" or not isinstance(value, dict):
        return True
    return not _rl().member(a, {**value, "no such field": None})


def an_optional_key_may_be_unset_a_required_one_not(t: int, v: int) -> bool:
    """Whether, for a record term `t` and a member `v` of it, taking out
    an optional key gives a member and taking out a required key does
    not (true where the term is no record or the value no member)."""
    rl, a, value = _rl(), TERMS[int(t)], VALUES[int(v)]
    if a["op"] != "record" or not isinstance(value, dict) or not rl.member(a, value):
        return True
    for name, _, required in a["fields"]:
        if name in value:
            without = {k: x for k, x in value.items() if k != name}
            if rl.member(a, without) == required:
                return False
    return True


def null_is_a_value_not_absence(t: int) -> bool:
    """Whether a record with one optional field holding term `t` admits
    the map with the key unset, and admits the key holding `None`
    exactly when the term holds `None`."""
    rl, a = _rl(), TERMS[int(t)]
    one = record(("k", a, False))
    return rl.member(one, {}) and rl.member(one, {"k": None}) == rl.member(a, None)


def a_record_is_monotone_in_a_field(t: int, u: int, v: int) -> bool:
    """Whether, when every catalogue member of term `t` is a member of
    term `u`, the record with a required field in `t` holding value `v`
    under that key is also in the record with the field in `u`."""
    rl, a, b = _rl(), TERMS[int(t)], TERMS[int(u)]
    if any(not rl.member(b, x) for x in _members(a)):
        return True
    value = {"k": VALUES[int(v)]}
    return not rl.member(record(("k", a, True)), value) or rl.member(record(("k", b, True)), value)


def a_text_node_holds_the_texts_of_its_language(v: int) -> bool:
    """Whether value `v` is in each text node of the catalogue exactly
    when it is a text the regular term's own matcher holds."""
    rl, regular, value = _rl(), importlib.import_module("mathema.regular"), VALUES[int(v)]
    return all(rl.member(text(n), value) == (isinstance(value, str) and regular.contains(n, value))
               for n in (_lit("a"), DOLLAR, SHALLOW, DEEP))


def the_universe_is_every_json_value(t: int) -> bool:
    """Whether a list and a number that is not whole are members of
    `any` and of the complement of term `t`, whenever they are not
    members of the term, and never of a choice, a text or a record."""
    rl, a = _rl(), TERMS[int(t)]
    for value in ([], [True], 1.5):
        if not rl.member(ANY, value) or rl.member(complement(a), value) == rl.member(a, value):
            return False
        if a["op"] in ("choice", "text", "record") and rl.member(a, value):
            return False
    return True


def a_bound_must_be_named(d: int, v: int) -> bool:
    """Whether `member` of definition `d` answers without a bound exactly
    when the definition is exact, refusing with `InvalidTerm` otherwise,
    and whether a member under `at_most` is a member under `at_least`."""
    rl, document, value = _rl(), DOCUMENTS[int(d)], VALUES[int(v)]
    try:
        rl.member(document, value)
        answered = True
    except rl.InvalidTerm:
        answered = False
    if answered != document["exact"]:
        return False
    return not rl.member(document, value, bound="at_most") or rl.member(document, value, bound="at_least")


# ---- the document constructors -----------------------------------------

def _within(narrow: dict, wide: dict) -> bool:
    rl = _rl()
    return all(rl.member(wide, v) for v in VALUES if rl.member(narrow, v))


def complement_of_swaps_the_bounds(d: int, v: int) -> bool:
    """Whether the complement of definition `d` holds value `v` under
    `at_least` exactly when the definition does not hold it under
    `at_most`, and under `at_most` exactly when not under `at_least`;
    and whether it is exact exactly when the definition is."""
    rl, document, value = _rl(), DOCUMENTS[int(d)], VALUES[int(v)]
    turned = rl.complement_of(document)
    return (turned["exact"] == document["exact"]
            and rl.member(turned, value, bound="at_least") == (not rl.member(document, value, bound="at_most"))
            and rl.member(turned, value, bound="at_most") == (not rl.member(document, value, bound="at_least")))


def constructors_keep_at_most_inside_at_least(d: int, e: int) -> bool:
    """Whether the union, the intersection and a record of definitions
    `d` and `e`, and the complement of each, have every catalogue member
    of their `at_most` in their `at_least`, and are exact when both are."""
    rl, a, b = _rl(), DOCUMENTS[int(d)], DOCUMENTS[int(e)]
    built = [rl.union_of(a, b), rl.inter_of(a, b), rl.complement_of(a),
             rl.record_of([("p", a, True), ("q", b, False)])]
    for document in built:
        rl.validate(document)
        at_most, at_least = rl.bounds(document)
        if not _within(at_most, at_least):
            return False
        if document["exact"] != (a["exact"] and (b["exact"] or document is built[2])):
            return False
    return True


def constructors_mean_what_the_nodes_mean(d: int, e: int, v: int) -> bool:
    """Whether, under each bound, the union of definitions `d` and `e`
    holds value `v` exactly when one of them does and the intersection
    exactly when both do."""
    rl, a, b, value = _rl(), DOCUMENTS[int(d)], DOCUMENTS[int(e)], VALUES[int(v)]
    for bound in ("at_least", "at_most"):
        x, y = rl.member(a, value, bound=bound), rl.member(b, value, bound=bound)
        if rl.member(rl.union_of(a, b), value, bound=bound) != (x or y):
            return False
        if rl.member(rl.inter_of(a, b), value, bound=bound) != (x and y):
            return False
    return True


#: nodes whose canonical text shows the order of keys and the escaping of text
_WRITTEN = [
    (choice("b", "a"), '{"exact":true,"language":{"op":"choice","values":["a","b"]},"version":1}'),
    (choice("\u00e9"), '{"exact":true,"language":{"op":"choice","values":["\\u00e9"]},"version":1}'),
    (choice("\ud800"), '{"exact":true,"language":{"op":"choice","values":["\\ud800"]},"version":1}'),
    (record(("b", FLAG, False), ("a", OFF, True)),
     '{"exact":true,"language":{"fields":[["a",{"op":"choice","values":[false]},true],'
     '["b",{"op":"choice","values":[false,true]},false]],"op":"record","rest":{"op":"empty"}},'
     '"version":1}'),
]

#: documents whose lists are written as tuples, which JSON cannot carry
_TUPLES = [
    _exact({"op": "union", "args": (FLAG, OFF)}),
    _exact({"op": "inter", "args": (FLAG,)}),
    _exact({"op": "record", "fields": (["x", FLAG, True],), "rest": EMPTY}),
    _exact({"op": "record", "fields": [("x", FLAG, True)], "rest": EMPTY}),
    _exact({"op": "choice", "values": (1, 2)}),
]


def canonical_text_is_written_one_way(i: int) -> bool:
    """Whether the canonical text of written node `i` is, character for
    character, the text stated for it: keys in sorted order, no white
    space, every character outside ASCII escaped."""
    node, written = _WRITTEN[int(i)]
    return _rl().canonical_text(_exact(node)) == written


def a_list_written_as_a_tuple_is_refused(i: int) -> bool:
    rl = _rl()
    try:
        rl.validate(_TUPLES[int(i)])
    except rl.InvalidTerm:
        return True
    return False


def one_required_empty_field_empties_a_record_of_several(t: int) -> bool:
    """Whether a record with a required field of no value and a second,
    optional field holding term `t` is `empty` in canonical form and has
    no member in the catalogue."""
    rl, a = _rl(), TERMS[int(t)]
    node = record(("gone", EMPTY, True), ("other", a, False))
    return rl.canonical(node) == EMPTY and not _members(node)


def a_bound_is_one_of_the_two_names(d: int) -> bool:
    """Whether `member` refuses a bound that is neither `at_least` nor
    `at_most`, for definition `d`, exact or not."""
    rl = _rl()
    for bound in ("language", "most", ""):
        try:
            rl.member(DOCUMENTS[int(d)], None, bound=bound)
        except rl.InvalidTerm:
            continue
        return False
    return True


def record_of_holds_each_field_under_each_bound(d: int, v: int) -> bool:
    """Whether, under each bound, the record of one required field built
    from definition `d` holds the map with value `v` under that key
    exactly when the definition holds the value under that bound."""
    rl, document, value = _rl(), DOCUMENTS[int(d)], VALUES[int(v)]
    built = rl.record_of([("k", document, True)])
    return all(rl.member(built, {"k": value}, bound=bound) == rl.member(document, value, bound=bound)
               for bound in ("at_least", "at_most"))


def lists(item: dict, lo: int = 0, hi: "int | None" = None) -> dict:
    return {"op": "list", "item": item, "min": lo, "max": hi}


_X = record(("x", FLAG, True))
#: list terms: of flags, texts, records and lists, bounded and not, and
#: boolean combinations of them with one another and with other kinds
LISTS = [
    lists(FLAG), lists(FLAG, 1), lists(FLAG, 0, 2), lists(FLAG, 2, 3), lists(OFF, 0, 1),
    lists(choice("a", "b")), lists(text(DOLLAR), 1, 2), lists(ANY), lists(ANY, 3), lists(ANY, 0, 0),
    lists(EMPTY), lists(EMPTY, 1), lists(FLAG, 2, 1), lists(_X), lists(_X, 1, 1),
    lists(lists(FLAG)), lists(lists(FLAG, 1), 0, 2), lists(lists(ANY, 0, 0), 1),
    record(("tools", lists(choice("a", "b")), True)),
    record(("tools", lists(choice("a")), True), ("more", lists(FLAG, 1), False)),
    lists(record(("tools", lists(choice("a", "b"), 0, 1), False))),
    union(lists(FLAG), lists(choice("a", "b"))), inter(lists(FLAG, 1), lists(OFF)),
    inter(lists(ANY, 2), lists(FLAG, 0, 2)), complement(lists(FLAG)), complement(lists(ANY)),
    inter(lists(ANY), complement(lists(FLAG))),
    inter(lists(ANY, 0, 2), complement(lists(FLAG)), complement(lists(choice("a", "b")))),
    inter(lists(ANY, 0, 1), complement(lists(FLAG)), complement(lists(choice("a", "b")))),
    union(FLAG, lists(OFF, 1)), inter(complement(lists(ANY)), complement(FLAG)),
    lists(complement(lists(ANY))), lists(union(FLAG, lists(FLAG))),
    FLAG, EMPTY, ANY, _X,
]
#: the item values enumeration builds lists from
_ITEMS = [True, False, "a", "c", {"x": True}, [], [True]]


def _small_lists() -> list:
    """Every list of up to three of the item values, and of up to two of
    the lists of up to one of them, with the other values lists are told
    apart from."""
    import itertools
    out = [list(t) for n in range(4) for t in itertools.product(_ITEMS[:5], repeat=n)]
    inner = [[], [True], [False], ["a"], [True, False], [{"x": True}]]
    out += [list(t) for n in range(1, 3) for t in itertools.product(inner, repeat=n)]
    out += [[[True], "a"], [{"x": True}, [True]], ["a\n"], ["a", "a\n"], [[[]]],
            [{"tools": ["a"]}], [{"tools": ["a", "b"]}], [{}], [{"tools": "a"}]]
    out += [None, True, "a", 1, 1.5, {}, {"x": True}, {"tools": []}, {"tools": ["a", "b"]},
            {"tools": ["a"], "more": [True]}, {"tools": ["a"], "more": []}, {"tools": [True]}]
    return out


LVALUES = _small_lists()


def _lm(t: int, v: int) -> bool:
    return _rl().member(LISTS[int(t)], LVALUES[int(v)])


def a_list_is_its_items_and_its_length(i: int, lo: int, hi: int, v: int) -> bool:
    """Whether value `v` is in the list of item term `i` with lengths
    from `lo` to `hi` (`hi` 4 standing for no end) exactly when it is a
    list, of a length in the interval, with every item in the term."""
    rl, item, value = _rl(), TERMS[int(i)], LVALUES[int(v)]
    top = None if int(hi) == 4 else int(hi)
    wanted = (isinstance(value, list) and int(lo) <= len(value) and (top is None or len(value) <= top)
              and all(rl.member(item, x) for x in value))
    return rl.member(lists(item, int(lo), top), value) == wanted


def a_list_is_of_no_other_kind(t: int, v: int) -> bool:
    """Whether a list value `v` is outside term `t` when the term is a
    choice, a text or a record, and inside its complement; and whether a
    value that is no list is outside every list term."""
    rl, value = _rl(), LVALUES[int(v)]
    a = TERMS[int(t)]
    if isinstance(value, list):
        return a["op"] not in ("choice", "text", "record") or (
            not rl.member(a, value) and rl.member(complement(a), value))
    return not rl.member(lists(a), value)


def the_list_of_nothing_is_in_every_list_from_zero(t: int) -> bool:
    rl, a = _rl(), TERMS[int(t)]
    return rl.member(lists(a), []) and rl.member(lists(a, 0, 0), []) and not rl.member(lists(a, 1), [])


def a_list_is_monotone(t: int, u: int, v: int) -> bool:
    """Whether, when every catalogue member of term `t` is in term `u`,
    a list of `t` holding value `v` is a list of `u`; and whether a list
    within lengths 1 to 2 is within 0 to 3."""
    rl, a, b, value = _rl(), TERMS[int(t)], TERMS[int(u)], LVALUES[int(v)]
    if rl.member(lists(a, 1, 2), value) and not rl.member(lists(a, 0, 3), value):
        return False
    if any(not rl.member(b, x) for x in _members(a)):
        return True
    if isinstance(value, list) and not all(x in VALUES for x in value):
        return True
    return not rl.member(lists(a), value) or rl.member(lists(b), value)


def lists_meet_item_by_item(t: int, u: int, v: int) -> bool:
    """Whether the intersection of a list of term `t` of 1 to 3 items
    and a list of term `u` of up to 2 has the members of the list of
    their intersection of 1 to 2 items."""
    rl, a, b, value = _rl(), TERMS[int(t)], TERMS[int(u)], LVALUES[int(v)]
    return (rl.member(inter(lists(a, 1, 3), lists(b, 0, 2)), value)
            == rl.member(lists(inter(a, b), 1, 2), value))


def the_complement_of_a_list(t: int, v: int) -> bool:
    """Whether the complement of the list of term `t` of 1 to 2 items
    holds a list value `v` exactly when its length is not 1 or 2 or some
    item is outside the term, and holds every value that is no list."""
    rl, a, value = _rl(), TERMS[int(t)], LVALUES[int(v)]
    inside = rl.member(complement(lists(a, 1, 2)), value)
    if not isinstance(value, list):
        return inside
    return inside == (len(value) not in (1, 2) or any(not rl.member(a, x) for x in value))


def one_more_item(t: int, v: int, w: int) -> bool:
    """Whether a member `v` of the unbounded list of term `t`, with
    catalogue value `w` appended, is still a member exactly when `w` is
    in the term."""
    rl, a, value, more = _rl(), TERMS[int(t)], LVALUES[int(v)], VALUES[int(w)]
    if not rl.member(lists(a), value):
        return True
    return rl.member(lists(a), [*value, more]) == rl.member(a, more)


def list_rules_of_the_canonical_form(t: int) -> bool:
    """Whether, for item term `t`: a list whose longest length is below
    its shortest is `empty`; a list of at most nothing is the list of
    nothing whatever its item; an item of no value gives the list of
    nothing from zero and `empty` from one; and an item otherwise keeps
    the list a list."""
    rl, a = _rl(), TERMS[int(t)]
    nothing = {"op": "list", "item": EMPTY, "min": 0, "max": 0}
    gone = rl.canonical(a) == EMPTY
    return (rl.canonical(lists(a, 2, 1)) == EMPTY and rl.canonical(lists(a, 0, 0)) == nothing
            and (rl.canonical(lists(a)) == nothing) == gone
            and (rl.canonical(lists(a, 1)) == EMPTY) == gone
            and (gone or rl.canonical(lists(a, 1, 3)) == lists(rl.canonical(a), 1, 3)))


def list_terms_keep_the_standing_laws(t: int, u: int, v: int) -> bool:
    """Whether, for list terms `t` and `u` and value `v`: canonical is
    idempotent and keeps membership, complement is not, union is or and
    intersection is and."""
    rl, a, b, value = _rl(), LISTS[int(t)], LISTS[int(u)], LVALUES[int(v)]
    once = rl.canonical(a)
    x, y = _lm(t, v), _lm(u, v)
    return (rl.canonical(once) == once and rl.member(once, value) == x
            and rl.member(complement(a), value) == (not x)
            and rl.member(union(a, b), value) == (x or y)
            and rl.member(inter(a, b), value) == (x and y))


def a_malformed_list_is_refused(i: int) -> bool:
    rl = _rl()
    bad = [{"op": "list", "item": FLAG}, {"op": "list", "item": FLAG, "min": 0},
           lists(FLAG, -1), lists(FLAG, True), lists(FLAG, 0, False), lists(FLAG, 1.0),
           {"op": "list", "item": 1, "min": 0, "max": None},
           {"op": "list", "item": FLAG, "min": 0, "max": None, "distinct": True},
           lists(FLAG, 0, "2"), {"op": "list", "items": FLAG, "min": 0, "max": None}][int(i)]
    try:
        rl.validate(_exact(bad))
    except rl.InvalidTerm:
        return True
    return False


def numbers_and_booleans_are_told_apart_by_kind(c: int, v: int) -> bool:
    """Whether the choice of constant `c` alone holds value `v` exactly
    when the two are the same value of the same kind: a number is the
    number it equals whether written whole or with a point (`1` and
    `1.0`, `0`, `0.0` and `-0.0`), and a boolean is never a number
    (`True` is not `1`, `False` is not `0`), inside a record's field and
    as a list's item as well."""
    constants = [0, 1, False, True, 0.0, 1.0, -0.0, None, "0", "1", ""]
    kinds = ["n0", "n1", "bF", "bT", "n0", "n1", "n0", "null", "t0", "t1", "t"]
    rl, constant, value = _rl(), constants[int(c)], constants[int(v)]
    same = kinds[int(c)] == kinds[int(v)]
    return (rl.member(choice(constant), value) == same
            and rl.member(record(("k", choice(constant), True)), {"k": value}) == same
            and rl.member(lists(choice(constant), 1, 1), [value]) == same)


def list_of_holds_each_item_under_each_bound(d: int, v: int) -> bool:
    """Whether, under each bound, the list of one to two values built
    from definition `d` holds the list of value `v` alone, and of `v`
    twice, exactly when the definition holds the value under that bound;
    whether it is exact exactly when the definition is; and whether the
    list built with no lengths given holds the list of nothing and the
    value three times over."""
    rl, document, value = _rl(), DOCUMENTS[int(d)], VALUES[int(v)]
    built = rl.list_of(document, 1, 2)
    rl.validate(built)
    any_length = rl.list_of(document)
    return built["exact"] == document["exact"] and all(
        rl.member(built, [value], bound=bound) == rl.member(document, value, bound=bound)
        and rl.member(built, [value, value], bound=bound) == rl.member(document, value, bound=bound)
        and not rl.member(built, [], bound=bound)
        and rl.member(any_length, [], bound=bound)
        and rl.member(any_length, [value] * 3, bound=bound) == rl.member(document, value, bound=bound)
        for bound in ("at_least", "at_most"))


def generated_list(seed: int, depth: int = 0) -> dict:
    """A term drawn from `seed` in which lists stand beside the other
    nodes: lists of generated terms, bounded and not, to three deep."""
    rng = random.Random(f"list {seed} {depth}")
    leaves = [EMPTY, ANY, FLAG, OFF, choice("a", "c"), text(_lit("a")), _X]
    if depth >= 3 or rng.random() < 0.3:
        return rng.choice(leaves)
    kind = rng.choice(["list", "list", "list", "union", "inter", "complement", "record"])
    if kind == "list":
        lo = rng.randint(0, 2)
        return lists(generated_list(seed * 5 + 1, depth + 1), lo, rng.choice([None, lo, lo + 1, 3]))
    if kind == "complement":
        return complement(generated_list(seed * 7 + 1, depth + 1))
    if kind == "record":
        return record(("x", generated_list(seed * 11 + 2, depth + 1), rng.random() < 0.6))
    return {"op": kind, "args": [generated_list(seed * 13 + i + 3, depth + 1)
                                 for i in range(rng.randint(1, 3))]}


def generated_term(seed: int, depth: int = 0) -> dict:
    """A term drawn from `seed`: every node kind, records up to three
    deep over the field names x, y and z."""
    rng = random.Random(f"term {seed} {depth}")
    leaves = [EMPTY, ANY, choice(None), FLAG, OFF, choice(1, "a"), choice("a", "b", "a\n"),
              text(_lit("a")), text(DOLLAR), text(SHALLOW), text(DEEP)]
    if depth >= 3 or rng.random() < 0.35:
        return rng.choice(leaves)
    kind = rng.choice(["record", "record", "union", "inter", "complement"])
    if kind == "complement":
        return complement(generated_term(seed * 7 + 1, depth + 1))
    if kind == "record":
        names = rng.sample(["x", "y", "z"], rng.randint(0, 3))
        return record(*[(n, generated_term(seed * 11 + i + 2, depth + 1), rng.random() < 0.6)
                        for i, n in enumerate(names)])
    args = [generated_term(seed * 13 + i + 3, depth + 1) for i in range(rng.randint(0, 3))]
    return {"op": kind, "args": args}


def generated_value(seed: int, depth: int = 0):
    """A JSON value drawn from `seed`: scalars, the catalogue's texts,
    lists, and maps up to three deep over the keys x, y, z and w."""
    rng = random.Random(f"value {seed} {depth}")
    scalars = [None, True, False, 0, 1, 1.0, 1.5, "", "a", "a\n", "b", "/wt", "/wt/task-7", "/wt/x", []]
    if depth >= 3 or rng.random() < 0.45:
        return rng.choice(scalars)
    return {k: generated_value(seed * 17 + i + 5, depth + 1)
            for i, k in enumerate(rng.sample(["x", "y", "z", "w"], rng.randint(0, 3)))}


def generated_terms_keep_the_laws(seed: int) -> bool:
    """Whether, for two terms and forty values drawn from `seed`:
    canonical is idempotent and keeps membership; complement, union and
    intersection mean not, or and and; and what `find_by_enumeration` answers
    about the first inside the second agrees with `member` on the drawn
    values and on the value it finds."""
    rl = _rl()
    a, b = generated_term(int(seed)), generated_term(int(seed) + 1000)
    values = [generated_value(int(seed) * 40 + i) for i in range(40)]
    once = rl.canonical(a)
    if rl.canonical(once) != once:
        return False
    for value in values:
        x, y = rl.member(a, value), rl.member(b, value)
        if rl.member(once, value) != x or rl.member(complement(a), value) == x:
            return False
        if rl.member(union(a, b), value) != (x or y) or rl.member(inter(a, b), value) != (x and y):
            return False
    found = rl.find_by_enumeration([a], [b])
    if found.status == "member":
        return rl.member(a, found.member) and not rl.member(b, found.member)
    return not any(rl.member(a, v) and not rl.member(b, v) for v in values)
