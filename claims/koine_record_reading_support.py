# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about which record-language definitions the
KOINE route reads, and about the shape of what it writes, are stated
over.

The modules under claim are `mathema.koine.record_membership` and
`mathema.koine.record_relations`. The record-language oracle
(`tests/_record_language_oracle.py`) is what the
route is compared with: a definition it refuses (by raising) the route
refuses with `InvalidTerm`, and a definition it reads the route reads,
with the same members under each bound, or declines by name for a list
node it reads.

Each function takes an index into `DOCUMENTS`: definitions well formed
and not (the reference's catalogues, the conformance vectors, and each
catalogue term changed in one way: a key added or left out, a list
written as a tuple or an object, a field written another way, a
duplicate field, a rest that is or is not empty in canonical form, a
choice value of another kind or past the length of number the
interpreter writes), or into `TERMS`. Each returns the truth of one
statement, so a claim reads `f(i) == True`."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Q = _load("koine_record_question_support")
REF = Q.REF
TERMS = REF.TERMS
VALUES = Q.VALUES
EMPTY = {"op": "empty"}

#: rests that are empty in canonical form, and rests that are not
_EMPTY_RESTS = [
    {"op": "union", "args": []}, {"op": "choice", "values": []},
    {"op": "text", "language": {"op": "empty"}},
    {"op": "inter", "args": [{"op": "choice", "values": []}, {"op": "any"}]},
    {"op": "record", "fields": [["x", EMPTY, True]], "rest": EMPTY},
    {"op": "list", "item": REF.FLAG, "min": 2, "max": 1},
    {"op": "union", "args": [EMPTY, {"op": "union", "args": [EMPTY]}]},
]
_FULL_RESTS = [
    {"op": "any"}, {"op": "complement", "arg": {"op": "any"}}, REF.FLAG,
    {"op": "inter", "args": []}, {"op": "union", "args": [EMPTY, {"op": "any"}]},
    {"op": "list", "item": EMPTY, "min": 0, "max": 0},
    {"op": "record", "fields": [["x", EMPTY, False]], "rest": EMPTY},
]


def _variants(node: dict) -> list:
    """Each way of changing `node` in one place that the tests of a
    reader turn on: a key added, each key left out, the operation
    unknown, and the changes particular to its operation."""
    op = node.get("op")
    out = [{**node, "junk": 0}, {**node, "op": "set"}]
    out += [{k: v for k, v in node.items() if k != key} for key in node if key != "op"]
    if op == "choice":
        out += [{**node, "values": tuple(node["values"])},
                {**node, "values": [*node["values"], 1.5]},
                {**node, "values": [*node["values"], [1]]},
                {**node, "values": [*node["values"], float("nan")]},
                {**node, "values": [*node["values"], 10 ** 5000]},
                {**node, "values": [*node["values"], 10 ** 400]},
                {**node, "values": [*node["values"], 2.0]}]
    if op in ("union", "inter"):
        out += [{**node, "args": {"a": 1}}, {**node, "args": tuple(node["args"])},
                {**node, "args": [*node["args"], 1]}]
    if op == "complement":
        out += [{**node, "arg": 1}, {**node, "arg": {"op": "set"}}]
    if op == "text":
        out += [{**node, "language": 5}, {**node, "language": {"op": "literal", "codes": [-5]}},
                {**node, "language": {"op": "chars", "ranges": [[5, 1]]}}]
    if op == "record":
        fields = node["fields"]
        out += [{**node, "fields": tuple(fields)}, {**node, "fields": {"x": REF.FLAG}}]
        if fields:
            first = fields[0]
            out += [{**node, "fields": [*fields, list(first)]},
                    {**node, "fields": [tuple(first), *fields[1:]]},
                    {**node, "fields": [[1, first[1], first[2]], *fields[1:]]},
                    {**node, "fields": [[first[0], first[1], 1], *fields[1:]]},
                    {**node, "fields": [[first[0], first[1]], *fields[1:]]},
                    {**node, "fields": [[first[0], {"op": "set"}, first[2]], *fields[1:]]}]
        out += [{**node, "rest": rest} for rest in _EMPTY_RESTS + _FULL_RESTS]
    return out


def _vector_documents() -> list:
    return [v["document"] for v in Q.VECTORS] + [
        v["document"] for v in json.loads(
            (_HERE.parent / "tests" / "data" / "record_language_vectors.json")
            .read_text(encoding="utf-8"))["vectors"] if v.get("invalid")]


def _reviewed() -> list:
    """The definitions an outside review read the route on."""
    ch = REF.choice
    rec = REF.record
    return [
        REF._exact({"op": "record", "fields": [["a", ch(1), True], ["a", ch(2), True]],
                    "rest": EMPTY}),
        REF._exact({"op": "choice", "values": [1], "junk": 0}),
        REF._exact({"op": "text", "language": {"op": "literal", "codes": [-5]}}),
        REF._exact({"op": "record", "fields": []}),
        REF._exact({"op": "union", "args": {"a": 1}}),
        {**REF._exact(rec(("x", ch(True), True))), "note": "x"},
        REF._exact({"op": "record", "fields": [["x", ch(True), True]],
                    "rest": {"op": "union", "args": []}}),
        REF._exact({"op": "choice", "values": [1, True], "why": "x"}),
        REF._exact(rec(("x", ch(1.0), True))),
        REF._exact(ch(10 ** 400)), REF._exact(ch(2 ** 53 + 1)), REF._exact(ch(10 ** 5000)),
        {**REF._exact(REF.FLAG), "version": 1.0}, {**REF._exact(REF.FLAG), "version": True},
        {**REF._exact(REF.FLAG), "exact": 1},
        {**REF._exact(REF.FLAG), "at_least": REF.FLAG},
        {k: v for k, v in REF._exact(REF.FLAG).items() if k != "kind"},
        {"kind": "record_language", "version": 1, "exact": False, "at_least": REF.FLAG,
         "at_most": REF.FLAG, "source": {"written": "by hand"}, "note": 1},
    ]


DOCUMENTS = (REF.VALID + REF.INVALID + _vector_documents() + _reviewed()
             + [REF._exact(v) for t in TERMS for v in _variants(t)])


def _rm():
    from mathema.koine import record_membership
    return record_membership


def _rl():
    return REF._load()


def _reference_reads(document) -> bool:
    """Whether the reference reads `document`: `bounds` gives its two
    nodes rather than raising."""
    try:
        _rl().bounds(copy.deepcopy(document))
    except Exception:
        return False
    return True


def _holds_a_list(node) -> bool:
    return Q._holds_a_list(node)


def _route(document):
    """What the route makes of `document`: `("documents", (at_most,
    at_least))`, `("declined", message)`, `("refused", message)`, or
    `("raised", the exception's type)` for anything else."""
    rm = _rm()
    try:
        return "documents", rm.membership_documents(copy.deepcopy(document))
    except rm.Declined as e:
        return "declined", str(e)
    except rm.InvalidTerm as e:
        return "refused", str(e)
    except Exception as e:
        return "raised", type(e).__name__


def a_definition_is_refused_as_the_reference_refuses_it(i: int) -> bool:
    """Whether the route refuses definition `i` with `InvalidTerm`
    exactly when the reference refuses it; when the reference reads it,
    the route gives its two documents, or declines it by name and the
    definition holds a list node; and the route never raises anything
    else."""
    document = DOCUMENTS[int(i)]
    outcome, _ = _route(document)
    if not _reference_reads(document):
        return outcome == "refused"
    if outcome == "declined":
        return _holds_a_list(document)
    return outcome == "documents"


def a_relation_refuses_what_the_route_refuses(i: int) -> bool:
    """Whether `subset` between definition `i` and the empty language
    raises `InvalidTerm` exactly when the route refuses the definition,
    and otherwise gives a verdict."""
    from mathema.koine import record_relations
    document = DOCUMENTS[int(i)]
    outcome, _ = _route(document)
    try:
        decided = record_relations.decide("subset", copy.deepcopy(document),
                                          REF._exact(EMPTY))
    except _rm().InvalidTerm:
        return outcome == "refused"
    except Exception:
        return False
    return outcome != "refused" and decided.verdict in ("proven", "falsified", "unknown")


def a_definition_both_read_has_the_same_members(i: int) -> bool:
    """Whether, for definition `i` that the reference and the route
    both read, each bound's membership document has, at every catalogue
    value, the truth the reference gives under that bound."""
    from mathema.koine import record_terms
    from mathema.koine.interpret import Value
    document = DOCUMENTS[int(i)]
    outcome, documents = _route(document)
    if outcome != "documents" or not _reference_reads(document):
        return True
    rl = _rl()
    for value in VALUES:
        for written, bound in zip(documents, ("at_most", "at_least")):
            want = rl.member(document, value, bound=bound)
            if record_terms.interpret(written, [value]) != Value(want):
                return False
    return True


# ---- the shapes the membership function is written in ----------------------

def _expected(node: dict, operand):
    """The membership expression of a node as this file states its
    shape, written out independently of the route: false and true;
    one constant test for each value of a choice, joined by or; a
    text's kind test and its language; not, or and and; and for a
    record, the dict test, the closed keys, then one part per field."""
    from mathema.koine import language_terms as lt
    from mathema.koine import record_terms as rt
    from mathema.koine.syntax import Bool, Int, List, Str, Term
    op = node["op"]

    def kind(e, k):
        return Term(rt.IS_OF_KIND, (e, Term(k)))

    def present(e):
        return Term(rt.VALUE_OF_PRESENT, (e,))

    def joined(head, parts):
        if not parts:
            return Bool(head == "operator::logic::and")
        return parts[0] if len(parts) == 1 else Term(head, tuple(parts))

    def constant(value):
        if value is None:
            return Term(rt.IS_ABSENT, (operand,))
        equal = "operator::comparison::equal"
        if isinstance(value, bool):
            return Term("operator::logic::and",
                        (kind(operand, "kind::bool"), Term(equal, (present(operand), Bool(value)))))
        if isinstance(value, (int, float)):
            number = Term("operator::logic::or",
                          (kind(operand, "kind::int"), kind(operand, "kind::scalar")))
            return Term("operator::logic::and",
                        (number, Term(equal, (present(operand), Int(int(value))))))
        return Term("operator::logic::and",
                    (kind(operand, "kind::string"), Term(equal, (present(operand), Str(value)))))
    if op == "empty":
        return Bool(False)
    if op == "any":
        return Bool(True)
    if op == "choice":
        return joined("operator::logic::or", [constant(v) for v in node["values"]])
    if op == "text":
        return Term("operator::logic::and", (kind(operand, "kind::string"),
                                             lt.in_language(present(operand), node["language"])))
    if op == "complement":
        return Term("operator::logic::not", (_expected(node["arg"], operand),))
    if op in ("union", "inter"):
        head = "operator::logic::or" if op == "union" else "operator::logic::and"
        return joined(head, [_expected(a, operand) for a in node["args"]])
    of_map = present(operand)
    parts = [kind(operand, "kind::dict"),
             Term(rt.HAS_NO_KEY_OTHER_THAN,
                  (of_map, List(tuple(Str(name) for name, _, _ in node["fields"]))))]
    for name, inner, required in node["fields"]:
        has = Term(rt.HAS_KEY, (of_map, Str(name)))
        inside = _expected(inner, Term(rt.VALUE_AT_KEY, (of_map, Str(name))))
        parts.append(Term("operator::logic::and", (has, inside)) if required
                     else Term("operator::logic::or", (Term("operator::logic::not", (has,)),
                                                       inside)))
    return Term("operator::logic::and", tuple(parts))


SHAPED = TERMS + [n for d in DOCUMENTS[:len(REF.VALID)] if isinstance(d, dict)
                  and isinstance(d.get("language"), dict) for n in [d["language"]]] \
    + [REF.generated_term(seed) for seed in range(200)]


def each_node_is_written_in_its_stated_shape(t: int) -> bool:
    """Whether the membership expression of node `t` is the one this
    file states the shape of, term for term, for every node the route
    reads (a node it declines or refuses is left out)."""
    from mathema.koine.syntax import Name
    from mathema.koine import record_terms as rt
    rm, node = _rm(), SHAPED[int(t)]
    operand = Name(rt.PARAMETER)
    try:
        written = rm.membership_expression(copy.deepcopy(node), operand)
    except (rm.Declined, rm.InvalidTerm):
        return True
    return written == _expected(node, operand)
