# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An interval endpoint written `0.1` is the number as written, 1/10, in
exact arithmetic, and the float `0.1` in the float carrier. The
`@enforce_domain` guard compares each argument in its own kind: a float
against the endpoint as a float, so `0.1` is inside `[0, 0.1]` and
outside `[0, 0.1)`; an exact number (an int, a Fraction, a Decimal, a
numpy integer) against the written value, so `Fraction(1, 10)` and
`Decimal('0.1')` are inside `[0, 0.1]` and outside `[0, 0.1)`, and the
exact value of the float 0.1, a little above 1/10, is outside both."""
from decimal import Decimal
from fractions import Fraction

import pytest

from mathema import claims_decorator
from mathema.authoring import DomainError, enforce_domain

np = pytest.importorskip("numpy")


@enforce_domain()
@claims_decorator("for x in [0, 0.1), f(x) >= 0")
def half_open(x: float) -> float:
    return x


@enforce_domain()
@claims_decorator("for x in [0, 0.1], f(x) >= 0")
def closed(x: float) -> float:
    return x


@enforce_domain()
@claims_decorator("for n in [0, 3), f(n) >= 0")
def below_three(n: int) -> int:
    return n


@pytest.mark.parametrize("value", [0.1, np.float64(0.1)], ids=repr)
def test_a_float_meets_the_endpoint_as_a_float(value):
    with pytest.raises(DomainError):
        half_open(value)
    assert closed(value) == value


@pytest.mark.parametrize("value", [Fraction(1, 10), Decimal("0.1")],
                         ids=repr)
def test_an_exact_number_meets_the_endpoint_as_written(value):
    with pytest.raises(DomainError):
        half_open(value)
    assert closed(value) == value


@pytest.mark.parametrize("value", [Fraction(0.1), Decimal(0.1)], ids=repr)
def test_the_exact_value_of_the_float_lies_above_the_written_endpoint(value):
    with pytest.raises(DomainError):
        half_open(value)
    with pytest.raises(DomainError):
        closed(value)


@pytest.mark.parametrize("value", [Fraction(1, 10) - Fraction(1, 10 ** 30),
                                   Decimal("0.0999999999999999999999999")],
                         ids=repr)
def test_an_exact_number_just_below_is_inside_both(value):
    assert half_open(value) == value
    assert closed(value) == value


@pytest.mark.parametrize("value", [3, np.int64(3), Fraction(3), Decimal(3)],
                         ids=repr)
def test_an_integer_endpoint_reads_the_same_for_every_kind(value):
    with pytest.raises(DomainError):
        below_three(value)
    assert below_three(value - 1) == value - 1
