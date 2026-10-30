# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Overflow is the computation's matter: where the float64 run of a body
whose exact value is finite returns an infinity, is_computation_safe(f)
is falsified with that point as its witness, whatever arithmetic
overflowed (a product, a literal past float64's range, a power), and a
value claim's `[float]` companion carries the same failure while its
mathematics line stands."""
import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


def literal(x: float) -> float:
    # 1e309 is 10**309 as written, inf in float64
    return 1e309


def product(x: float) -> float:
    # 2 * 10**308 is finite, inf in float64
    return x * 1e308


def bounded(x: float) -> float:
    return x / 4


def _v(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


def test_a_literal_past_float64_range_is_not_computation_safe():
    p = _v(literal, "for x in [0, 2], is_computation_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "is_overflow_safe[f]" in p.counterexample, p.counterexample
    assert "returned inf" in p.counterexample, p.counterexample


def test_a_product_that_overflows_in_the_domain_is_not_computation_safe():
    p = _v(product, "for x in [0, 2], is_computation_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "x = 2" in p.counterexample, p.counterexample


def test_a_body_that_stays_in_range_is_computation_safe():
    p = _v(bounded, "for x in [0, 2], is_computation_safe(f)")
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_the_float_companion_carries_the_overflow():
    rec = mathema.check(product, claims=["for x in [0, 2], f(x) >= 0"])
    rows = {p.name: p for p in rec.probes}
    assert rows["f_x_ge_0"].verdict == "proven", rows["f_x_ge_0"]
    assert rows["f_x_ge_0[float]"].verdict == "falsified", rows["f_x_ge_0[float]"]


def logged(x: float) -> float:
    import numpy as np
    return float(np.log(x))


def test_a_pole_infinity_is_named_as_a_pole_not_an_overflow():
    # np.log(0) is -inf: the logarithm has a pole at 0, no overflow. Pure
    # Python has no pole infinity (math.log(0) and 1/0 raise), so the
    # case needs numpy
    pytest.importorskip("numpy")
    p = _v(logged, "for x in [0, 2], is_computation_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "at a pole" in p.counterexample, p.counterexample
    assert "not an overflow" in p.counterexample, p.counterexample
