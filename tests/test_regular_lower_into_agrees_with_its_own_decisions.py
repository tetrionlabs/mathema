# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`regular.lower_into` lowers the text nodes of one question into z3
over one shared set of atoms, and what it lowers agrees with regular's
own decisions: a node has a text inside it, and one outside it, under
the lowering exactly when `find_member` says so, and each text the
solver gives, read back by the lowering, is held or not held by
`regular.contains` as the solver placed it."""
import pytest

from mathema import regular

z3 = pytest.importorskip("z3")
ALL = [[0, regular.MAX_CODE_POINT]]


def _lit(*codes):
    return {"op": "literal", "codes": list(codes)}


def _chars(*ranges):
    return {"op": "chars", "ranges": [list(r) for r in ranges]}


DIGIT = _chars((48, 57))
NODES = [regular.canonical(n) for n in [
    {"op": "empty"}, {"op": "epsilon"}, _lit(97), _lit(0x10FFFF), _lit(0xD83D, 0xDE00),
    _lit(0xD800), DIGIT, _chars((97, 122), (48, 57)),
    {"op": "concat", "args": [_lit(97), DIGIT]},
    {"op": "union", "args": [_lit(97), _lit(98), {"op": "epsilon"}]},
    {"op": "inter", "args": [{"op": "repeat", "arg": DIGIT, "min": 0, "max": None}, _lit(49)]},
    {"op": "complement", "arg": _lit(97)},
    {"op": "repeat", "arg": DIGIT, "min": 1, "max": 3},
    {"op": "repeat", "arg": DIGIT, "min": 2, "max": None},
    {"op": "concat", "args": [_lit(97), {"op": "repeat", "arg": _lit(10), "min": 0, "max": 1}]},
]]


def _found(lowered, node, inside: bool):
    x = z3.String("x")
    solver = z3.Solver()
    solver.add(z3.InRe(x, lowered.everything))
    held = z3.InRe(x, lowered.regex(node))
    solver.add(held if inside else z3.Not(held))
    if solver.check() != z3.sat:
        return None
    return lowered.decode(solver.model().eval(x, model_completion=True).as_string())


@pytest.mark.parametrize("index", range(len(NODES)))
def test_a_lowered_node_agrees_with_regulars_own_decisions(index):
    node = NODES[index]
    lowered = regular.lower_into(NODES, z3)
    for inside in (True, False):
        text = _found(lowered, node, inside)
        expected = regular.find_member(ALL, [node], []) if inside else \
            regular.find_member(ALL, [], [node])
        assert (text is not None) == (expected.status == "member"), (node, inside, expected)
        if text is not None:
            assert regular.contains(node, text) is inside, (node, inside, text)


def test_lower_into_is_a_public_call_of_the_term_algebra():
    assert "lower_into" in regular.__all__ and callable(regular.lower_into)
