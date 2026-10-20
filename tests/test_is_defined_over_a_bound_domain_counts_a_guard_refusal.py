# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_defined(f)` with no binding is read over the working domain: the
function's own guards (a conditional raise, an exit, `@enforce_domain`)
cut it, and the calls they refuse are no trial. A claim that binds the
domain itself states it: `for x in [-1, 1], is_defined(f)` says f has a
value at every point of [-1, 1], so a guard refusing a call inside it
is a call with no value there, and the claim is falsified at that
point. A binding on a parameter no guard reads leaves the guards'
cut in place."""
import math
import sys
from fractions import Fraction

import pytest

from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim


def raises_below_zero(x: float) -> float:
    if x < 0:
        raise ValueError("negative")
    return x


def exits_below_zero(x: float) -> float:
    if x < 0:
        sys.exit(3)
    return x


@enforce_domain(domain={"x": (0.0, 10.0)})
def enforced(x: float) -> float:
    return x


def guard_on_y(x: float, y: float) -> float:
    if y < 0:
        raise ValueError("y negative")
    return x + y


def _row(fn, text, route="best"):
    (p,) = check_conjectures(fn, [claim(text, route=route)])
    return p


@pytest.mark.parametrize("fn", [raises_below_zero, exits_below_zero,
                                enforced], ids=lambda f: f.__name__)
def test_the_unbound_claim_reads_the_working_domain(fn):
    p = _row(fn, "is_defined(f)")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample)


@pytest.mark.parametrize("route", ["best", "derive", "probe"])
@pytest.mark.parametrize("fn", [raises_below_zero, exits_below_zero,
                                enforced], ids=lambda f: f.__name__)
def test_a_guard_refusing_inside_the_bound_domain_falsifies(fn, route):
    p = _row(fn, "for x in [-1, 1], is_defined(f)", route)
    assert p.verdict == "falsified", (route, p.verdict, p.sketch, p.note)
    x = Fraction(p.counterexample.split("x = ", 1)[1].split(":")[0]
                 .split(",")[0].split()[0])
    assert -1 <= x < 0, p.counterexample


def test_the_bound_claim_names_no_working_domain():
    p = _row(raises_below_zero, "for x in [-1, 1], is_defined(f)")
    assert "mathema.working_domain" not in (p.meta or {}), p.meta
    assert "working domain" not in (p.note or ""), p.note


def test_a_bound_domain_inside_what_the_guard_leaves_is_proven():
    p = _row(raises_below_zero, "for x in [0, 1], is_defined(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_a_binding_no_guard_reads_keeps_the_guards_cut():
    p = _row(guard_on_y, "for x in [-1, 1], is_defined(f)")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample)


def log_above_zero(x: float) -> float:
    if x <= 0:
        raise ValueError("nonpositive")
    return math.log(x)


def test_a_bound_row_inside_the_guard_says_nothing_of_a_working_domain():
    p = _row(log_above_zero, "for x in (0, 1], is_defined(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "working domain" not in (p.sketch or "") + (p.note or ""), p.sketch
