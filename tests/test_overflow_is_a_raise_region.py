# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`math.exp(u)` raises OverflowError once `u` exceeds log of the largest
double (709.782712893384), and a value claim is false wherever the code
raises. So the logistic function's symmetry is not proven over the whole
line, where `exp(-x)` overflows for x below about -709.78, and is proven
on any range that stays inside the representable region."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def grow(x: float) -> float:
    return math.exp(x)


@pytest.mark.parametrize("fn,law", [
    (logistic, "f(-x) == 1 - f(x)"),
    (logistic, "for x in [-1000, 0], f(x) >= 0"),
    (grow, "for x in [0, 1000], f(x) >= 1"),
])
def test_an_overflowing_exp_blocks_the_proof(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)
    (q,) = check_conjectures(fn, [claim(law)])
    assert q.verdict == "falsified", (q.verdict, q.note)
    assert q.counterexample


@pytest.mark.parametrize("fn,law", [
    (logistic, "for x in [-700, 700], f(-x) == 1 - f(x)"),
    (grow, "for x in [0, 709], f(x) >= 1"),
])
def test_inside_the_representable_range_it_is_still_proven(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_the_threshold_is_the_last_representable_exponent():
    t = 709.782712893384
    assert math.exp(t) > 0
    with pytest.raises(OverflowError):
        math.exp(math.nextafter(t, math.inf))


def cubed(x: float) -> float:
    return x ** 3


def cubed_int(n: int) -> int:
    return n ** 3


def test_a_float_power_overflow_is_a_raise_region():
    (p,) = check_conjectures(cubed, [claim("f(-x) == -f(x)", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)
    (q,) = check_conjectures(cubed, [claim("f(-x) == -f(x)")])
    assert q.verdict != "proven", (q.verdict, q.note)
    (w,) = check_conjectures(cubed, [claim("f(x) == x * x * x")])
    assert w.verdict == "falsified" and w.counterexample, (w.verdict, w.note)
    (r,) = check_conjectures(cubed, [claim("for x in [-1e100, 1e100], f(-x) == -f(x)",
                                           route="derive")])
    assert r.verdict == "proven", (r.verdict, r.note)


def test_an_integer_power_never_overflows():
    (p,) = check_conjectures(cubed_int, [claim("for n in [-10**6, 10**6] ⊂ Z, f(-n) == -f(n)",
                                               route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def squared(x: float) -> float:
    return x ** 2


def test_an_operational_infinity_bounds_the_overflow_region():
    # with no operational infinity, infinity is infinity: x**2 raises
    # OverflowError past 1.34e154 and the claim is false there
    (p,) = check_conjectures(squared, [claim("f(x) >= 0", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.note)
    # declared at 1e100, "for all x" stops at 1e100, where x**2 is finite
    cj = claim("f(x) >= 0", route="derive", pseudo_infinity=1e100)
    (q,) = check_conjectures(squared, [cj])
    assert q.verdict == "proven", (q.verdict, q.note)
    # the bound is stated in the record, never applied silently
    assert "1e+100" in q.statement or "1e100" in q.statement, q.statement
    # exp overflows at 709.78, well inside 1e100, so it still falsifies
    (r,) = check_conjectures(grow, [claim("f(x) >= 0", pseudo_infinity=1e100)])
    assert r.verdict == "falsified" and r.counterexample, (r.verdict, r.note)
