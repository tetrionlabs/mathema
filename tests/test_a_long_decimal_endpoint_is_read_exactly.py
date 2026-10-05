# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A domain endpoint written with sixteen or seventeen significant
digits is the number written, never a rounding of it to fifteen. Read
at fifteen digits, `0.3472963553338606` becomes `0.347296355333861`,
which lies past the root `0.34729635533386069...` of `x^3 - 3x + 1`,
so a strict claim that fails at that root would be proven."""
import pytest
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.domain import Interval
from mathema.symbolic._extensive import _sturm_decide
from mathema.symbolic._proof_support import _exact_endpoint


def negated_square(x: float) -> float:
    return -(x ** 3 - 3 * x + 1) ** 2


def test_an_endpoint_keeps_every_digit_it_was_written_with():
    for written in ("0.3472963553338606", "0.3472963553338607",
                    "1.414213562373095", "1.4142135623730951", "0.1", "2.0"):
        assert _exact_endpoint(sympy.Float(float(written))) == sympy.Rational(written)


def test_a_root_just_inside_a_long_endpoint_breaks_a_strict_claim():
    x = sympy.Symbol("x", real=True)
    result = _sturm_decide(-(x ** 3 - 3 * x + 1) ** 2, "<",
                           {"x": Interval(0.3472963553338606, 0.5, True, True)},
                           {"x": x})
    assert result.status == "disproven"


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("law", [
    "for x in [0.3472963553338606, 0.5], f(x) < 0",
    "for x in [0.3472963553338606, 0.5], f(x) != 0",
    "for x in [0.3472963553338606, 0.3472963553338607], f(x) < 0",
])
def test_a_strict_claim_over_a_long_endpoint_is_falsified_at_the_root(law):
    (p,) = check_conjectures(negated_square, [claim(law)], extensive=True)
    assert p.verdict == "falsified"
    assert p.counterexample == "x = 0.34729635533386066"
    assert negated_square(0.34729635533386066) == 0.0
