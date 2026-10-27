# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim's own side is evaluated exactly, or the point is not
evaluable: an infinity the claim's float arithmetic produced from finite
values, at a point where no call returned one and the sides have no
exact reading, is never read as a miss. An infinity the claim writes
(`inf`, `oo`) is the claim's own and is compared as written."""
from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.types import Mat  # noqa: E402


def scaled(c: float, A: Mat("n", "n")):
    return A


def ident(x: float) -> float:
    return x


def test_an_overflow_of_the_claims_own_arithmetic_is_not_counted():
    # trace(c A) = c trace(A) for every real c (trace is linear); at
    # c near -1.8e308 the right side overflows float64 to -inf
    (p,) = check_conjectures(scaled, [claim(
        "trace(c * A) ~= c * trace(A)", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    assert "where the claim's own arithmetic overflowed float64" in p.note, \
        p.note


@pytest.mark.parametrize("law", ["for x in [0, 1], f(x) < inf",
                                 "for x in [0, 1], f(x) > -inf",
                                 "for x in [0, 1], f(x) <= oo"])
def test_an_infinity_the_claim_writes_is_compared_as_written(law):
    (p,) = check_conjectures(ident, [claim(law, route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "overflowed" not in (p.note or ""), p.note


def test_an_overflow_against_a_finite_side_decides_by_its_sign():
    # an infinity from finite operands stands for a value beyond every
    # float: against a finite side it decides the relation by its sign,
    # so abs(c trace(A)) <= 1e308 is false wherever c trace(A) > 1e308
    # (c = 1.5e308, A = [[1.0]] is such a point)
    (p,) = check_conjectures(scaled, [claim(
        "abs(c * trace(A)) <= 1e308", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_an_overflow_against_a_written_infinity_is_a_finite_value():
    # c trace(A) is finite for every c and A, so it is never inf
    (p,) = check_conjectures(scaled, [claim(
        "c * trace(A) != inf", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)
