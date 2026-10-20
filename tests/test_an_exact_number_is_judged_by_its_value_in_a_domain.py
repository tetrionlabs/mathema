# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `Decimal` or a `Fraction` is an exact number, and a numeric domain
judges it by its value: `Decimal('5.5')` lies in `[0, 10]`, and
`Decimal('3')` is an integer. An endpoint written `0.3` is the number
3/10 to an exact number, so `Decimal('0.3')` lies in `[0, 0.3]` while
`Decimal('0.30000000000000001')` does not. A numpy scalar is the number
it holds. A domain that is not numeric (strings, a language) keeps
judging the value as the object it is.
"""
from decimal import Decimal
from fractions import Fraction

import pytest

from mathema.domain import Interval, domain_contains


@pytest.mark.parametrize("value", [Decimal("5.5"), Fraction(11, 2),
                                   Decimal("0"), Decimal("10")])
def test_an_exact_number_inside_a_real_interval_is_a_member(value):
    assert domain_contains(value, (0, 10)) is True


@pytest.mark.parametrize("value", [Decimal("10.5"), Fraction(-1, 3),
                                   Decimal("-0.0001")])
def test_an_exact_number_outside_a_real_interval_is_not(value):
    assert domain_contains(value, (0, 10)) is False


def test_an_endpoint_written_as_a_decimal_is_that_number_to_an_exact_value():
    bound = Interval(0, 0.3, True, True)
    assert domain_contains(Decimal("0.3"), bound) is True
    assert domain_contains(Fraction(3, 10), bound) is True
    assert domain_contains(Decimal("0.30000000000000001"), bound) is False


def test_an_open_endpoint_excludes_the_exact_endpoint():
    assert domain_contains(Decimal("10"), Interval(0, 10, True, False)) is False


@pytest.mark.parametrize("value, bound, expected", [
    (Decimal("3"), "Z", True),
    (Decimal("3.5"), "Z", False),
    (Fraction(4, 2), "Z", True),
    (Decimal("-1"), "N", False),
    (Decimal("7"), "N", True),
])
def test_an_exact_number_meets_the_integer_sets_by_its_value(value, bound,
                                                             expected):
    assert domain_contains(value, bound) is expected


def test_a_numpy_integer_is_an_integer():
    numpy = pytest.importorskip("numpy")
    assert domain_contains(numpy.int64(3), "Z") is True
    assert domain_contains(numpy.float64(5.5), (0, 10)) is True


def test_an_exact_number_lies_in_the_complex_plane():
    assert domain_contains(Decimal("2.5"), "C") is True
    assert domain_contains(Fraction(1, 3), "C") is True


def test_an_exact_number_is_not_a_string():
    assert domain_contains(Decimal("1"), "S") is False


def test_a_bool_stays_outside_every_numeric_domain():
    assert domain_contains(True, (0, 10)) is False
