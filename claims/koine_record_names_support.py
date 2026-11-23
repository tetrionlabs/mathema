# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions the claims about field names that look like paths, quotes
or nothing at all, on the KOINE route, are stated over.

A field's name never makes it the same solver variable as another
field's, at one place or nested: a record of two such names, or of one
nested under another, has its member found; and a question drawn from a
seed over records named so has the answer the oracle's enumerator gives
(`tests/_record_language_oracle.py`), both ways where its universe is
complete and one way otherwise.

Each function takes indices into `NAMES` or a seed, and returns the
truth of one statement, so a claim reads `f(...) == True`. `shrunk`
gives the smallest question a failing seed reduces to, for a reader of
the failure."""
from __future__ import annotations

import copy
import importlib.util
import random
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _question_support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_question_support", _HERE / "koine_record_question_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Q = _question_support()
REF = Q.REF
#: field names a solver could read as one another, or as a path, a
#: quote or an escape: NUL, the empty name, two NULs, a plain letter, a
#: dotted and quoted name, a double quote, a single quote, a backslash
NAMES = ["\x00", "", "\x00\x00", "a", "a'.'b", '"', "'", "\\"]
SCALARS = [None, True, False, 0, 1, 2, "a", "b"]


def _rm():
    from mathema.koine import record_membership
    return record_membership


def _sq():
    from mathema.koine import solver_question
    return solver_question


def _rl():
    return REF._load()


def _found(inside, outside=()):
    rm = _rm()
    return _sq().find_member([rm.membership_document(n) for n in inside],
                             [rm.membership_document(n) for n in outside])


def _placed(value, inside, outside=()) -> bool:
    rl = _rl()
    return all(rl.member(n, value) for n in inside) and not any(
        rl.member(n, value) for n in outside)


def two_names_at_one_place_are_two_fields(a: int, b: int) -> bool:
    """Whether the record of required fields named `a` (holding 1) and
    `b` (holding 2) has a member found, placed by the oracle, with both
    keys and no other."""
    if int(a) == int(b):
        return True
    node = REF.record((NAMES[int(a)], REF.choice(1), True), (NAMES[int(b)], REF.choice(2), True))
    found = _found([node])
    return (found.status == "member" and _placed(found.member, [node])
            and set(found.member) == {NAMES[int(a)], NAMES[int(b)]})


def a_nested_name_is_not_an_outer_one(a: int, b: int, c: int) -> bool:
    """Whether the record of field `a` (a record of field `b` holding 1)
    beside field `c` (holding 2) has a member found, placed by the
    oracle, when `a` and `c` are two names."""
    if int(a) == int(c):
        return True
    node = REF.record((NAMES[int(a)], REF.record((NAMES[int(b)], REF.choice(1), True)), True),
                      (NAMES[int(c)], REF.choice(2), True))
    found = _found([node])
    return found.status == "member" and _placed(found.member, [node])


def a_text_field_of_any_name_is_found(a: int) -> bool:
    """Whether the record of one field named `a`, holding the text 'a',
    has the member {a: 'a'} found."""
    node = REF.record((NAMES[int(a)], {"op": "text", "language": {"op": "literal",
                                                                   "codes": [97]}}, True))
    found = _found([node])
    return found.status == "member" and found.member == {NAMES[int(a)]: "a"}


def weird_term(rng: random.Random, depth: int = 3) -> dict:
    """A term drawn from `rng`: choices of `SCALARS`, a text of one
    literal, `any` and `empty` at the leaves, and records over `NAMES`,
    unions, intersections and complements above them, to `depth`."""
    if depth <= 0 or rng.random() < 0.25:
        leaf = rng.choice(["any", "empty", "choice", "choice", "text"])
        if leaf == "choice":
            return REF.choice(*rng.sample(SCALARS, rng.randint(1, 3)))
        if leaf == "text":
            return {"op": "text", "language": {"op": "literal",
                                               "codes": [ord(rng.choice("ab"))]}}
        return {"op": leaf}
    kind = rng.choice(["record", "record", "union", "inter", "complement", "complement"])
    if kind == "record":
        names = rng.sample(NAMES, rng.randint(0, 4))
        return REF.record(*[(name, weird_term(rng, depth - 1), rng.random() < 0.5)
                            for name in names])
    if kind == "complement":
        return REF.complement(weird_term(rng, depth - 1))
    return {"op": kind, "args": [weird_term(rng, depth - 1) for _ in range(rng.randint(1, 3))]}


def weird_question(seed: int) -> tuple:
    """`(inside, outside)`: one to three terms drawn from `seed`, the
    first one or more inside."""
    rng = random.Random(f"weird names {seed}")
    terms = [weird_term(rng) for _ in range(rng.randint(1, 3))]
    k = rng.randint(1, len(terms))
    return terms[:k], terms[k:]


def _agrees_on(inside, outside) -> bool:
    found = _found(inside, outside)
    counted = _rl().find_by_enumeration(inside, outside)
    return Q._agrees(found, counted, inside, outside)


def a_question_over_weird_names_agrees_with_the_enumerator(seed: int) -> bool:
    """Whether the KOINE route's answer to the question drawn from
    `seed` agrees with the oracle's enumerator, by the rule of
    `koine_record_question_support._agrees`."""
    return _agrees_on(*weird_question(int(seed)))


def _smaller(node: dict):
    """The terms one step smaller than `node`."""
    yield {"op": "any"}
    yield {"op": "empty"}
    op = node["op"]
    if op == "complement":
        yield node["arg"]
        for inner in _smaller(node["arg"]):
            yield {"op": "complement", "arg": inner}
    if op in ("union", "inter"):
        for i, arg in enumerate(node["args"]):
            yield arg
            yield {**node, "args": node["args"][:i] + node["args"][i + 1:]}
            for inner in _smaller(arg):
                yield {**node, "args": [*node["args"][:i], inner, *node["args"][i + 1:]]}
    if op == "record":
        for i, (name, inner, required) in enumerate(node["fields"]):
            yield {**node, "fields": node["fields"][:i] + node["fields"][i + 1:]}
            for smaller in _smaller(inner):
                fields = copy.deepcopy(node["fields"])
                fields[i] = [name, smaller, required]
                yield {**node, "fields": fields}


def shrunk(seed: int) -> tuple:
    """`(inside, outside)`: the question drawn from `seed`, made smaller
    one term or one part at a time for as long as it still breaks
    `a_question_over_weird_names_agrees_with_the_enumerator`; the
    question as drawn when it does not break it."""
    inside, outside = weird_question(int(seed))
    if _agrees_on(inside, outside):
        return inside, outside
    changed = True
    while changed:
        changed = False
        terms = inside + outside
        for i in range(len(terms)):
            for smaller in _smaller(terms[i]):
                ni, no = list(inside), list(outside)
                if i < len(inside):
                    ni[i] = smaller
                else:
                    no[i - len(inside)] = smaller
                if not _agrees_on(ni, no):
                    inside, outside, changed = ni, no, True
                    break
            if changed:
                break
    return inside, outside
