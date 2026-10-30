# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A body that builds an exact number from exact arguments
(`Fraction(1, 3)`, `Fraction(n, 4)`, `Decimal("0.1")`, `Decimal(n)`) is
read exactly: the number is exact by construction, so the exact reading
builds the same one. `Decimal(x)` of a float `x` is exact too: a float
is a dyadic rational, which a Decimal holds digit for digit, so the
reading builds the Decimal of the point's coordinate; a rational with no
finite decimal expansion has none. `Fraction(x)` of a float `x` has no
exact reading beyond the float's own value, and the point is not read
exactly."""
from decimal import Decimal
from fractions import Fraction

import pytest

from mathema._exact_body import NotExact, exact_callee, unfaithful
from mathema.conjecture import check_conjectures, claim


def _spin():
    i = 0
    while i < 3:
        i += 1


def third(n: int) -> Fraction:
    _spin()
    return Fraction(1, 3) + n


def quarters(n: int) -> Fraction:
    _spin()
    return Fraction(n, 4)


def tenths(n: int) -> Decimal:
    _spin()
    return Decimal("0.1") * n


def halves(n: int) -> Decimal:
    _spin()
    return Decimal(n) / 2


def from_float(x: float) -> Fraction:
    _spin()
    return Fraction(x) / 2


def decimal_from_float(x: float) -> float:
    _spin()
    return float(Decimal(x) / 2)


def _v(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.parametrize("fn,law", [
    (third, "for n in {0, 1, 2}, f(n) == n + 1/3"),
    (quarters, "for n in {0, 1, 2, 3}, f(n) == n / 4"),
    (tenths, "for n in {0, 1, 7}, f(n) == n / 10"),
    (halves, "for n in {0, 1, 3}, f(n) == n / 2"),
])
def test_an_exact_construction_is_proven_exactly(fn, law):
    p = _v(fn, law)
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), \
        (p.verdict, p.route, p.sketch)
    assert unfaithful(fn) == [], unfaithful(fn)


def test_an_exactly_false_claim_on_an_exact_construction_falsifies():
    # n + 1/3 against n + 3333333333333333/10**16: false by 1/(3 * 10**16)
    p = _v(third, "for n in [0, 10] subset Z, f(n) <= n + 0.3333333333333333")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    witness = p.meta["mathema.exact_witness"]
    assert witness["reading"] == "mathematics", witness


@pytest.mark.parametrize("fn", [from_float])
def test_a_construction_from_a_float_is_not_read_exactly(fn):
    with pytest.raises(NotExact):
        exact_callee(fn)(Fraction(1, 10))


def test_a_decimal_of_the_points_coordinate_is_read_exactly():
    # Decimal(1/10) is 0.1 exactly, halved 0.05: f(1/10) is 1/20
    assert exact_callee(decimal_from_float)(Fraction(1, 10)) == Fraction(1, 20)
    # 1/3 has no finite decimal expansion, so no Decimal equals it
    with pytest.raises(NotExact):
        exact_callee(decimal_from_float)(Fraction(1, 3))
