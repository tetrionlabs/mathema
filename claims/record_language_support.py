# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about `mathema.record_language` are stated over.

Each takes whole numbers a claim can quantify: indices into `TERMS`, a
fixed catalogue of record-language nodes (every node kind, nested
records, optional and required fields, shapes of a set of permissions),
into `VALUES`, a fixed catalogue of JSON values (scalars, texts with and
without a trailing newline, maps with missing, extra and wrong-kind
keys, a list, a number that is not whole), and into `DOCUMENTS`,
definitions exact and not. Each returns the truth of one statement
about the module, so a claim reads `f(t, v) == True`.

`record_language.py` imports only `regular.py`, so the two are loaded
here from their files as a package of their own: the claims can then be
checked by any installed mathema, a released one included, against the
files in this tree. `generated_term` and `generated_value` draw further
terms and values from a seed, for the same statements over more than
the catalogue."""
from __future__ import annotations

import importlib
import json
import random
import sys
import types
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent.parent / "mathema"


def _load(name: str):
    """The module in the file `mathema/<name>.py` of this tree, loaded
    once inside a bare package `candidate_terms`, so its import of a
    sibling module reads the file beside it."""
    if "candidate_terms" not in sys.modules:
        package = types.ModuleType("candidate_terms")
        package.__path__ = [str(_PACKAGE)]
        sys.modules["candidate_terms"] = package
    return importlib.import_module(f"candidate_terms.{name}")


def _rl():
    return _load("record_language")


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
#: a child set of permissions, its parent, and the child with `merge` widened
CHILD = record(("edit", FLAG, True), ("merge", OFF, True), ("root", text(DEEP), True),
               ("shell", _CHILD_SHELL, False))
PARENT = record(("edit", FLAG, True), ("merge", FLAG, True), ("root", text(SHALLOW), True),
                ("shell", _PARENT_SHELL, False))
WIDENED = record(("edit", FLAG, True), ("merge", FLAG, True), ("root", text(DEEP), True),
                 ("shell", _CHILD_SHELL, False))

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
]

VALUES = [
    None, True, False, 0, 1, 1.0, 2, -1, 1.5, "", "a", "a\n", "b", "1", "/wt", "/wt/task-7",
    "/wt/task-7/src", "/wt/other", "/wt/task-7\n", [], [True], {}, {"x": True}, {"x": False},
    {"x": None}, {"x": 1}, {"x": True, "y": "a"}, {"x": False, "y": "c"}, {"y": "a"},
    {"x": True, "w": 1}, {"x": {"z": None}}, {"x": {"z": 0}}, {"x": {}}, {"x": [True]},
    {"edit": True, "merge": False, "root": "/wt/task-7/src"},
    {"edit": False, "merge": False, "root": "/wt/task-7", "shell": {"git": "diff"}},
    {"edit": True, "merge": True, "root": "/wt/task-7"},
    {"edit": True, "merge": False, "root": "/wt/elsewhere", "shell": {"git": "commit"}},
    {"edit": True, "merge": False, "root": "/etc"},
    {"edit": True, "merge": False},
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
    rl, regular, value = _rl(), _load("regular"), VALUES[int(v)]
    return all(rl.member(text(n), value) == (isinstance(value, str) and regular.node_member(n, value))
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


# ---- find_member and the relations derived from it ----------------------

def includes(a: dict, b: dict, timeout_ms: int = 5000):
    """`proven` when no value is in node `a` and outside node `b`,
    `falsified` with such a value, or `unknown` with the reason."""
    found = _rl().find_member([a], [b], timeout_ms=timeout_ms)
    return {"none": ("proven", None), "member": ("falsified", found.member)}.get(
        found.status, ("unknown", found.reason))


def disjoint(a: dict, b: dict, timeout_ms: int = 5000):
    """`proven` when no value is in both nodes, `falsified` with a
    common member, or `unknown`."""
    found = _rl().find_member([a, b], [], timeout_ms=timeout_ms)
    return {"none": ("proven", None), "member": ("falsified", found.member)}.get(
        found.status, ("unknown", found.reason))


def equal(a: dict, b: dict, timeout_ms: int = 5000):
    """`proven` when each node includes the other, `falsified` with a
    value in one and not the other, or `unknown`."""
    one, other = includes(a, b, timeout_ms), includes(b, a, timeout_ms)
    if "falsified" in (one[0], other[0]):
        return one if one[0] == "falsified" else other
    return ("proven", None) if one[0] == other[0] == "proven" else ("unknown", one[1] or other[1])


def a_found_member_is_a_member(t: int, u: int) -> bool:
    """Whether the value `find_member` gives for a value in term `t` and
    outside term `u` is, by `member`, in the one and outside the other."""
    rl, a, b = _rl(), TERMS[int(t)], TERMS[int(u)]
    found = rl.find_member([a], [b])
    return found.status != "member" or (rl.member(a, found.member) and not rl.member(b, found.member))


def none_found_means_no_catalogue_value(t: int, u: int) -> bool:
    """Whether, when `find_member` says no value is in term `t` and
    outside term `u`, no value of the catalogue is."""
    rl, a, b = _rl(), TERMS[int(t)], TERMS[int(u)]
    if rl.find_member([a], [b]).status != "none":
        return True
    return not any(rl.member(a, v) and not rl.member(b, v) for v in VALUES)


def a_catalogue_value_is_found(t: int, u: int) -> bool:
    """Whether, when some catalogue value is in term `t` and outside
    term `u`, `find_member` finds a member (it never says none, and on
    this catalogue it is never left without an answer)."""
    rl, a, b = _rl(), TERMS[int(t)], TERMS[int(u)]
    if not any(rl.member(a, v) and not rl.member(b, v) for v in VALUES):
        return True
    return rl.find_member([a], [b]).status == "member"


def a_term_and_its_complement_share_nothing(t: int) -> bool:
    a = TERMS[int(t)]
    return disjoint(a, complement(a))[0] == "proven" and includes(a, a)[0] == "proven"


def a_term_equals_its_canonical_form(t: int) -> bool:
    a = TERMS[int(t)]
    return equal(a, _rl().canonical(a))[0] == "proven"


def inclusion_is_monotone(t: int, u: int) -> bool:
    """Whether term `t` is included in its union with term `u`, and
    their intersection in `t`."""
    a, b = TERMS[int(t)], TERMS[int(u)]
    return includes(a, union(a, b))[0] == "proven" and includes(inter(a, b), a)[0] == "proven"


def inclusion_is_transitive(t: int, u: int, w: int) -> bool:
    a, b, c = TERMS[int(t)], TERMS[int(u)], TERMS[int(w)]
    if includes(a, b)[0] != "proven" or includes(b, c)[0] != "proven":
        return True
    return includes(a, c)[0] == "proven"


def the_child_is_inside_its_parent() -> bool:
    """Whether the child set of permissions is included in its parent,
    and the child with `merge` widened is not included in the child,
    with a value `member` puts in the one and outside the other."""
    rl = _rl()
    verdict, witness = includes(WIDENED, CHILD)
    return (includes(CHILD, PARENT)[0] == "proven" and verdict == "falsified"
            and rl.member(WIDENED, witness) and not rl.member(CHILD, witness)
            and includes(PARENT, CHILD)[0] == "falsified")


# ---- laws found missing by mutating the module ---------------------------

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


def a_text_of_any_character_is_found(i: int) -> bool:
    """Whether `find_member` finds the one member of a choice of one
    text, for texts holding the first code point, the last, a lone
    surrogate and a character outside ASCII."""
    wanted = ("\x00", "a\x00b", "\U0010ffff", "\ud800", "\u00e9", "")[int(i)]
    found = _rl().find_member([choice(wanted)], [])
    return found.status == "member" and found.member == wanted


def a_value_member_does_not_place_is_not_returned(i: int) -> bool:
    """Whether `find_member` answers `unknown`, and returns no member,
    when the value read from the solver is one `member` does not place
    inside every node asked and outside every other: case 0 a value in
    one of two inside nodes only, case 1 a value in one of two outside
    nodes, case 2 a value in no inside node."""
    rl = _rl()
    inside, outside, wrong = [
        ([FLAG, choice(True, "a")], [], False),
        ([FLAG], [choice("a"), OFF], False),
        ([FLAG], [], "a"),
    ][int(i)]
    real = rl._Lowering.read
    rl._Lowering.read = lambda self, model, value=None, path=(): wrong
    try:
        found = rl.find_member(inside, outside)
    finally:
        rl._Lowering.read = real
    return found.status == "unknown" and found.member is None


# ---- generated terms and values -----------------------------------------

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
    intersection mean not, or and and; and what `find_member` answers
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
    found = rl.find_member([a], [b])
    if found.status == "member":
        return rl.member(a, found.member) and not rl.member(b, found.member)
    if found.status == "none":
        return not any(rl.member(a, v) and not rl.member(b, v) for v in values)
    return False
