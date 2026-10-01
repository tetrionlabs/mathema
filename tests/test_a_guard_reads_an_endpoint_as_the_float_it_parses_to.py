# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An interval endpoint written `0.1` denotes the float it parses to,
0.1000000000000000055511151231257827021181583404541015625, the same
value the derive route reads. The `@enforce_domain` guard judges an
exact number against that value: `Fraction(1, 10)` and `Decimal('0.1')`
lie below it, so both are inside `[0, 0.1)` as well as `[0, 0.1]`, the
float's own exact value is inside only the closed interval, and a
number just above it is inside neither."""
from decimal import Decimal
from fractions import Fraction

import pytest

from mathema import claims_decorator
from mathema.authoring import DomainError, enforce_domain

_TENTH = Fraction(0.1)
_ABOVE = _TENTH + Fraction(1, 10 ** 40)


@enforce_domain()
@claims_decorator("for x in [0, 0.1), f(x) >= 0")
def half_open(x: float) -> float:
    return x


@enforce_domain()
@claims_decorator("for x in [0, 0.1], f(x) >= 0")
def closed(x: float) -> float:
    return x


def test_the_endpoint_is_the_exact_value_of_the_float():
    assert _TENTH == Fraction(
        1000000000000000055511151231257827021181583404541015625,
        10 ** 55)


@pytest.mark.parametrize("value", [Fraction(1, 10), Decimal("0.1")],
                         ids=repr)
def test_one_tenth_lies_inside_both_intervals(value):
    assert half_open(value) == value
    assert closed(value) == value


def test_the_floats_exact_value_is_inside_only_the_closed_interval():
    for value in (_TENTH, Decimal(0.1), 0.1):
        with pytest.raises(DomainError):
            half_open(value)
        assert closed(value) == value


@pytest.mark.parametrize("value", [_ABOVE, Decimal(str(Decimal(0.1)) + "1")],
                         ids=["fraction", "decimal"])
def test_a_number_just_above_the_float_is_inside_neither(value):
    with pytest.raises(DomainError):
        half_open(value)
    with pytest.raises(DomainError):
        closed(value)
