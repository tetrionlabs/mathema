# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""CompiledForm: executable closed forms and the lifted-numeric
fallback. A claim the probe route cannot evaluate (a d() law) whose
symbolic comparison stalls gets numeric evidence on the resolved
intermediate; route probe:lifted_numeric, ceiling holds, the note
naming the reconstruction. to_source prints foreign code under a
provenance travels on the form itself."""
import math

import sympy

from mathema.claims import check_conjectures, claim
from mathema.compiled import compile_form, numeric_check


def test_compile_form_round_trips_evaluation():
    x = sympy.Symbol("x", real=True)
    cf = compile_form(x ** 2 + 1)
    assert cf is not None and cf.names == ("x",)
    assert abs(cf.fn(3.0) - 10.0) < 1e-12


def test_compile_form_declines_unevaluated_calculus():
    # Sum/Product/Limit/Derivative have no numeric evaluator yet; an
    # Integral now compiles onto the quad backend instead of declining
    x = sympy.Symbol("x", real=True)
    n = sympy.Symbol("n", integer=True)
    assert compile_form(sympy.Sum(x, (n, 0, 5))) is None
    quad = compile_form(sympy.Integral(sympy.exp(-x ** 2), (x, 0, 1)))
    assert quad is not None and quad.backend == "quad"
    assert abs(quad.fn() - 0.7468241328) < 1e-6


def test_infinite_integral_bounds_need_an_operational_infinity():
    # quadrature over an infinite range can be silently inaccurate, so
    # an infinite bound compiles only under a declared operational
    # infinity (the |inf| reading), read at that range and stated in
    # the form's validity; without one the form declines
    x = sympy.Symbol("x", real=True)
    gauss = sympy.Integral(sympy.exp(-x ** 2), (x, -sympy.oo, sympy.oo))
    assert compile_form(gauss) is None
    capped = compile_form(gauss, pseudo_infinity=(-100.0, 100.0))
    assert capped is not None and capped.backend == "quad"
    assert "operational infinity [-100, 100]" in capped.validity
    assert abs(capped.fn() - math.sqrt(math.pi)) < 1e-6


def test_numeric_check_agrees_and_disagrees_honestly():
    x = sympy.Symbol("x", real=True)
    lhs = compile_form(2 * x)
    rhs_true = compile_form(x + x)
    rhs_false = compile_form(x + x + sympy.Rational(1, 2))
    v, n, _ = numeric_check(lhs, rhs_true, "==", {"x": (0.0, 10.0)})
    assert v == "holds" and n >= 10
    v, n, cx = numeric_check(lhs, rhs_false, "==", {"x": (0.0, 10.0)})
    assert v == "falsified" and cx


def heat_index_like(t, h):
    return (-8.78 + 1.61 * t + 2.34 * h - 0.146 * t * h
            + 0.012 * t * t * math.exp(h / 80) / (1 + 0.01 * t * h))


def test_false_derivative_claim_falsifies_through_some_route():
    # d(f,h) >= -10 is genuinely false in the box (the -0.146*t term
    # dominates); sympy's sign engine stalls on the expression, so the
    # lifted-numeric fallback supplies the counterexample, but any
    # route agreeing it is false is a pass
    (p,) = check_conjectures(heat_index_like, [claim(
        "for t in [80,110], h in [40,100], d(f(t,h), h) >= -10",
        route="derive")])
    assert p.verdict == "falsified"
    if p.route == "probe:lifted_numeric":
        assert "reconstruction" in p.note
        assert p.counterexample


def test_true_derivative_claim_gathers_lifted_numeric_evidence():
    # d(f,h) <= 3 holds across the box; derive stalls, the probe route
    # cannot read d(), and the fallback supplies holds-strength
    # evidence on the resolved intermediate
    (p,) = check_conjectures(heat_index_like, [claim(
        "for t in [80,110], h in [40,100], d(f(t,h), h) <= 3",
        route="derive")])
    assert p.verdict in ("proven", "holds")
    if p.route == "probe:lifted_numeric":
        assert p.n and p.n >= 10
        assert "reconstruction" in p.note


def test_unclosable_integral_gets_quad_backed_evidence():
    # sympy has no closed form for this integrand, so the intermediate
    # stays an Integral; the quad backend (sympy evalf -> mpmath
    # quadrature, no new dependency) supplies executed evidence. The
    # FALSE bound falsifies with a genuine numerically-integrated
    # witness, which exercises the whole pipeline in one adjudication.
    def carrier(a):
        return a
    (p,) = check_conjectures(carrier, [claim(
        "for a in [0.5, 2], integrate(exp(-x**2 + sin(x)), x, 0, a) >= 10",
        route="derive")])
    assert p.verdict == "falsified"
    assert p.route == "probe:lifted_numeric"
    assert p.counterexample
