# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`regular.lower_into(nodes, ...)` cuts the alphabet into atoms by the
character sets of `nodes` alone, so its `regex` is the language of a
node only for a canonical node among them. A node it did not lower may
need a distinction the atoms do not make: lowered beside `[a-z]`, the
literal `b` and the literal `a` are the same one symbol, and a question
asking for `b` and not `a` has no answer under the lowering though "b"
answers it. A node not among the lowered ones, or not canonical, is
refused rather than lowered over atoms that cannot tell its characters
apart."""
import pytest

from mathema import regular

z3 = pytest.importorskip("z3")

A_TO_Z = {"op": "chars", "ranges": [[97, 122]]}
A, B = {"op": "literal", "codes": [97]}, {"op": "literal", "codes": [98]}


def _solve(lowered, inside, outside):
    x = z3.String("x")
    solver = z3.Solver()
    solver.add(z3.InRe(x, lowered.everything))
    for node in inside:
        solver.add(z3.InRe(x, lowered.regex(node)))
    for node in outside:
        solver.add(z3.Not(z3.InRe(x, lowered.regex(node))))
    if solver.check() != z3.sat:
        return None
    return lowered.decode(solver.model().eval(x, model_completion=True).as_string())


def test_a_node_lowered_beside_others_it_was_not_cut_with_is_refused_or_answered_rightly():
    lowered = regular.lower_into([A_TO_Z], z3)
    assert regular.contains(B, "b") and not regular.contains(A, "b")
    try:
        text = _solve(lowered, [B], [A])
    except (regular.InvalidTerm, KeyError, ValueError):
        return
    assert text is not None and regular.contains(B, text) and not regular.contains(A, text), text


def test_a_node_not_in_canonical_form_is_refused_or_answered_rightly():
    raw = {"op": "union", "args": [{"op": "chars", "ranges": [[120, 121], [97, 98]]},
                                   {"op": "literal", "codes": [120]}]}
    y = {"op": "literal", "codes": [121]}
    lowered = regular.lower_into([raw, y], z3)
    assert regular.contains(raw, "y")
    try:
        text = _solve(lowered, [raw, y], [])
    except (regular.InvalidTerm, KeyError, ValueError):
        return
    assert text is not None and regular.contains(raw, text) and regular.contains(y, text), text


def test_a_solver_character_outside_the_atoms_is_not_read_as_a_member():
    # a string the caller did not hold to `everything` may carry a
    # character below the first symbol; it is no atom's symbol
    lowered = regular.lower_into([A_TO_Z], z3)
    below = "\u4dff"
    try:
        text = lowered.decode(below)
    except (regular.InvalidTerm, KeyError, ValueError, IndexError):
        return
    pytest.fail(f"{below!r} is no atom's symbol, yet it was read as {text!r}")
