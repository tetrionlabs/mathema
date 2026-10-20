# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A shape claim (monotonic, affine, convex, concave) is a claim about f
at every point of its domain, so a point where f has no value (a raise,
a nan) falsifies it, with that point as the witness and the domain
remedy, the same as for any value claim. A call the function's own
guard refuses lies outside its working domain and is no trial; a call
refused by the function's own guard in a value claim is reported as the
refusal it is, never as a floating-point boundary."""
import math

import pytest

from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim


def nan_right(x: float) -> float:
    total = 0.0
    for _ in range(2):
        total += x if x <= 0 else math.nan
    return total / 2


def root_sum(x: float) -> float:
    total = 0.0
    for _ in range(2):
        total += math.sqrt(x)
    return total


def capped(x: float) -> float:
    if x > 5:
        raise ValueError("x above 5")
    total = 0.0
    for _ in range(2):
        total += x
    return total


def overflow_literal(x: float) -> float:
    # 1e309 is a finite number past the float range: Python reads inf
    if x > 0:
        return 1e309
    return x


def _row(fn, text, name):
    (p,) = check_conjectures(fn, [claim(text, name=name, route="best")])
    return p


def _witness_x(p) -> float:
    return float(p.counterexample.split("x = ", 1)[1].split()[0]
                 .rstrip(",:"))


def test_a_nan_falsifies_a_curvature_claim():
    p = _row(nan_right, "for x in [-10, 10], d(f(x), x, x) == 0", "affine[x]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "nan" in p.counterexample, p.counterexample
    assert _witness_x(p) > 0, p.counterexample


def test_a_nan_falsifies_a_direction_claim():
    p = _row(nan_right, "for x in [-10, 10], d(f(x), x) >= 0",
             "monotonic_increasing[x]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "nan" in p.counterexample, p.counterexample
    assert _witness_x(p) > 0, p.counterexample


def test_a_shape_claim_on_the_side_with_values_still_holds():
    p = _row(nan_right, "for x in [-10, 0], d(f(x), x) >= 0",
             "monotonic_increasing[x]")
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_a_raise_inside_the_domain_falsifies_a_direction_claim():
    p = _row(root_sum, "for x in [-10, 10], d(f(x), x) >= 0",
             "monotonic_increasing[x]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "raised ValueError" in p.counterexample, p.counterexample
    assert _witness_x(p) < 0, p.counterexample


def test_a_raise_inside_the_domain_falsifies_a_curvature_claim():
    p = _row(root_sum, "for x in [-10, 10], d(f(x), x, x) <= 0", "concave[x]")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "raised ValueError" in p.counterexample, p.counterexample


def test_an_overflow_is_no_counterexample_to_a_direction():
    # 1e309 as written is 10**309, so f never decreases; the float64 run
    # reads it as inf, which says nothing about the mathematics
    p = _row(overflow_literal, "for x in [-10, 10], d(f(x), x) >= 0",
             "monotonic_increasing[x]")
    assert p.verdict == "unknown", (p.verdict, p.counterexample, p.note)
    assert "float64 run overflowed" in (p.note or ""), p.note


@pytest.mark.parametrize("text, name", [
    ("for x in [-10, 10], d(f(x), x, x) == 0", "affine[x]"),
    ("for x in [-10, 10], d(f(x), x, x) >= 0", "convex[x]"),
])
def test_an_overflow_is_no_counterexample_to_a_curvature(text, name):
    p = _row(overflow_literal, text, name)
    assert p.verdict != "proven", (p.verdict, p.sketch)
    assert "inf" not in (p.counterexample or ""), p.counterexample


def test_the_functions_own_guard_cuts_the_working_domain():
    (p,) = check_conjectures(capped, [claim(
        "d(f(x), x) >= 0", name="monotonic_increasing[x]", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


_OPEN = claim("for x in (0, 1], f(x) >= 0").domain["x"]


@enforce_domain(domain={"x": _OPEN})
def open_guard(x: float) -> float:
    return x


def test_a_guard_refusal_is_named_as_the_guard_refusing():
    (p,) = check_conjectures(open_guard, [claim("for x in [0, 1], f(x) == x")])
    assert p.verdict == "falsified"
    assert "DomainError" in p.counterexample
    assert "floating-point boundary" not in p.counterexample, p.counterexample
    assert math.isfinite(1.0)
