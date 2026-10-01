# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A loop that builds a value and then divides by it divides by zero
wherever that value is zero. A claim over such a point is not proven
from the loop's closed form, which reads the quotient without its
pole."""
import pytest

from mathema.conjecture import check_conjectures, claim


def inverse_of_accumulated(x: float) -> float:
    s = 0.0
    for _ in range(1):
        s += x
    return 1 / s


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("text", [
    "f(x) * x == 1",
    "for x in [-3, 5], abs(f(x)) >= 0",
])
def test_the_pole_of_a_loop_written_reciprocal_is_not_proven_away(text):
    with pytest.raises(ZeroDivisionError):
        inverse_of_accumulated(0.0)
    (p,) = check_conjectures(inverse_of_accumulated,
                             [claim(text, route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch)

