# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter the claim binds to a real interval, a set of numbers, or
R, Z or N is drawn as a number, whatever marker its annotation carries:
`Annotated[float, Finite]` says the number is finite, not that the
parameter is a matrix. A parameter the claim does not bind is drawn as
before."""
from typing import Annotated

import pytest

from mathema.authoring import enforce_structure
from mathema.conjecture import check_conjectures, claim
from mathema.types import Finite


@enforce_structure()
def plus_one_finite(x: Annotated[float, Finite]) -> float:
    return x + 1


def plus_one(x: float) -> float:
    return x + 1


_STRENGTH = ("falsified", "unknown", "holds", "proven")


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


@pytest.mark.parametrize("text", [
    "for x in [0, 5], f(x) == x + 1",
    "for x in {0, 1, 2.5}, f(x) == x + 1",
    "for x in R, f(x) == x + 1",
    "for x in Z, f(x) == x + 1",
    "for x in N, f(x) == x + 1",
])
def test_a_marked_parameter_bound_to_numbers_is_checked_at_numbers(text):
    p = _row(plus_one_finite, text)
    assert p.verdict in ("proven", "holds"), \
        (p.verdict, p.route, p.counterexample, p.note)
    assert "[[" not in (p.note or "") + (p.sketch or ""), (p.note, p.sketch)


@pytest.mark.parametrize("text", [
    "for x in {0, inf}, f(x) == x + 1",
    "for x in [0, oo], f(x) == x + 1",
])
def test_a_named_value_the_guard_refuses_falsifies_at_that_value(text):
    p = _row(plus_one_finite, text)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)
    assert "x = inf" in (p.counterexample or ""), p.counterexample
    assert "[[" not in (p.counterexample or ""), p.counterexample


def test_a_marked_parameter_bound_to_numbers_is_derived_as_the_unmarked_is():
    marked = _row(plus_one_finite, "for x in [0, 5], f(x) == x + 1")
    unmarked = _row(plus_one, "for x in [0, 5], f(x) == x + 1")
    assert (unmarked.verdict, unmarked.route) == ("proven", "derive"), \
        (unmarked.verdict, unmarked.route, unmarked.note)
    assert (marked.verdict, marked.route) == (unmarked.verdict, unmarked.route), \
        (marked.verdict, marked.route, marked.note)


def test_a_false_claim_over_numbers_is_falsified_at_a_number():
    p = _row(plus_one_finite, "for x in [0, 5], f(x) == x + 2")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)
    assert "[[" not in (p.counterexample or ""), p.counterexample


def test_a_marked_parameter_the_claim_does_not_bind_is_drawn_as_before():
    p = _row(plus_one_finite, "f(x) == x + 1")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)
    assert "[[" in (p.counterexample or ""), p.counterexample
