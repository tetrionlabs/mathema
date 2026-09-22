# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""_proof_support.py's power-tower equality retry (_provably_signed/
_atomize_positive_power_bases): a fractional power raised to another
expression sharing its own symbolic exponent, whose base is a compound
expression rather than a plain symbol, sympy's own powdenest/simplify
stalls on exactly this shape. Covers both the sympy-level
mechanism directly and real derive-route claims that were previously
undecided because of it."""
import sympy

from mathema.conjecture import claim, check_conjectures
from mathema.symbolic._proof_support import (_affine_sign_by_corners,
                                             _atomize_positive_power_bases,
                                             _provably_signed)


def test_affine_sign_by_corners_does_not_crash_on_an_unbounded_free_symbol():
    # a real, pre-existing bug found while adding _provably_signed's own
    # Mul-factor decomposition: -I*(a-1), with only `a` bounded/declared;
    # Poly(-I*(a-1), a) reads I as a fixed coefficient (degree 1 in a
    # alone), so the old code proceeded to the corner loop and crashed
    # trying float() on a still-symbolic (I never substituted) result.
    # Must return None (undetermined), not raise.
    i_sym = sympy.Symbol("I", real=True)   # deliberately unbounded/undeclared
    a = sympy.Symbol("a", positive=True, real=True)
    result = _affine_sign_by_corners(-i_sym * (a - 1), {"a": (0.1, 0.9)}, {"a": a})
    assert result is None


# --- the mechanism, directly against sympy expressions ----------------------

def test_provably_signed_resolves_a_plain_positive_symbol():
    A = sympy.Symbol("A", positive=True, real=True)
    assert _provably_signed(A, {}, {}, None) is True


def test_provably_signed_resolves_an_affine_expression_via_corners():
    e = sympy.Symbol("e", positive=True, real=True)
    assert _provably_signed(e - 1, {"e": (1.5, 5)}, {"e": e}, None) is True


def test_provably_signed_resolves_a_product_of_signed_factors():
    # -I*(a-1): I positive, (a-1) negative (a in [0.1, 0.9]), -1 negative;
    # an even count of negative factors, so the product is positive,
    # even though the product itself is degree-2 (not affine) and
    # ask()/is_positive alone don't resolve it
    i_sym = sympy.Symbol("I", positive=True, real=True)
    a = sympy.Symbol("a", positive=True, real=True)
    domain = {"a": (0.1, 0.9)}
    params = {"a": a}
    expr = -i_sym * (a - 1)
    assert _provably_signed(expr, domain, params, None) is True


def test_provably_signed_stays_undetermined_when_it_should():
    x = sympy.Symbol("x", real=True)   # no positivity assumption at all
    assert _provably_signed(x, {}, {}, None) is None


def test_atomize_leaves_expression_unchanged_when_nothing_qualifies():
    x = sympy.Symbol("x", real=True)
    expr = x ** sympy.Symbol("n", real=True)
    assert _atomize_positive_power_bases(expr, {}, {}, None) is expr


def test_atomize_and_powdenest_closes_the_isoelastic_shaped_identity():
    # the exact algebraic shape behind test_monopoly_profit_isoelastic's
    # real FOC: X*(X**e)**((e-1)/e) - X**e, X = A*(e-1), reduces to 0
    A, e, c = sympy.symbols("A e c", positive=True, real=True)
    domain = {"A": (1, 100), "e": (1.5, 5), "c": (0.1, 5)}
    params = {"A": A, "e": e, "c": c}
    base = A * (e - 1)
    diff = c * (base * (base ** e) ** ((e - 1) / e) - base ** e) / base ** e

    assert diff.equals(0) is None   # confirms the gap actually exists first
    atomized = _atomize_positive_power_bases(diff, domain, params, None)
    assert sympy.powdenest(atomized, force=True).equals(0) is True


def test_atomize_never_produces_a_false_proof():
    # the same shape, deliberately wrong by a factor of 2, must not
    # come back equal to 0 after atomization
    A, e, c = sympy.symbols("A e c", positive=True, real=True)
    domain = {"A": (1, 100), "e": (1.5, 5), "c": (0.1, 5)}
    params = {"A": A, "e": e, "c": c}
    base = A * (e - 1)
    wrong = c * (2 * base * (base ** e) ** ((e - 1) / e) - base ** e) / base ** e

    atomized = _atomize_positive_power_bases(wrong, domain, params, None)
    assert sympy.powdenest(atomized, force=True).equals(0) is False


# --- real derive-route claims, previously undecided because of this gap ----

def monopoly_profit_isoelastic(q: float, A: float, e: float, c: float) -> float:
    return A * q ** (1 - 1 / e) - c * q


def test_isoelastic_monopoly_foc_now_proves():
    results = check_conjectures(monopoly_profit_isoelastic, [claim(
        "for A in [1,100], e in [1.5,5], c in [0.1,5], "
        "d(f(q,A,e,c), q)@{q=(A*(1-1/e)/c)**e} == 0", route="derive")])
    assert results[0].verdict == "proven"


def utility_along_budget(x: float, a: float, I: float, px: float, py: float) -> float:  # noqa: E741 (I is income, referenced by this exact name in the claim text below)
    y = (I - px * x) / py
    return x ** a * y ** (1 - a)


_COBB_DOUGLAS_FOC = ("for a in [0.1,0.9], I in [10,1000], px in [0.5,20], "
                     "py in [0.5,20], d(f(x,a,I,px,py), x)@{x=a*I/px} == 0")


def test_cobb_douglas_foc_proves_under_extensive():
    # deliberately NOT asserted under the fast cap: this proof runs in
    # ~0.5s on an idle machine against a 3s cap, so under full-suite
    # load the fast-tier assertion was a genuine flake (observed
    # repeatedly). The capability claim that matters, the power-tower
    # machinery settles this FOC symbolically, is load-tolerant under
    # the extensive tier, and the route honestly says which tier ran.
    results = check_conjectures(utility_along_budget,
                                [claim(_COBB_DOUGLAS_FOC, route="derive")],
                                extensive=True)
    assert results[0].verdict == "proven"
    # the route names the mechanism that actually won: on an idle
    # machine the fast attempt itself closes this (route "derive",
    # even under extensive=True); under load it falls to a ladder
    # rung and reports "derive:extensive". Both are honest.
    assert results[0].route in ("derive", "derive:extensive")


def test_fast_cap_timeout_reports_undecided_with_timeout_meta(monkeypatch):
    # the deterministic version of "the fast tier ran out of clock":
    # the derive route never executes the function itself, so a sleep
    # in the function body can't reach the capped region, instead the
    # decision procedure the cap actually wraps (_decide_relation) is
    # made to outlast the 3s fast cap definitively. The claim must come
    # back unknown with the structured timeout tag, never a
    # false verdict either way.
    import time

    from mathema.symbolic import _proof_support

    real = _proof_support._decide_relation

    def slow(*args, **kwargs):
        time.sleep(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(_proof_support, "_decide_relation", slow)
    results = check_conjectures(utility_along_budget,
                                [claim(_COBB_DOUGLAS_FOC, route="derive")])
    # the lifted-numeric fallback supersedes the timed-out unknown with
    # holds-strength evidence on the resolved intermediate; the
    # structured timeout tag survives on the winner, and the verdict is
    # never falsely proven
    assert results[0].verdict in ("unknown", "holds")
    assert results[0].verdict != "proven"
    assert results[0].meta.get("mathema.timeout") == "fast"
    assert results[0].meta.get("mathema.derive_status") == "undecided"
