# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim word over complex numbers keeps the exact value of each part.

`sum`, `prod` and `dot` of complex numbers whose real or imaginary part
lies beyond float range give that part exact (a `Fraction`), as the real
words do, and the other part as the float it rounds to. No part is
converted to a float that cannot hold it, so nothing raises
`OverflowError`. A complex value within float range is an ordinary
Python complex. A claim compares such a value with a function's result
part by part, exactly.
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")

import math  # noqa: E402
import sys  # noqa: E402
from fractions import Fraction  # noqa: E402

import numpy as np  # noqa: E402

from mathema._linalg_eval import FUNCTIONS  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402

_BIG = sys.float_info.max
_B = Fraction(1.7e308)


def _z(*xs):
    return np.array(xs, dtype=complex)


def test_both_parts_of_a_sum_beyond_float_range_stay_exact():
    value = FUNCTIONS["sum"](_z(1.7e308 + 1.7e308j, 1.7e308 + 1.7e308j))
    assert value.real == 2 * _B and value.imag == 2 * _B
    assert isinstance(value.real, Fraction)
    assert isinstance(value.imag, Fraction)


def test_a_real_part_beyond_float_range_leaves_the_imaginary_part_a_float():
    value = FUNCTIONS["sum"](_z(1.7e308 + 1j, 1.7e308 + 2j))
    assert value.real == 2 * _B and isinstance(value.real, Fraction)
    assert value.imag == 3.0 and isinstance(value.imag, float)


def test_an_imaginary_part_beyond_float_range_leaves_the_real_part_a_float():
    value = FUNCTIONS["sum"](_z(1 + 1.7e308j, 2 + 1.7e308j))
    assert value.imag == 2 * _B and isinstance(value.imag, Fraction)
    assert value.real == 3.0 and isinstance(value.real, float)


def test_the_mean_of_large_complex_numbers_is_the_exact_mean():
    xs = _z(1.7e308 + 1.7e308j, 1.7e308 - 1.7e308j, 1.7e308 + 0j)
    assert FUNCTIONS["mean"](xs) == complex(1.7e308, 0.0)


def test_a_product_beyond_float_range_keeps_each_part_exact():
    value = FUNCTIONS["prod"](_z(1e200 + 1e200j, 1e200 + 0j))
    assert value.real == Fraction(1e200) ** 2 and value.imag == value.real
    assert isinstance(value.real, Fraction)


def test_a_dot_beyond_float_range_keeps_each_part_exact():
    value = FUNCTIONS["dot"](_z(1e200 + 0j), _z(0 + 1e200j))
    assert value.real == 0.0 and isinstance(value.real, float)
    assert value.imag == Fraction(1e200) ** 2


def test_a_complex_value_within_float_range_is_a_python_complex():
    xs = _z(1 + 1j, 2 + 0j, 3 - 1j, -2 + 0.5j)
    assert type(FUNCTIONS["sum"](xs)) is complex
    assert FUNCTIONS["sum"](xs) == 4 + 0.5j
    assert type(FUNCTIONS["mean"](xs)) is complex
    assert FUNCTIONS["mean"](xs) == 1 + 0.125j
    assert type(FUNCTIONS["prod"](xs[:2])) is complex


def test_a_sum_that_cancels_back_into_float_range_is_a_python_complex():
    value = FUNCTIONS["sum"](_z(1.7e308 + 1.7e308j, 1.7e308 + 1.7e308j,
                                -1.7e308 - 1.7e308j))
    assert type(value) is complex and value == 1.7e308 + 1.7e308j


def test_a_value_beyond_float_range_is_not_a_float_complex():
    value = FUNCTIONS["sum"](_z(1.7e308 + 1j, 1.7e308 + 1j))
    assert value != complex(_BIG, 2.0)
    assert value != complex(math.inf, 2.0)
    assert value == value


def _float_total(a) -> float:
    total = 0.0
    for v in a:
        total += float(v)
    return total


def _capped(a) -> complex:
    """The float sum of a*(1+1j), each part capped at the largest float."""
    total = _float_total(a)
    capped = min(total, _BIG)
    return complex(capped, capped)


def _imaginary_capped(a) -> complex:
    """The float sum of a*1j, the imaginary part capped."""
    return complex(0.0, min(_float_total(a), _BIG))


def _float_sum(a) -> complex:
    """The float sum of a*(1+1j)."""
    total = _float_total(a)
    return complex(total, total)


_PAST = "for a in [1.2e308, 1.7e308]^n \\ {\u2205}, assuming dim(a) >= 2, "
_WITHIN = "for a in [1e100, 2e100]^n \\ {\u2205}, assuming dim(a) >= 2, "


def _verdict(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    return p


@pytest.mark.parametrize("fn, text, verdict", [
    (_capped, _PAST + "f(a) == sum(a * (1 + 1j))", "falsified"),
    (_capped, _PAST + "f(a) != sum(a * (1 + 1j))", "holds"),
    (_imaginary_capped, _PAST + "f(a) == sum(a * 1j)", "falsified"),
    (_imaginary_capped, _PAST + "f(a) != sum(a * 1j)", "holds"),
])
def test_a_function_capped_below_the_exact_complex_sum_is_unequal_to_it(
        fn, text, verdict):
    p = _verdict(fn, text)
    assert verdict == p.verdict, (p.verdict, p.note, p.counterexample)
    assert "OverflowError" not in (p.note or "") + (p.counterexample or "")


def test_a_claim_over_a_complex_sum_within_float_range_holds():
    p = _verdict(_float_sum, _WITHIN + "f(a) ~= sum(a * (1 + 1j))")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
