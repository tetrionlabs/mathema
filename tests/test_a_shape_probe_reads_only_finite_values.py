# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The monotonicity and curvature probes read the shape of a function
from finite values only. An overflow to infinity, or a nan, says
nothing about which way a function moves or bends, so a trial that
meets one is not a counterexample; and a call refused by the
function's own guard is reported as the refusal it is, never as a
floating-point boundary."""
import math

from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim


def nan_right(x: float) -> float:
    total = 0.0
    for _ in range(2):
        total += x if x <= 0 else math.nan
    return total / 2


def _row(fn, text, name):
    (p,) = check_conjectures(fn, [claim(text, name=name, route="best")])
    return p


def test_a_nan_is_not_a_curvature():
    p = _row(nan_right, "for x in [-10, 10], d(f(x), x, x) == 0", "affine[x]")
    assert p.verdict != "falsified", p.counterexample
    assert "nan" not in str(p.counterexample)


def test_a_nan_is_not_a_direction():
    p = _row(nan_right, "for x in [-10, 10], d(f(x), x) >= 0",
             "monotonic_increasing[x]")
    assert p.verdict != "falsified", p.counterexample


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
