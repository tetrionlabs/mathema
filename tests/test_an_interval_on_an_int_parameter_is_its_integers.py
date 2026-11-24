# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An interval bound to a parameter annotated `int` ranges over the
integers of the interval. A body that raises ValueError at each of them
is proven there by running the five points, and the row says so; the
same body with no annotation, where the interval holds the floats too,
raises OverflowError at -3.0 and is not proven."""
from mathema.conjecture import check_conjectures, claim

_CLAIM = "for x in [-5, -1], raises(f(x), ValueError)"


def over_the_integers(x: int) -> int:
    if x < 0:
        y = x * 10 ** 300
        w = y * y
        v = w // 10 ** 600
        u = v + 0.5  # noqa: F841
        raise ValueError("neg")
    return x


def over_the_reals(x):
    if x < 0:
        y = x * 10 ** 300
        w = y * y
        v = w // 10 ** 600
        u = v + 0.5  # noqa: F841
        raise ValueError("neg")
    return x


def _raised(fn, x):
    try:
        fn(x)
    except BaseException as error:  # noqa: BLE001
        return type(error).__name__
    return None


def test_the_integers_of_the_interval_are_the_points_run():
    assert {_raised(over_the_integers, x) for x in range(-5, 0)} == {"ValueError"}
    (row,) = check_conjectures(over_the_integers, [claim(_CLAIM)])
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)
    assert "5 points" in f"{row.sketch} {row.note}", (row.sketch, row.note)


def test_the_same_body_over_the_reals_is_not_proven():
    assert _raised(over_the_reals, -3.0) == "OverflowError"
    for route in ("derive", "best"):
        (row,) = check_conjectures(over_the_reals, [claim(_CLAIM, route=route)])
        assert row.verdict != "proven", (route, row.verdict, row.sketch, row.note)
