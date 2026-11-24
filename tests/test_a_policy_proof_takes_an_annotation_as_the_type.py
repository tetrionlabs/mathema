# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A missing-value policy is proven from a guard whose path tests
another parameter, where that parameter is annotated `float`, `int`,
`bool` or `str`: the proof takes the annotation as the parameter's type
and the row says so. With no annotation the parameter is any object,
whose `==` may raise, and with an annotation of a class whose `==`
raises the same holds: neither is proven."""
from typing import Optional

from mathema.conjecture import check_conjectures, claim

_VALUE = "for x in [0, 1], y in [-1, 1], f(x, y) == x * y"
_POLICY = "absent(f, x) raises(ArithmeticError)"


class Touchy:
    def __eq__(self, other):
        raise KeyError("touched")

    __hash__ = None


def annotated_float(x: Optional[float], y: float) -> float:
    if y == 0.123456:
        raise ZeroDivisionError("rare")
    if x is None:
        raise ArithmeticError("x is required")
    return x * y


def unannotated(x: Optional[float], y):
    if y == 0.123456:
        raise ZeroDivisionError("rare")
    if x is None:
        raise ArithmeticError("x is required")
    return x * y


def annotated_touchy(x: Optional[float], y: Touchy):
    if y == 0.123456:
        raise ZeroDivisionError("rare")
    if x is None:
        raise ArithmeticError("x is required")
    return x * y


def _raised(fn, *args):
    try:
        fn(*args)
    except BaseException as error:  # noqa: BLE001
        return error
    return None


def _row(fn):
    return check_conjectures(fn, [claim(_VALUE), claim(_POLICY)])[-1]


def test_the_policy_is_proven_assuming_the_annotation():
    for y in (-1.0, 0.0, 0.123456, 1.0):
        assert isinstance(_raised(annotated_float, None, y), ArithmeticError)
    row = _row(annotated_float)
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "assuming y is a float, as annotated" in row.note, row.note
    assert row.meta["mathema.assumptions"]["annotations"] == ["y is a float, as annotated"]


def test_a_parameter_with_no_annotation_is_any_object():
    assert isinstance(_raised(unannotated, None, Touchy()), KeyError)
    row = _row(unannotated)
    assert row.verdict != "proven", (row.verdict, row.route, row.note)


def test_an_annotation_whose_comparison_raises_is_not_taken_as_a_number():
    assert isinstance(_raised(annotated_touchy, None, Touchy()), KeyError)
    row = _row(annotated_touchy)
    assert row.verdict != "proven", (row.verdict, row.route, row.note)
