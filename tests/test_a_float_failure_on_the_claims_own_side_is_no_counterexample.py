# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim's own side is mathematics. When evaluating it in floats
fails at a point (`exp(-1e6)` underflows to 0.0, so a division by it
raises ZeroDivisionError) the function is not at fault there: the side
is read exactly, and the point is decided by that reading, or left
undecided when there is none. A division by zero the claim states in
exact arithmetic still falsifies."""
import math

from mathema.conjecture import check_conjectures, claim


def opaque_identity(x):
    return math.fsum([x])


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


def test_an_underflow_on_the_claims_own_side_does_not_falsify():
    p = _row(opaque_identity, "for x in R, exp(f(x)) / exp(f(x)) == 1")
    assert p.verdict != "falsified", (p.verdict, p.route, p.counterexample)


def test_a_division_by_zero_the_claim_states_exactly_still_falsifies():
    p = _row(opaque_identity, "for x in [0, 2], 1 / (f(x) - 1) != 0")
    assert p.verdict == "falsified", (p.verdict, p.route, p.counterexample)
