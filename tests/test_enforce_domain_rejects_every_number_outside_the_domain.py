# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`@enforce_domain` declares `excluded_outside_domain` proven by
construction, so its guard rejects every number outside the declared
domain whatever its numeric type: a bool, a numpy scalar, a Fraction
and a Decimal are judged by their value like an int or a float, and a
number inside the domain still passes."""
from decimal import Decimal
from fractions import Fraction

import pytest

import mathema
from mathema.authoring import DomainError, enforce_domain

np = pytest.importorskip("numpy")


@enforce_domain({"x": (2, 3)})
def doubled(x: float) -> float:
    return x * 2


@enforce_domain({"n": "Z"})
def counted(n: int) -> int:
    return n


_OUTSIDE = [True, False, np.True_, np.int64(5), np.float32(5.0), np.float64(5.0),
            np.float16(1.0), np.int8(-1), np.complex128(5 + 0j),
            Fraction(5), Fraction(7, 2), Decimal(5), Decimal("3.5"),
            Fraction(3) + Fraction(1, 10 ** 30),
            Decimal("1.99999999999999999999999999999999999999")]


@pytest.mark.parametrize("value", _OUTSIDE, ids=repr)
def test_a_number_outside_the_interval_is_rejected(value):
    with pytest.raises(DomainError):
        doubled(value)


@pytest.mark.parametrize("value", [np.float32(2.5), np.int64(2),
                                   Fraction(5, 2), Decimal("2.5"), 3, 2.0],
                         ids=repr)
def test_a_number_inside_the_interval_passes(value):
    assert doubled(value) == value * 2


@pytest.mark.parametrize("value", [np.float64(1.5), Fraction(3, 2),
                                   Decimal("1.5"), True], ids=repr)
def test_a_non_integer_is_rejected_by_an_integer_domain(value):
    with pytest.raises(DomainError):
        counted(value)


@pytest.mark.parametrize("value", [np.int64(4), Fraction(4), Decimal(4)],
                         ids=repr)
def test_an_integer_of_any_type_passes_an_integer_domain(value):
    assert counted(value) == 4


def test_a_sequence_element_of_any_numeric_type_is_judged():
    @enforce_domain({"xs": (0, 1)})
    def total(xs: list) -> float:
        return float(sum(xs))

    with pytest.raises(DomainError):
        total([0.5, np.float32(2.0)])
    with pytest.raises(DomainError):
        total(np.array([0.5, 2.0], dtype=np.float32))
    assert total([Fraction(1, 2), np.float32(0.25)]) == 0.75


def test_the_exclusion_stays_proven_and_its_probe_finds_nothing():
    rec = mathema.check(doubled)
    row = next(p for p in rec.probes
               if p.name.startswith("excluded_outside_domain"))
    assert row.verdict == "proven", (row.verdict, row.note)
    for value in _OUTSIDE:
        with pytest.raises(DomainError):
            doubled(value)
