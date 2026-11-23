# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A seeded search for a question `regular.lower_into` answers wrongly.

Several random nodes over a few characters are lowered together into
z3 over an alphabet whose ranges may differ from, overlap or miss the
nodes' characters, or be empty. For a random choice of nodes the text
must lie in and nodes it must lie outside, the solver's answer under
the lowering is compared with every text of up to `LONGEST` characters
over the alphabet: a member the solver gives must, read back by
`decode`, lie in the alphabet and be placed by `regular.contains` as
asked of every node, and the solver must find a member whenever a short
text is one. `regular.find_member` must give the same status.

The default budget is small; MATHEMA_FUZZ_FULL=1 runs the full size."""
import itertools
import os
import random

import pytest

from mathema import regular

z3 = pytest.importorskip("z3")

FULL = os.environ.get("MATHEMA_FUZZ_FULL") == "1"
CASES = 3000 if FULL else 150
LONGEST = 3
#: the characters the nodes read
LOW, HIGH = 0x61, 0x65
#: one character no node's small set holds, standing for all such
OUTSIDE = 0x41


def _node(rng, depth):
    if depth <= 0 or rng.random() < 0.3:
        k = rng.random()
        if k < 0.35:
            return {"op": "literal",
                    "codes": [rng.randint(LOW, HIGH) for _ in range(rng.randint(0, 2))]}
        if k < 0.75:
            ranges = []
            for _ in range(rng.randint(1, 3)):
                lo = rng.randint(LOW, HIGH)
                ranges.append([lo, rng.randint(lo, HIGH)])
            return {"op": "chars", "ranges": ranges}
        if k < 0.85:
            return {"op": "chars", "ranges": [[0, regular.MAX_CODE_POINT]]}
        return {"op": rng.choice(["empty", "epsilon"])}
    op = rng.choice(["concat", "union", "inter", "complement", "repeat", "repeat"])
    if op == "complement":
        return {"op": op, "arg": _node(rng, depth - 1)}
    if op == "repeat":
        lo = rng.randint(0, 2)
        hi = rng.choice([None, lo, lo + 1, lo + 2])
        return {"op": op, "arg": _node(rng, depth - 1), "min": lo, "max": hi}
    return {"op": op, "args": [_node(rng, depth - 1) for _ in range(rng.randint(2, 3))]}


def _alphabet(rng):
    """None (every code point), or ranges over the nodes' characters
    and one beyond them, possibly empty and possibly overlapping."""
    if rng.random() < 0.25:
        return None
    ranges = []
    for _ in range(rng.randint(0, 3)):
        lo = rng.choice([OUTSIDE, *range(LOW, HIGH + 1)])
        hi = rng.choice([c for c in [OUTSIDE, *range(LOW, HIGH + 1)] if c >= lo])
        ranges.append([lo, hi])
    return ranges


def _characters(alphabet):
    if alphabet is None:
        return [OUTSIDE, *range(LOW, HIGH + 1), regular.MAX_CODE_POINT]
    return sorted({c for lo, hi in alphabet for c in range(lo, hi + 1)})


def _brute(characters, inside, outside):
    for n in range(LONGEST + 1):
        for codes in itertools.product(characters, repeat=n):
            text = "".join(map(chr, codes))
            if all(regular.contains(x, text) for x in inside) and \
                    not any(regular.contains(x, text) for x in outside):
                return text
    return None


def _lowered_member(lowered, inside, outside):
    x = z3.String("x")
    solver = z3.Solver()
    solver.set("timeout", 10_000)
    solver.add(z3.InRe(x, lowered.everything))
    for node in inside:
        solver.add(z3.InRe(x, lowered.regex(node)))
    for node in outside:
        solver.add(z3.Not(z3.InRe(x, lowered.regex(node))))
    outcome = solver.check()
    if outcome == z3.unsat:
        return "none", None
    if outcome != z3.sat:
        return "unknown", None
    return "member", lowered.decode(solver.model().eval(x, model_completion=True).as_string())


def _one_case(seed):
    rng = random.Random(seed)
    pool = [regular.canonical(_node(rng, 3)) for _ in range(rng.randint(1, 4))]
    alphabet = _alphabet(rng)
    chosen = rng.sample(pool, rng.randint(1, len(pool)))
    split = rng.randint(0, len(chosen))
    inside, outside = chosen[:split], chosen[split:]
    lowered = regular.lower_into(pool, z3, alphabet)
    status, text = _lowered_member(lowered, inside, outside)
    characters = _characters(alphabet)
    short = _brute(characters, inside, outside)
    where = (seed, alphabet, inside, outside, status, text, short)
    if status == "unknown":
        return "unknown"
    if status == "member":
        assert all(ord(c) in characters or alphabet is None for c in text), where
        if alphabet is not None:
            assert all(any(lo <= ord(c) <= hi for lo, hi in alphabet) for c in text), where
        assert all(regular.contains(x, text) for x in inside), where
        assert not any(regular.contains(x, text) for x in outside), where
    else:
        assert short is None, where
    expected = regular.find_member(alphabet if alphabet is not None
                                   else [[0, regular.MAX_CODE_POINT]], inside, outside)
    assert expected.status == status, (where, expected)
    return status


def test_lower_into_agrees_with_brute_force_over_short_texts():
    counts: dict = {}
    for seed in range(CASES):
        status = _one_case(seed)
        counts[status] = counts.get(status, 0) + 1
    assert counts.get("member", 0) and counts.get("none", 0), counts
