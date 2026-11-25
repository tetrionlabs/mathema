# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim whose call takes a remainder by zero (`f(x, 1 % 0)`) is a claim
about a call that cannot be made: evaluating the argument raises
ZeroDivisionError before the function runs. The claim gets a row that is
not proven and says so; checking it does not raise."""
import pytest

from mathema.conjecture import check_conjectures, claim

_NEG = "for x in [-5, -1], "


def plain(x, y):
    if x < 0:
        raise ValueError("n")
    return x


@pytest.mark.parametrize("argument", ["1 % 0", "1 % (2 - 2)", "1.5 % 0", "x % 0"])
@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_remainder_by_zero_in_the_call_gets_a_row(argument, route):
    with pytest.raises(ZeroDivisionError):
        plain(-2.0, eval(argument, {"x": -2.0}))
    (row,) = check_conjectures(
        plain, [claim(_NEG + f"raises(f(x, {argument}), ValueError)", route=route)])
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)
    assert f"{row.sketch} {row.note}".strip(), row


def test_the_row_names_the_argument():
    (row,) = check_conjectures(
        plain, [claim(_NEG + "raises(f(x, 1 % 0), ValueError)", route="derive")])
    assert "1 % 0" in f"{row.sketch} {row.note}", (row.verdict, row.sketch, row.note)
