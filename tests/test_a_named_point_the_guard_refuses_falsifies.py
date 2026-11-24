# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A point the claim names is judged where the function's own guard
refuses it: an infinite member of a finite set (`{0, inf}`), or an
infinite closed end written in the claim (`[0, oo]`). The guard's raise
there falsifies a value claim, with the point as the witness and the
exception named. An open end (`[0, oo)`) names no point. A `raises`
claim about the same point is read as before."""
import math
from typing import Annotated

import pytest

from mathema.authoring import enforce_structure
from mathema.conjecture import check_conjectures, claim
from mathema.types import Finite


@enforce_structure()
def plus_one_finite(x: Annotated[float, Finite]) -> float:
    return x + 1


def plus_one_guarded(x: float) -> float:
    if not math.isfinite(x):
        raise ValueError("x must be finite")
    return x + 1


def plus_one(x: float) -> float:
    return x + 1


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


@pytest.mark.parametrize("fn", [plus_one_finite, plus_one_guarded],
                         ids=lambda fn: fn.__name__)
@pytest.mark.parametrize("text, point", [
    ("for x in {0, inf}, f(x) == x + 1", "x = inf"),
    ("for x in [0, oo], f(x) == x + 1", "x = inf"),
    ("for x in [-oo, 0], f(x) == x + 1", "x = -inf"),
    ("for x in {-inf, 2}, f(x) == x + 1", "x = -inf"),
])
def test_a_named_point_the_guard_refuses_falsifies_the_value_claim(
        fn, text, point):
    p = _row(fn, text)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)
    assert point in (p.counterexample or ""), p.counterexample
    assert "ValueError" in (p.counterexample or ""), p.counterexample


@pytest.mark.parametrize("fn", [plus_one_finite, plus_one_guarded],
                         ids=lambda fn: fn.__name__)
@pytest.mark.parametrize("text", [
    "for x in {0, 1}, f(x) == x + 1",
    "for x in [0, 5], f(x) == x + 1",
    "for x in [0, oo), f(x) == x + 1",
    "for x in (-oo, 0], f(x) == x + 1",
])
def test_a_domain_that_names_no_refused_point_is_read_as_before(fn, text):
    p = _row(fn, text)
    assert p.verdict in ("proven", "holds"), \
        (p.verdict, p.route, p.counterexample, p.note)


def test_a_function_that_returns_at_the_named_point_is_read_as_before():
    p = _row(plus_one, "for x in {0, inf}, f(x) == x + 1")
    assert p.verdict != "falsified", (p.verdict, p.route, p.counterexample)


@pytest.mark.parametrize("fn", [plus_one_finite, plus_one_guarded],
                         ids=lambda fn: fn.__name__)
def test_a_raises_claim_naming_the_guards_exception_is_not_falsified(fn):
    p = _row(fn, "for x in {inf}, raises(f(x), ValueError)")
    assert p.verdict in ("proven", "holds"), \
        (p.verdict, p.route, p.counterexample, p.note)
