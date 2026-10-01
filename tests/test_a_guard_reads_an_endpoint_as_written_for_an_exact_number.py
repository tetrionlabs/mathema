# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An interval endpoint written `0.1` is the number as written, 1/10, in
exact arithmetic, and the float `0.1` in float arithmetic. The
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
from mathema.domain import Interval

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


@pytest.mark.parametrize("float_type", [np.float16, np.float32, np.float64],
                         ids=lambda t: t.__name__)
def test_a_float_meets_the_endpoint_in_its_own_float_type(float_type):
    value = float_type("0.1")
    with pytest.raises(DomainError):
        half_open(value)
    assert closed(value) == value


@pytest.mark.parametrize("float_type", [np.float16, np.float32],
                         ids=lambda t: t.__name__)
def test_a_narrow_float_next_to_the_endpoint_is_judged_in_its_type(float_type):
    value = float_type("0.1")
    above = np.nextafter(value, float_type(1))
    below = np.nextafter(value, float_type(0))
    with pytest.raises(DomainError):
        closed(above)
    assert half_open(below) == below


def test_an_array_of_narrow_floats_meets_the_endpoint_in_its_type():
    from mathema import enforce_dimensions

    @enforce_dimensions()
    @claims_decorator("for xs in [0, 0.1]^3, f(xs) >= 0")
    def total(xs: np.ndarray) -> float:
        return float(np.asarray(xs, dtype=float).sum())

    assert total(np.full(3, "0.1", dtype=np.float32)) > 0
    from mathema.authoring import DimensionError
    with pytest.raises(DimensionError):
        total(np.full(3, np.nextafter(np.float32("0.1"), np.float32(1))))


@pytest.mark.parametrize("float_type,big", [(np.float16, 1e5),
                                            (np.float32, 1e39)],
                         ids=["float16", "float32"])
def test_an_endpoint_beyond_a_narrow_type_reads_as_its_infinity(float_type,
                                                                 big):
    @enforce_domain({"x": (0, big)})
    def scaled(x: float) -> float:
        return 2 * x

    @enforce_domain({"x": Interval(-big, 0.0, False, True)})
    def below(x: float) -> float:
        return x

    for value in (float_type(1.0), np.finfo(float_type).max):
        assert scaled(value) == 2 * value
    assert below(float_type(-1.0)) == float_type(-1.0)
    assert below(-np.finfo(float_type).max) == -np.finfo(float_type).max
    # an infinite argument is still outside a finite endpoint
    with pytest.raises(DomainError):
        scaled(float_type(np.inf))
    with pytest.raises(DomainError):
        below(float_type(-np.inf))


def test_a_float16_array_against_an_endpoint_beyond_its_range():
    from mathema import enforce_dimensions
    from mathema.authoring import DimensionError

    @enforce_dimensions()
    @claims_decorator("for xs in [0, 1e5]^3, f(xs) >= 0")
    def total(xs: np.ndarray) -> float:
        return float(np.asarray(xs, dtype=float).sum())

    assert total(np.ones(3, dtype=np.float16)) == 3.0
    with pytest.raises(DimensionError):
        total(np.full(3, np.inf, dtype=np.float16))
