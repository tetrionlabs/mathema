# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A seeded search for a record-language question with text nodes that
the KOINE route answers wrongly.

Random record-language nodes mixing choices, records and text nodes
(their regular languages over a few characters, with complements,
intersections and repeats) are asked as one question: a value in every
node of `inside` and in no node of `outside`. The KOINE route
(`solver_question.find_member` over the membership documents) is
compared with the test oracle (`tests/_record_language_oracle.py`):
a member the route gives must be placed by the oracle's `member` as
asked, and the route must never say `none` where the oracle's
enumeration finds a member. Exact definitions built from the same nodes
are also related by `record_relations.decide`, and a proven or
falsified verdict is checked against the oracle's enumeration.

The default budget is small; MATHEMA_FUZZ_FULL=1 runs the full size."""
import os
import random

import pytest

from mathema.koine import record_membership, record_relations, solver_question
from tests import _record_language_oracle as oracle

pytest.importorskip("z3")

FULL = os.environ.get("MATHEMA_FUZZ_FULL") == "1"
CASES = 1500 if FULL else 60
LOW, HIGH = 0x61, 0x63
SCALARS = [None, True, False, 0, 1, "a", "b", "ab", ""]


def _regular(rng, depth):
    if depth <= 0 or rng.random() < 0.35:
        k = rng.random()
        if k < 0.4:
            return {"op": "literal",
                    "codes": [rng.randint(LOW, HIGH) for _ in range(rng.randint(0, 2))]}
        if k < 0.8:
            lo = rng.randint(LOW, HIGH)
            return {"op": "chars", "ranges": [[lo, rng.randint(lo, HIGH)]]}
        return {"op": "chars", "ranges": [[0, 0x10FFFF]]}
    op = rng.choice(["concat", "union", "inter", "complement", "repeat"])
    if op == "complement":
        return {"op": op, "arg": _regular(rng, depth - 1)}
    if op == "repeat":
        lo = rng.randint(0, 1)
        return {"op": op, "arg": _regular(rng, depth - 1), "min": lo,
                "max": rng.choice([None, lo + 1])}
    return {"op": op, "args": [_regular(rng, depth - 1) for _ in range(2)]}


def _node(rng, depth):
    k = rng.random()
    if depth <= 0 or k < 0.3:
        j = rng.random()
        if j < 0.45:
            return {"op": "text", "language": _regular(rng, 2)}
        if j < 0.8:
            return {"op": "choice", "values": rng.sample(SCALARS, rng.randint(1, 3))}
        return {"op": rng.choice(["empty", "any"])}
    if k < 0.55:
        names = rng.sample(["x", "y"], rng.randint(0, 2))
        return {"op": "record", "rest": {"op": "empty"},
                "fields": [[n, _node(rng, depth - 1), rng.random() < 0.5] for n in names]}
    if k < 0.7:
        return {"op": "complement", "arg": _node(rng, depth - 1)}
    return {"op": rng.choice(["union", "inter"]),
            "args": [_node(rng, depth - 1) for _ in range(2)]}


def _exact(node):
    return {"kind": oracle.KIND, "version": oracle.VERSION, "exact": True, "language": node}


def _placed(value, inside, outside):
    return all(oracle.member(n, value) for n in inside) and \
        not any(oracle.member(n, value) for n in outside)


def _one_case(seed):
    rng = random.Random(seed)
    nodes = [oracle.canonical(_node(rng, 2)) for _ in range(rng.randint(1, 3))]
    split = rng.randint(0, len(nodes))
    inside, outside = nodes[:split], nodes[split:]
    found = solver_question.find_member(
        [record_membership.membership_document(n) for n in inside],
        [record_membership.membership_document(n) for n in outside], timeout_ms=10_000)
    enumerated = oracle.find_by_enumeration(inside, outside)
    where = (seed, inside, outside, found, enumerated)
    if found.status == "member":
        assert _placed(found.member, inside, outside), where
    elif found.status == "none":
        assert enumerated.status == "none", where
    if enumerated.status == "none" and enumerated.complete:
        assert found.status != "member", where
    if len(nodes) >= 2:
        word = rng.choice(record_relations.WORDS)
        a, b = _exact(nodes[0]), _exact(nodes[1])
        decision = record_relations.decide(word, a, b, timeout_ms=10_000)
        universal = {"not subset": "subset", "!=": "="}.get(word, word)
        questions = {"subset": [([nodes[0]], [nodes[1]])],
                     "disjoint": [([nodes[0], nodes[1]], [])],
                     "=": [([nodes[0]], [nodes[1]]), ([nodes[1]], [nodes[0]])]}[universal]
        breaking = [oracle.find_by_enumeration(i, o) for i, o in questions]
        holds = "proven" if word == universal else "falsified"
        if decision.verdict == holds:
            assert all(e.status == "none" for e in breaking), (where, word, decision)
        elif decision.verdict in ("proven", "falsified"):
            assert any(_placed(decision.witness["value"], i, o) for i, o in questions), \
                (where, word, decision)
    return found.status


def test_the_koine_route_agrees_with_the_oracle_on_questions_with_text_nodes():
    counts: dict = {}
    for seed in range(CASES):
        status = _one_case(seed)
        counts[status] = counts.get(status, 0) + 1
    assert counts.get("member", 0) and counts.get("none", 0), counts
