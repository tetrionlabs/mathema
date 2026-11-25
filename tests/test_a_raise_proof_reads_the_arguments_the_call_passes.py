# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raises proof stands for the call the claim writes. Python evaluates
the call's arguments before the function runs, so an argument that may
fail (`1/0`, a call) leaves the claim unproven, and a constant written in
the place of a parameter the domain binds is not the domain. A call that
passes each parameter its own variable, by position or by keyword, on a
plain function or a method bound to an instance, is the call derive
reads, and is proven."""
import pytest

from mathema.conjecture import check_conjectures, claim

_NEG = "for x in [-5, -1], "
_Y = _NEG + "y in {1, None}, "


def plain(x, y):
    if x < 0:
        raise ValueError("n")
    return x


def one(x):
    if x < 0:
        raise ValueError("n")
    return x


def reads_second(x, y):
    if x < 0:
        raise ValueError(y + 1)
    return x


class _Holder:
    def method(self, x, y):
        if x < 0:
            raise ValueError("n")
        return x

    def reads_second(self, x, y):
        if x < 0:
            raise ValueError(y + 1)
        return x


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text, route="derive")])
    return row


@pytest.mark.parametrize("call", [
    "f(x, 1/0)", "f(x, 1 // (2 - 2))", "f(x, y=1/0)", "f(x, int('a'))", "f(x, 0 ** -1)",
    "f(x, 2 ** (1 // 0))", "f(x, [1][2])", "f(x, *[1 / 0])", "f(x, **{})",
    "f(x, undefined_name)",
])
def test_an_argument_that_is_not_read_as_unable_to_fail_is_not_proven(call):
    row = _row(plain, _NEG + f"raises({call}, ValueError)")
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


def test_the_argument_that_is_not_read_is_named():
    row = _row(plain, _NEG + "raises(f(x, 1/0), ValueError)")
    assert "`1 / 0` is evaluated before the function runs" in f"{row.sketch} {row.note}", \
        (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("call", ["f(x, 1/2)", "f(x, 2*3 + 1)", "f(x, -1.5)", "f(x, 'a')",
                                  "f(x, y=3 - 1)", "f(x, None)", "f(x, 7 // 2)",
                                  "f(x, 2 ** 3)", "f(x, *[1])"])
def test_an_argument_of_literals_and_defined_arithmetic_is_read(call):
    row = _row(plain, _NEG + f"raises({call}, ValueError)")
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("call", ["f(1 + 1)", "f(2 * 3)", "f('a')", "f(None)", "f(x=1 + 1)"])
def test_a_constant_in_the_place_of_a_bound_parameter_is_not_the_domain(call):
    row = _row(one, _NEG + f"raises({call}, ValueError)")
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn,text", [
    (plain, _Y + "raises(f(x, y=y), ValueError)"),
    (plain, _Y + "raises(f(x=x, y=y), ValueError)"),
    (plain, _Y + "raises(f(y=y, x=x), ValueError)"),
    (_Holder().method, _Y + "raises(f(x, y), ValueError)"),
    (_Holder().method, _Y + "raises(f(x, y=y), ValueError)"),
], ids=["keyword", "both keywords", "keywords out of order", "bound method",
        "bound method, keyword"])
def test_a_call_that_passes_each_parameter_its_own_variable_is_proven(fn, text):
    row = _row(fn, text)
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn,text", [
    (plain, _Y + "raises(f(x=y, y=x), ValueError)"),
    (plain, _Y + "raises(f(y, x), ValueError)"),
    (plain, _Y + "raises(f(y, y=x), ValueError)"),
    (_Holder().reads_second, _Y + "raises(f(x, y), ValueError)"),
    (reads_second, _NEG + "raises(f(x, 'a'), ValueError)"),
    (_Holder().method, _Y + "raises(f(y, x), ValueError)"),
], ids=["keywords swapped", "positions swapped", "each given the other's variable",
        "method reads it", "text where the body adds", "method, positions swapped"])
def test_a_call_that_passes_a_parameter_another_value_is_not_proven(fn, text):
    row = _row(fn, text)
    assert row.verdict != "proven", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("text", [
    _Y + "raises(f(x, y=x), ValueError)",
    _NEG + "raises(f(x, x), ValueError)",
], ids=["keyword given another variable", "position given another variable"])
def test_another_variable_for_a_parameter_nothing_reads_is_proven(text):
    row = _row(plain, text)
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)
