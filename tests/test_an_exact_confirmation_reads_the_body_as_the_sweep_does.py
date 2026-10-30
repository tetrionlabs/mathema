# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every place mathema evaluates a claim at a point in exact arithmetic
reads the function's body the way the finite sweep does
(`mathema._exact_body.exact_callee`): the derive witness's exact
reading and the conditioning at a miss (`evaluate.exact_at`), the
probe's exact verdict on a draw that passes only within the tolerance,
and the equivalence check's exact values. A helper that branches on
`isinstance(y, float)` takes the branch the computation took, so it
can neither confirm an equality the code does not compute nor deny one
it does; and where a decision of the body goes one way exactly and the
other in the function's own float run, the point has no exact reading:
the confirmation is undecided, never a falsification.

Each function under test runs a `while` loop so derive cannot read it."""
from fractions import Fraction

from mathema.analysis import effective_facts
from mathema.conjecture import check_conjectures, claim
from mathema.gates import _point_evaluator


def _spin():
    i = 0
    while i < 3:
        i += 1


def _nudge(y):
    if isinstance(y, float):
        return y + 1e-12
    return y


def nudged_half(x: float) -> float:
    _spin()
    return _nudge(x / 2)


def _scaled(y):
    if isinstance(y, float):
        return y
    return y * 100


def typed_half(x: float) -> float:
    _spin()
    return _scaled(x / 2)


def _stretch(y):
    if isinstance(y, float):
        return y * (1 + 1e-9)
    return y


def stretched_half(x: float) -> float:
    _spin()
    return _stretch(x / 2)


def sum_branch(x: float) -> int:
    _spin()
    if x / 10 + 0.2 == 0.3:
        return 1
    return 0


def _exact_at(fn, law, point):
    cj = claim(law)
    deps = _point_evaluator(cj, fn, effective_facts(fn), dict(cj.domain), {})
    assert deps is not None
    return deps["evaluate"].exact_at(point)


def test_the_exact_reading_at_a_point_takes_the_computations_type_branch():
    # x / 2 is a float in the computation: the helper returns it as it is
    assert _exact_at(typed_half, "for x in [1, 2], f(x) == x / 2",
                     {"x": Fraction(3, 2)}) == (Fraction(3, 4), Fraction(3, 4))


def test_the_exact_reading_at_a_point_keeps_what_the_helper_adds_to_a_float():
    left, right = _exact_at(nudged_half, "for x in [1, 2], f(x) == x / 2",
                            {"x": Fraction(3, 2)})
    assert right == Fraction(3, 4)
    assert left == Fraction(3, 4) + Fraction(1, 10 ** 12)


def test_a_point_whose_decision_differs_in_float_has_no_exact_reading():
    # 1/10 + 2/10 == 3/10 exactly; 0.1 + 0.2 is 0.30000000000000004
    assert _exact_at(sum_branch, "for x in [0, 2], f(x) == 0",
                     {"x": Fraction(1)}) is None


def test_a_draw_passing_within_tolerance_is_decided_by_the_body_read_exactly():
    # the float draws pass within the relative tolerance; read exactly,
    # the helper scales the value the computation holds as a float by
    # 1 + 1e-9, so the claim is false at the draw
    (p,) = check_conjectures(stretched_half, [claim(
        "for x in [1000, 2000], f(x) == x / 2", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "false here in exact arithmetic" in p.counterexample, \
        p.counterexample
