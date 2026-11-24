# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An `enforce_structure` guard judges its parameter before the function
runs, so a `raises` claim is proven only where the guard lets through
every value the call passes: every member of a finite set, every real
number of an interval for `Finite` and `Real`, the constant written in
the call. An infinity in the set, text or nan in the guarded place, and a
guarded parameter the claim does not bind are refused by the guard with
its own ValueError, and the claim is not proven."""
from typing import Annotated

import pytest

from mathema.authoring import enforce_structure
from mathema.conjecture import check_conjectures, claim
from mathema.types import Finite

_NEG = "for x in [-5, -1], "
_INF = float("inf")


@enforce_structure()
def first_is_finite(x: Annotated[float, Finite], y):
    if x < 0:
        raise KeyError("n")
    return x


@enforce_structure()
def second_is_finite(x, y: Annotated[float, Finite]):
    if x < 0:
        raise KeyError("n")
    return x


def _raised(fn, *args):
    try:
        fn(*args)
    except BaseException as error:  # noqa: BLE001
        return type(error).__name__
    return None


@pytest.mark.parametrize("fn,text,points", [
    (first_is_finite, _NEG + "raises(f(x, 1), KeyError)", [(-5.0, 1), (-3.3, 1), (-1, 1)]),
    (first_is_finite, "for x in {-2, -1}, raises(f(x, 1), KeyError)", [(-2, 1), (-1, 1)]),
    (second_is_finite, _NEG + "y in [1, 2], raises(f(x, y), KeyError)",
     [(-5.0, 1), (-3.3, 1.5), (-1, 2)]),
    (second_is_finite, _NEG + "y in {1, 2}, raises(f(x, y), KeyError)",
     [(-5.0, 1), (-1, 2)]),
    (second_is_finite, _NEG + "raises(f(x, 1/2), KeyError)", [(-5.0, 0.5), (-1, 0.5)]),
    (second_is_finite, _NEG + "raises(f(x, pi), KeyError)", [(-5.0, 3.14), (-1, 3.14)]),
    (second_is_finite, _NEG + "raises(f(x, (1, 2)), KeyError)",
     [(-5.0, (1, 2)), (-1, (1, 2))]),
], ids=["an interval of finite numbers", "a set of finite numbers",
        "the guarded parameter over an interval", "the guarded parameter over a set",
        "arithmetic in the guarded place", "pi in the guarded place",
        "a tuple of numbers in the guarded place"])
def test_a_guard_that_lets_every_value_through_keeps_the_proof(fn, text, points):
    assert {_raised(fn, *point) for point in points} == {"KeyError"}
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn,text,point", [
    (first_is_finite, "for x in {-inf, -1}, raises(f(x, 1), KeyError)", (-_INF, 1)),
    (first_is_finite, "for x in [-oo, -1], raises(f(x, 1), KeyError)", (-_INF, 1)),
    (second_is_finite, _NEG + "raises(f(x, 'a'), KeyError)", (-2.0, "a")),
    (second_is_finite, _NEG + "raises(f(x, nan), KeyError)", (-2.0, float("nan"))),
    (second_is_finite, _NEG + "raises(f(x, 1e999), KeyError)", (-2.0, _INF)),
    (second_is_finite, _NEG + "raises(f(x, (1, inf)), KeyError)", (-2.0, (1, _INF))),
    (second_is_finite, _NEG + "y in {1, inf}, raises(f(x, y), KeyError)", (-2.0, _INF)),
], ids=["an infinity in the set", "an interval closed at an infinity",
        "text in the guarded place", "nan in the guarded place",
        "a literal that overflows to infinity", "a tuple holding an infinity",
        "an infinity in the guarded parameter's set"])
@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_value_the_guard_refuses_is_not_read_past(fn, text, point, route):
    assert _raised(fn, *point) == "ValueError"
    (row,) = check_conjectures(fn, [claim(text, route=route)])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)
