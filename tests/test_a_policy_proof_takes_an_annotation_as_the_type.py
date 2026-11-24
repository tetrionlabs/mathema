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


def default_is_none(x: Optional[float], y: float = None):
    if y == 0.123456:
        raise ZeroDivisionError("rare")
    if x is None:
        raise ArithmeticError("x is required")
    return x * y


def default_is_touchy(x: Optional[float], y: float = Touchy()):  # noqa: B008
    if y == 0.123456:
        raise ZeroDivisionError("rare")
    if x is None:
        raise ArithmeticError("x is required")
    return x * y


def keyword_default_is_text(x: Optional[float], *, y: float = "a"):
    if y == 0.123456:
        raise ZeroDivisionError("rare")
    if x is None:
        raise ArithmeticError("x is required")
    return x * y


def default_is_a_float(x: Optional[float], y: float = 2.0) -> float:
    if y == 0.123456:
        raise ZeroDivisionError("rare")
    if x is None:
        raise ArithmeticError("x is required")
    return x * y


def test_a_default_of_another_type_contradicts_the_annotation():
    assert not isinstance(default_is_none.__defaults__[0], float)
    assert isinstance(_raised(default_is_touchy, None), KeyError)
    said = {
        default_is_none: "y is annotated float but its default None is not a float, "
                         "so the annotation is not taken as its type",
        default_is_touchy: "y is annotated float but its default of type Touchy is not "
                           "a float, so the annotation is not taken as its type",
    }
    for fn, words in said.items():
        row = _row(fn)
        # the verdict the same body has with y unannotated
        assert row.verdict == _row(unannotated).verdict == "holds", \
            (fn.__name__, row.verdict, row.route, row.note)
        assert words in row.note, row.note
        assert "annotations" not in row.meta.get("mathema.assumptions", {})
    row = check_conjectures(keyword_default_is_text, [claim(_POLICY)])[-1]
    assert row.verdict != "proven", (row.verdict, row.route, row.note)


def test_a_default_of_the_annotated_type_keeps_the_proof():
    for args in ((None,), (None, 0.123456), (None, -1.0)):
        assert isinstance(_raised(default_is_a_float, *args), ArithmeticError)
    row = _row(default_is_a_float)
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "assuming y is a float, as annotated" in row.note, row.note
