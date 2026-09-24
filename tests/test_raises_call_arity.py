# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `raises(...)` claim whose call does not fit the function's
signature is malformed: the TypeError its own call produces says
nothing about the function, so the claim is refused as misspecified
rather than judged on that error."""
import pytest

from mathema.conjecture import check_conjectures, claim


def add(a: float, b: float) -> float:
    return a + b


def scaled(a: float, k: float = 2.0) -> float:
    return a * k


@pytest.mark.parametrize("call", ["f(a)", "f(a, b, a)"])
@pytest.mark.parametrize("route", ["best", "probe", "derive"])
def test_a_raises_call_with_the_wrong_arity_is_misspecified(call, route):
    r = check_conjectures(add, [claim(
        f"for a in [0, 1], b in [0, 1], raises({call}, TypeError)",
        route=route)])[0]
    assert r.verdict == "skipped:misspecified", (r.verdict, r.note)
    assert "2" in r.note and "(a, b)" in r.note, r.note


def test_a_call_that_fits_the_signature_is_still_judged():
    r = check_conjectures(add, [claim(
        "for a in [0, 1], b in [0, 1], raises(f(a, b), TypeError)")])[0]
    assert r.verdict == "falsified"


def test_a_default_parameter_may_be_left_out():
    r = check_conjectures(scaled, [claim(
        "for a in [0, 1], raises(f(a), TypeError)")])[0]
    assert r.verdict == "falsified"
