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
