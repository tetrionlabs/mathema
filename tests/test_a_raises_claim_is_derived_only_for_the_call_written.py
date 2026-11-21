# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive reads a `raises(f(...), E)` claim by binding the claim's domain
to the function's parameters, so it decides only a call that passes each
parameter, by its own name and in order. A call with any other argument
(`f(-x)`, `f(1)`, `f(x + 10)`, `f(y, x)`) is decided by running it."""
import pytest

from mathema.conjecture import check_conjectures, claim


def r01(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


def r02(x: float, y: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x + y


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


@pytest.mark.parametrize("fn,text", [
    (r01, "for x in [-5, -1], raises(f(-x), ValueError)"),
    (r01, "for x in [-5, -1], raises(f(1), ValueError)"),
    (r01, "for x in [-5, -1], raises(f(x + 10), ValueError)"),
    (r02, "for x in [-5, -1], y in [0, 1], raises(f(y, x), ValueError)"),
], ids=["negated", "constant", "shifted", "swapped"])
def test_a_raise_at_a_call_with_other_arguments_is_falsified(fn, text):
    assert r01(1.0) == 1.0 and r02(0.5, -2.0) == -1.5
    row = _row(fn, text)
    assert row.verdict == "falsified", (row.verdict, row.route, row.sketch)


@pytest.mark.parametrize("fn,text", [
    (r01, "for x in [-5, -1], raises(f(x), ValueError)"),
    (r02, "for x in [-5, -1], y in [0, 1], raises(f(x, y), ValueError)"),
], ids=["one", "two in order"])
def test_a_raise_at_the_call_of_the_parameters_in_order_is_proven(fn, text):
    row = _row(fn, text)
    assert row.verdict == "proven", (row.verdict, row.route, row.sketch)
