# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The residue engine's contour patterns, driven directly: exact values
for the classic shapes, and, just as load-bearing, the declines.
Every side condition that fails to discharge must return None, never a
guessed value: a missed pole or an unverified arc condition is how a
residue computation lies."""
import pytest
import sympy

from mathema.symbolic._residues import (
    ContourPattern, _real_value, contour_patterns, evaluate_integral,
    register_contour_pattern, residue_attempts,
)

x = sympy.Symbol("x", real=True)
theta = sympy.Symbol("theta", real=True)
a = sympy.Symbol("a", real=True, positive=True)
b = sympy.Symbol("b", real=True, positive=True)


def _integral(integrand, var, lo, hi):
    return sympy.Integral(integrand, (var, lo, hi))


def test_semicircle_evaluates_the_quartic_exactly():
    out = evaluate_integral(_integral(1 / (1 + x ** 4), x, -sympy.oo, sympy.oo),
                            {}, {"x": x})
    assert out is not None
    value, name, sketch = out
    assert name == "semicircle"
    assert sympy.simplify(value - sympy.pi / sympy.sqrt(2)) == 0
    assert "upper half-plane" in sketch


def test_semicircle_handles_a_parameterized_higher_order_pole():
    # 1/(x^2+a^2)^2: one double pole at i*a; the residue computation
    # carries the multiplicity, no separate formula needed.
    out = evaluate_integral(
        _integral(1 / (x ** 2 + a ** 2) ** 2, x, -sympy.oo, sympy.oo),
        {"a": (1.0, 5.0)}, {"x": x, "a": a})
    assert out is not None
    value, name, _ = out
    assert name == "semicircle"
    assert sympy.simplify(value - sympy.pi / (2 * a ** 3)) == 0


def test_unit_circle_evaluates_the_cosine_kernel():
    # the identity sympy's own integrate gets wrong (it returns 0):
    # 2*pi/sqrt(a^2-b^2), with the a > b side condition discharged from
    # the declared domains and the inner pole classified through the
    # Vieta complement of its strictly-outside partner.
    out = evaluate_integral(
        _integral(1 / (a + b * sympy.cos(theta)), theta, 0, 2 * sympy.pi),
        {"a": (2.0, 5.0), "b": (0.1, 1.0)}, {"a": a, "b": b})
    assert out is not None
    value, name, sketch = out
    assert name == "unit_circle"
    assert sympy.simplify(value - 2 * sympy.pi / sympy.sqrt(a ** 2 - b ** 2)) == 0
    assert "unit-circle contour" in sketch


def test_pole_on_the_contour_declines():
    # 1/(1 + cos(theta)): the substituted denominator vanishes at
    # z = -1, ON the unit circle; this method must refuse outright.
    out = evaluate_integral(
        _integral(1 / (1 + sympy.cos(theta)), theta, 0, 2 * sympy.pi),
        {}, {})
    assert out is None


def test_unverifiable_pole_side_declines():
    # a and b overlap ([1,3] x [2,4]), so a > b fails on part of the
    # box and the inner/outer classification cannot discharge, the
    # pattern must decline, never average over the ambiguity.
    out = evaluate_integral(
        _integral(1 / (a + b * sympy.cos(theta)), theta, 0, 2 * sympy.pi),
        {"a": (1.0, 3.0), "b": (2.0, 4.0)}, {"a": a, "b": b})
    assert out is None


def test_failed_arc_condition_declines():
    # x^2/(x^2+1): denominator degree exceeds the numerator's by no
    # more than 0, so the closing arc doesn't vanish (the integral
    # diverges), decline.
    out = evaluate_integral(
        _integral(x ** 2 / (x ** 2 + 1), x, -sympy.oo, sympy.oo), {}, {"x": x})
    assert out is None


def test_unenumerable_poles_decline():
    # a transcendental denominator: solveset returns a ConditionSet,
    # and a residue method with an incomplete pole list is unsound.
    out = evaluate_integral(
        _integral(1 / (x ** 2 + sympy.exp(x) + 2), x, -sympy.oo, sympy.oo),
        {}, {"x": x})
    assert out is None


def test_residual_imaginary_part_declines():
    assert _real_value(sympy.pi + sympy.I) is None
    assert _real_value(2 * sympy.pi * sympy.I * (-sympy.I / a)) == 2 * sympy.pi / a


def test_residue_attempts_decides_the_full_claim():
    integral = _integral(1 / (a + b * sympy.cos(theta)), theta, 0, 2 * sympy.pi)
    lhs = 2 * sympy.pi / sympy.sqrt(a ** 2 - b ** 2)
    domain = {"a": (2.0, 5.0), "b": (0.1, 1.0)}
    result = residue_attempts(lhs, integral, "==", domain, None, {"a": a, "b": b})
    assert result is not None and result.status == "proven"
    assert result.meta["mathema.derive_route"] == "residue:unit_circle"

    # and a wrong closed form is disproven on the same exact value
    wrong = 2 * sympy.pi / (a ** 2 - b ** 2)
    result = residue_attempts(wrong, integral, "==", domain, None, {"a": a, "b": b})
    assert result is not None and result.status == "disproven"


def test_registry_rejects_duplicate_names():
    assert {p.name for p in contour_patterns()} == {
        "unit_circle", "jordan", "semicircle", "keyhole", "keyhole_log",
        "half_line", "keyhole_plain"}
    with pytest.raises(ValueError, match="already registered"):
        register_contour_pattern(ContourPattern(
            "semicircle", lambda *args: None, lambda *args: None))


def test_jordan_evaluates_fourier_kernels_exactly():
    # cos(a*x)/(x^2+b^2) -> pi*e^(-a*b)/b, and the degree-headroom-1
    # case x*sin(a*x)/(x^2+1) -> pi*e^(-a) that only Jordan's lemma
    # covers (the plain semicircle needs two degrees).
    domain = {"a": (0.5, 3.0), "b": (1.0, 2.0)}
    params = {"x": x, "a": a, "b": b}
    out = evaluate_integral(
        _integral(sympy.cos(a * x) / (x ** 2 + b ** 2), x, -sympy.oo, sympy.oo),
        domain, params)
    assert out is not None and out[1] == "jordan"
    assert sympy.simplify(out[0] - sympy.pi * sympy.exp(-a * b) / b) == 0

    out = evaluate_integral(
        _integral(x * sympy.sin(a * x) / (x ** 2 + 1), x, -sympy.oo, sympy.oo),
        domain, params)
    assert out is not None and out[1] == "jordan"
    assert sympy.simplify(out[0] - sympy.pi * sympy.exp(-a)) == 0


def test_jordan_needs_a_decided_kernel_sign():
    # a in [-1, 1] straddles zero: which half-plane closes is
    # undecidable, so the pattern must decline.
    a_free = sympy.Symbol("a", real=True)
    out = evaluate_integral(
        _integral(sympy.cos(a_free * x) / (x ** 2 + 1), x, -sympy.oo, sympy.oo),
        {"a": (-1.0, 1.0)}, {"x": x, "a": a_free})
    assert out is None


def test_half_line_halves_an_even_full_line_integral():
    out = evaluate_integral(_integral(1 / (1 + x ** 4), x, 0, sympy.oo),
                            {}, {"x": x})
    assert out is not None
    value, name, sketch = out
    assert name == "half_line"
    assert sympy.simplify(value - sympy.pi / (2 * sympy.sqrt(2))) == 0
    assert "half the full-line" in sketch

    # an integrand that is not even must not be halved; it falls
    # through to the Log-keyhole, which needs no symmetry at all and
    # evaluates it exactly (int_0^oo x/(1+x^4) dx = pi/4).
    out = evaluate_integral(_integral(x / (1 + x ** 4), x, 0, sympy.oo),
                            {}, {"x": x})
    assert out is not None and out[1] == "keyhole_plain"
    assert sympy.simplify(out[0] - sympy.pi / 4) == 0


alpha = sympy.Symbol("alpha", real=True, positive=True)


def test_keyhole_proves_the_gamma_reflection_integral():
    # int_0^oo x^(alpha-1)/(1+x) dx = pi/sin(pi*alpha) for alpha in
    # (0,1): the Beta/Gamma reflection identity, with the branch-cut
    # discontinuity supplying the sine.
    out = evaluate_integral(
        _integral(x ** (alpha - 1) / (1 + x), x, 0, sympy.oo),
        {"alpha": (0.1, 0.9)}, {"x": x, "alpha": alpha})
    assert out is not None
    value, name, sketch = out
    assert name == "keyhole"
    assert sympy.simplify(value - sympy.pi / sympy.sin(sympy.pi * alpha)) == 0
    assert "branch cut" in sketch


def test_keyhole_corrects_the_branch_on_lower_half_poles():
    # x^(-1/2)/(1+x^2): poles at +-i; the lower one's z^b reads 2*pi
    # more argument on the keyhole branch, and without that factor the
    # value comes out wrong.
    out = evaluate_integral(
        _integral(1 / (sympy.sqrt(x) * (1 + x ** 2)), x, 0, sympy.oo),
        {}, {"x": x})
    assert out is not None
    assert sympy.simplify(out[0] - sympy.pi / sympy.sqrt(2)) == 0


def test_keyhole_declines_integer_and_straddling_exponents():
    # b = 2 is an integer (no branch cut, the method is vacuous), and
    # an exponent whose domain straddles an integer can't discharge
    # the non-integrality condition.
    out = evaluate_integral(
        _integral(x ** 2 / (1 + x ** 4), x, 0, sympy.oo), {}, {"x": x})
    assert out is None or out[1] != "keyhole"
    straddler = sympy.Symbol("s", real=True, positive=True)
    out = evaluate_integral(
        _integral(x ** straddler / (1 + x ** 4), x, 0, sympy.oo),
        {"s": (0.5, 1.5)}, {"x": x, "s": straddler})
    assert out is None


def test_log_keyhole_evaluates_weighted_and_plain_integrals():
    out = evaluate_integral(
        _integral(sympy.log(x) / (x ** 2 + a ** 2), x, 0, sympy.oo),
        {"a": (0.5, 3.0)}, {"x": x, "a": a})
    assert out is not None and out[1] == "keyhole_log"
    assert sympy.simplify(out[0] - sympy.pi * sympy.log(a) / (2 * a)) == 0

    # no symmetry at all: 1/((1+x)(2+x)) over [0, oo) = log 2, via the
    # Log discontinuity rather than any even extension
    out = evaluate_integral(
        _integral(1 / ((1 + x) * (2 + x)), x, 0, sympy.oo), {}, {"x": x})
    assert out is not None and out[1] == "keyhole_plain"
    assert sympy.simplify(out[0] - sympy.log(2)) == 0


def test_pole_on_the_positive_axis_declines_every_keyhole():
    # 1/((1-x)*(1+x^2)) has a pole at x = 1, on the branch cut itself.
    out = evaluate_integral(
        _integral(1 / ((1 - x) * (1 + x ** 2)), x, 0, sympy.oo), {}, {"x": x})
    assert out is None


def test_pv_indented_contour_evaluates_simple_real_poles():
    c = sympy.Symbol("c", real=True, positive=True)
    from mathema.symbolic._residues import _evaluate_pv
    out = _evaluate_pv(
        _integral(1 / ((x - c) * (x ** 2 + 1)), x, -sympy.oo, sympy.oo),
        {"c": (0.5, 3.0)}, {"x": x, "c": c})
    assert out is not None
    assert sympy.simplify(out[0] + sympy.pi * c / (c ** 2 + 1)) == 0

    # a double real pole has no principal value at all, decline
    out = _evaluate_pv(
        _integral(1 / ((x - 1) ** 2 * (x ** 2 + 1)), x, -sympy.oo, sympy.oo),
        {}, {"x": x})
    assert out is None
