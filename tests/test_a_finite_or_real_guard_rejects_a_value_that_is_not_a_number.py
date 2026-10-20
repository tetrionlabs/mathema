# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`@enforce_structure` on a parameter declared `Finite` or `Real`
rejects an argument that is not a number, nor a vector or matrix of
numbers (None, a string, a list holding None), as it rejects an
infinite or complex one, with or without numpy installed."""

from typing import Annotated

import pytest

from mathema.authoring import enforce_structure
from mathema.types import Finite, Mat, Real


@enforce_structure()
def finite_matrix(a: Mat("n", "n", Finite)) -> list:
    """Needs a finite matrix."""
    return a


@enforce_structure()
def real_matrix(a: Mat("n", "n", Real)) -> list:
    """Needs a real matrix."""
    return a


@enforce_structure()
def finite_number(x: Annotated[float, Finite]) -> float:
    """Needs a finite number."""
    return x


@enforce_structure()
def real_number(x: Annotated[float, Real]) -> float:
    """Needs a real number."""
    return x


_NOT_NUMBERS = [None, "abc", [None], [[1.0, None], [0.0, 1.0]],
                [[1.0, 2.0], [3.0]]]


@pytest.mark.parametrize("value", _NOT_NUMBERS, ids=repr)
@pytest.mark.parametrize("fn,prop", [
    (finite_matrix, "is_finite"), (real_matrix, "is_real"),
    (finite_number, "is_finite"), (real_number, "is_real"),
], ids=["finite matrix", "real matrix", "finite number", "real number"])
def test_a_value_that_is_not_a_number_is_rejected(fn, prop, value):
    with pytest.raises(ValueError, match=f"not {prop}.*not a number"):
        fn(value)


def test_a_number_or_a_matrix_of_numbers_is_accepted():
    m = [[1.0, 2.0], [3.0, 4.0]]
    assert finite_matrix(m) == m
    assert real_matrix(m) == m
    assert finite_number(2.5) == 2.5
    assert real_number(1 + 0j) == 1 + 0j


def test_an_infinite_or_complex_value_is_still_rejected_without_the_reason():
    with pytest.raises(ValueError, match=r"not is_finite \(finite\)$"):
        finite_number(float("inf"))
    with pytest.raises(ValueError, match=r"not is_real \(real\)$"):
        real_number(1 + 2j)
