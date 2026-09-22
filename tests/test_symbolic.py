# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The derive route (symbolic.py): d(...) (the partial-derivative
primitive that turns ordinary equality/inequality claims into calculus,
PDE, and Ito-lemma coefficient-matching claims), domain-aware bounds,
np.clip, ternary expressions, and branch conditions over affine local
variables."""
import math
import random

import numpy as np
import pytest
import sympy

from mathema.analysis import analyze_source
from mathema.conjecture import claim, check_conjectures
from mathema.grammar import to_latex
from mathema.symbolic import diagnose_fold, lift, lift_dot, lift_fold, lift_sum


def cube(x: float) -> float:
    return x ** 3


def heat_sol(t: float, x: float) -> float:
    return x ** 2 + 2.0 * t


def not_heat_sol(t: float, x: float) -> float:
    return x ** 2 + 3.0 * t


def sq(t: float, x: float, sigma: float) -> float:
    return x ** 2


def test_monotonicity_via_first_derivative():
    results = check_conjectures(cube, [claim("d(f(x), x) >= 0", route="derive")])
    assert results[0].verdict == "proven"


def test_pde_heat_equation_proven():
    results = check_conjectures(
        heat_sol, [claim("d(f(t, x), t) == d(f(t, x), x, x)", route="derive")])
    assert results[0].verdict == "proven"


def test_pde_wrong_solution_falsified():
    results = check_conjectures(
        not_heat_sol, [claim("d(f(t, x), t) == d(f(t, x), x, x)", route="derive")])
    assert results[0].verdict == "falsified"


def gauss_sum(n: float) -> float:
    return n * (n + 1) / 2


def const_pow(x: float, n: float) -> float:
    return x ** n


def test_sum_closed_form_proven():
    results = check_conjectures(
        gauss_sum, [claim("Sum(i)_{i=1}^n == f(n)", route="derive")],
        domain={"n": (1.0, 50.0)})
    assert results[0].verdict == "proven"


def test_sum_four_arg_form_and_subscript_sugar_agree():
    sugar = check_conjectures(
        gauss_sum, [claim("Sum(i)_{i=1}^n == f(n)", route="derive")],
        domain={"n": (1.0, 50.0)})
    plain = check_conjectures(
        gauss_sum, [claim("Sum(i, i, 1, n) == f(n)", route="derive")],
        domain={"n": (1.0, 50.0)})
    assert sugar[0].verdict == plain[0].verdict == "proven"


def test_prod_closed_form_proven():
    results = check_conjectures(
        const_pow, [claim("Prod(x)_{i=1}^n == f(x, n)", route="derive")],
        domain={"x": (0.01, 10.0)})
    assert results[0].verdict == "proven"


def test_lowercase_sum_on_derive_route_hints_at_capitalized_form():
    results = check_conjectures(
        gauss_sum, [claim("sum(i, i, 1, n) == f(n)", route="derive")])
    assert results[0].verdict == "unknown"
    assert "Sum(expr, var, lo, hi)" in results[0].sketch


def test_not_equal_and_approx_equal_relations_on_probe_route():
    # sq(t, x, sigma) = x**2, always >= 0, so it's genuinely never -1,
    # unlike cube(x) = x**3, which *does* equal -1 at x = -1.
    assert check_conjectures(sq, [claim("f(t, x, sigma) != -1", route="probe")])[0].verdict == "holds"
    assert check_conjectures(cube, [claim("f(x) ~= x^3", route="probe")])[0].verdict == "holds"


def test_approx_equal_provable_on_derive_route_like_equality():
    results = check_conjectures(cube, [claim("f(x) ~= x^3", route="derive")])
    assert results[0].verdict == "proven"


def test_not_equal_proven_for_a_provably_nonzero_constant_difference():
    def shifted(x: float) -> float:
        return x + 5.0

    results = check_conjectures(shifted, [claim("f(x) != x", route="derive")])
    assert results[0].verdict == "proven"


def test_not_equal_proven_for_a_provably_positive_difference_over_a_domain():
    # x + 5 is never exactly 0 over [0, 10], provably positive via
    # corner evaluation, not a bare constant this time.
    def shifted(x: float) -> float:
        return x + 5.0

    results = check_conjectures(
        shifted, [claim("for x in [0, 10], f(x) != 0", route="derive")])
    assert results[0].verdict == "proven"


def test_not_equal_falsified_when_the_two_sides_are_identically_equal():
    def shifted(x: float) -> float:
        return x + 5.0

    results = check_conjectures(shifted, [claim("f(x) != x + 5", route="derive")])
    assert results[0].verdict == "falsified"


def test_not_equal_stays_undecided_when_genuinely_mixed_sign():
    # x**3 - x**2 is zero at x=0 and x=1, negative in between, positive
    # outside, neither provably nonzero nor provably identically
    # equal, must stay honestly undecided, never guess.
    results = check_conjectures(cube, [claim("f(x) != x^2", route="derive")])
    # derive honestly can't settle it symbolically, and the shared
    # specials then witness the equality at x = 0 (0 == 0), which
    # falsifies the != claim outright
    assert results[0].verdict == "falsified"


def test_numpy_qualified_calls_lift_same_as_math_qualified():
    pytest.importorskip("numpy")
    import numpy as np

    # a real-world shape (arbital's actual linfoot()); np must be
    # imported in the *enclosing* scope, not inside the target function's
    # own body: lift() only understands a plain return-expression body,
    # so an Import statement inside it looks exactly like an
    # unsupported extra statement, unrelated to what this test checks.
    def linfoot_numpy(mi: float) -> float:
        return float(np.sqrt(1.0 - np.exp(-2.0 * max(0.0, mi))))

    # np.sqrt/np.exp must resolve exactly like math.sqrt/math.exp,
    # symbolic.py used to hardcode ("math", "cmath") separately from
    # analysis.py's own _MATH_MODULES (which already included np/numpy),
    # so a function using only numpy silently reported unliftable.
    # zero mutual information must mean zero correlation: linfoot(0) = 0.
    results = check_conjectures(
        linfoot_numpy, [claim("f(0.0) == 0.0", route="derive")])
    assert results[0].verdict == "proven"


def test_float_cast_wrapping_return_value_does_not_block_lifting():
    pytest.importorskip("numpy")
    import numpy as np

    def linfoot_numpy(mi: float) -> float:
        return float(np.sqrt(1.0 - np.exp(-2.0 * max(0.0, mi))))

    # the whole expression is wrapped in float(...), confirms that
    # cast doesn't make the body unliftable (it used to: float wasn't
    # in _SYMPY_FUNCS at all, an unconditional "unsupported call")
    results = check_conjectures(
        linfoot_numpy, [claim("f(mi) == f(mi)", route="derive")])
    assert results[0].verdict == "proven"


def test_ito_drift_coefficient_matching():
    """V = x^2 under dX = mu dt + sigma dW: Ito's lemma implies drift
    d/dt V + mu d/dx V + 1/2 sigma^2 d^2/dx^2 V = 2*mu*x + sigma^2. This
    is an ordinary equality claim over d(...) terms and free (aux) drift/
    diffusion symbols, no stochastic-process machinery involved."""
    results = check_conjectures(sq, [claim(
        "2*mu*x + sigma**2 == d(f(t,x,sigma), t) + mu*d(f(t,x,sigma), x) "
        "+ 0.5*sigma**2*d(f(t,x,sigma), x, x)", route="derive")])
    assert results[0].verdict == "proven"


def test_mixed_partial():
    def bilinear(x: float, y: float) -> float:
        return x * y

    results = check_conjectures(
        bilinear, [claim("d(f(x, y), x, y) == 1", route="derive")])
    assert results[0].verdict == "proven"


def test_d_rejects_non_parameter_variable():
    results = check_conjectures(
        cube, [claim("d(f(x), q) >= 0", route="derive")])
    assert results[0].verdict == "unknown"


def test_d_is_derive_route_only_probe_skips_cleanly():
    # "d" isn't in the probe route's safe-call whitelist; a probe claim
    # using it must skip cleanly, never crash the adjudication loop.
    results = check_conjectures(cube, [claim("d(f(x), x) >= 0", route="probe")])
    assert results[0].verdict == "skipped"


def test_pde_renders_to_latex():
    tex = to_latex("d(f(t, x), t) == d(f(t, x), x, x)")
    assert r"\partial" in tex


# ---- lim/integrate: L'Hopital's rule, Cauchy-Schwarz, Gram-Schmidt, ------
# ---- probability normalization -------------------------------------------

def sinx(x: float) -> float:
    return math.sin(x)


def dot2d(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * bx + ay * by


def gram_schmidt_2d(v1x: float, v1y: float, v2x: float, v2y: float) -> float:
    dot = v2x * v1x + v2y * v1y
    denom = v1x * v1x + v1y * v1y
    u2x = v2x - (dot / denom) * v1x
    u2y = v2y - (dot / denom) * v1y
    return v1x * u2x + v1y * u2y   # u1 . u2, should be 0 if orthogonal


def gauss_pdf(x: float, mu: float, sigma: float) -> float:
    return (1 / (sigma * math.sqrt(2 * math.pi))) * math.exp(
        -((x - mu) ** 2) / (2 * sigma ** 2))


def test_lhopital_direct_limit():
    results = check_conjectures(sinx, [claim("lim(f(x)/x, x, 0) == 1", route="derive")])
    assert results[0].verdict == "proven"


def test_lhopital_matches_derivative_ratio_limit():
    results = check_conjectures(sinx, [claim(
        "lim(f(x)/x, x, 0) == lim(d(f(x),x)/d(x,x), x, 0)", route="derive")])
    assert results[0].verdict == "proven"


def test_cauchy_schwarz_direct_form_proves_via_squaring():
    # abs()/sqrt() together stall the plain sign analysis, but both
    # sides are provably nonnegative, so the squaring rescue re-decides
    # on the squared difference, Lagrange's identity, the same
    # certificate the hand-squared form below has always used. This
    # was pinned "honestly undecided" (then "holds" via the empirical
    # fallback) before the squaring rung existed; a genuine proof now.
    results = check_conjectures(dot2d, [claim(
        "abs(f(ax,ay,bx,by)) <= sqrt(ax**2+ay**2)*sqrt(bx**2+by**2)",
        route="derive")])
    assert results[0].verdict == "proven"
    assert results[0].meta.get("mathema.derive_route") == "squared_comparison"


def test_cauchy_schwarz_squared_form_proven_via_factor_fallback():
    # Same claim, squared to avoid sqrt/Abs: the difference is
    # (ax*by - ay*bx)**2 by Lagrange's identity, invisible to plain
    # .is_nonnegative until factored, which is exactly what the factor()
    # fallback in try_prove's <=/>= path exists for.
    results = check_conjectures(dot2d, [claim(
        "f(ax,ay,bx,by)**2 <= (ax**2+ay**2)*(bx**2+by**2)", route="derive")])
    assert results[0].verdict == "proven"


def test_gram_schmidt_orthogonality_proven():
    # v1 bounded away from the origin: the division-by-zero-norm region
    # (a real raise at v1 = 0) is excluded, and the orthogonality
    # identity proves. Unbounded, the same claim now honestly falsifies
    # at the zero vector; a raise is not a value.
    results = check_conjectures(
        gram_schmidt_2d, [claim("for v1x in [1, 2], v1y in [1, 2], "
                                "f(v1x,v1y,v2x,v2y) == 0", route="derive")])
    assert results[0].verdict == "proven"


def test_gaussian_pdf_normalizes_to_one():
    # Needs the strictly-positive (not just nonnegative) domain assumption
    # threaded through *before* integrate() runs, or sympy can't resolve
    # the internal branch and returns an unevaluated Piecewise instead of 1.
    results = check_conjectures(gauss_pdf, [claim(
        "for sigma in [1e-6, 1e6], integrate(f(x,mu,sigma), x, -oo, oo) == 1",
        route="derive")])
    assert results[0].verdict == "proven"


def test_integrate_renders_to_latex():
    tex = to_latex("integrate(f(x), x, 0, 1) == 1")
    assert r"\int" in tex


# ---- ε/eps/epsilon resolves to the claim's own tolerance -----------------

def nearly_zero(x: float) -> float:
    return x - x + 1e-10   # always ~1e-10, regardless of x


def test_epsilon_derive_route_proven_within_tolerance():
    results = check_conjectures(
        nearly_zero, [claim("abs(f(x)) <= ε", route="derive", tolerance=1e-6)])
    assert results[0].verdict == "proven"


def test_epsilon_derive_route_disproven_outside_tolerance():
    results = check_conjectures(
        nearly_zero, [claim("abs(f(x)) <= epsilon", route="derive", tolerance=1e-12)])
    assert results[0].verdict == "falsified"


def test_epsilon_probe_route_uses_declared_tolerance():
    results = check_conjectures(
        nearly_zero, [claim("abs(f(x)) <= eps", route="probe", tolerance=1e-6)])
    assert results[0].verdict == "holds"
    results = check_conjectures(
        nearly_zero, [claim("abs(f(x)) <= eps", route="probe", tolerance=1e-12)])
    assert results[0].verdict == "falsified"


def test_epsilon_without_declared_tolerance_is_a_free_variable():
    # No tolerance declared; eps must fall back to being an ordinary aux
    # symbol/variable, not silently resolve to nothing or crash.
    results = check_conjectures(
        nearly_zero, [claim("abs(f(x)) <= eps", route="probe")])
    # evaluated (eps sampled as an ordinary variable), never rejected
    assert results[0].verdict not in ("skipped", "skipped:misspecified",
                                      "unknown")


def clamp_high(r: float) -> float:
    return min(1.0, r)


def test_domain_upper_bound_resolves_a_clamp():
    # a declared domain's upper bound is used as a sign assumption too,
    # not just the lower bound, Min(1.0, r) simplifies to bare r once
    # try_prove knows r's whole range is [0, 1].
    results = check_conjectures(
        clamp_high, [claim("for r in [0, 1], f(r) == r", route="derive")])
    assert results[0].verdict == "proven"


def test_domain_upper_bound_no_regression_when_undeclared():
    # with no domain declared, r ranges over all reals, so
    # min(1.0, r) == r genuinely fails whenever r > 1, a real
    # falsification, not merely an inconclusive .equals() result.
    results = check_conjectures(clamp_high, [claim("f(r) == r", route="derive")])
    assert results[0].verdict == "falsified"


def test_domain_upper_bound_resolves_inequality_via_affine_corner_check():
    # ask()/refine() have a real, incomplete-inference gap for a
    # *non-strict* boundary-touching inequality (ask(r >= 1) stays
    # undecided even under assuming(r <= 1)), exact affine-corner
    # evaluation sidesteps that gap rather than depending on sympy to
    # close it. r's whole domain sits below the clamp's cap, so Min
    # collapses to bare r first, then -r's sign over [-5, 0] is decided
    # by evaluating both corners.
    results = check_conjectures(
        clamp_high, [claim("for r in [-5, 0], f(r) <= 0", route="derive")])
    assert results[0].verdict == "proven"


def np_clip_fn(x: float) -> float:
    return float(np.clip(x, 0.0, 1.0))


def test_np_clip_maps_to_nested_min_max():
    # np.clip(x, lo, hi) == min(max(x, lo), hi), both bounds together,
    # unlike clamp_high's single-sided min() above.
    results = check_conjectures(
        np_clip_fn, [claim("for x in [0, 1], f(x) == x", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        np_clip_fn, [claim("for x in [2, 5], f(x) == 1.0", route="derive")])
    assert results[0].verdict == "proven"


def test_np_clip_resolves_an_equality_claim_via_the_lower_bound_too():
    # domain fully below the clip's floor, so the resolved diff lands on
    # a literal sympy.Float(0.0); sympy.Float's `==` is precision-aware,
    # not value-aware (Float(0.0) == 0 is False in sympy), so the
    # domain-resolved diff's zero-check must use diff.is_zero, not
    # `diff == 0`, or a true equality claim like this one would falsify
    # instead of proving.
    results = check_conjectures(
        np_clip_fn, [claim("for x in [-5, -2], f(x) == 0.0", route="derive")])
    assert results[0].verdict == "proven"


def test_np_clip_falsifies_a_genuinely_wrong_claim():
    # the equality-check fix must not turn every == claim into "proven"
    # regardless of correctness, a real counterexample still falsifies.
    results = check_conjectures(
        np_clip_fn, [claim("for x in [-5, -2], f(x) == 1.0", route="derive")])
    assert results[0].verdict == "falsified"


def np_minimum_fn(x: float) -> float:
    return float(np.minimum(1.0, x))


def np_maximum_fn(x: float) -> float:
    return float(np.maximum(0.0, x))


def test_np_minimum_maps_to_sympy_min():
    results = check_conjectures(
        np_minimum_fn, [claim("for x in [0, 1], f(x) == x", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        np_minimum_fn, [claim("for x in [2, 5], f(x) == 1.0", route="derive")])
    assert results[0].verdict == "proven"


def test_np_maximum_maps_to_sympy_max():
    results = check_conjectures(
        np_maximum_fn, [claim("for x in [-5, -1], f(x) == 0.0", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        np_maximum_fn, [claim("for x in [0, 5], f(x) == x", route="derive")])
    assert results[0].verdict == "proven"


def _scale(x: float) -> float:
    return 2.0 * x


def _offset(y: float, c: float) -> float:
    return y + c


def uses_helper(x: float) -> float:
    return _offset(_scale(x), 1.0)


def chain_a(x: float) -> float:
    return chain_b(x) + 1.0


def chain_b(x: float) -> float:
    return chain_c(x) + 1.0


def chain_c(x: float) -> float:
    return chain_d(x) + 1.0


def chain_d(x: float) -> float:
    return x + 1.0


def mutual_a(x: float) -> float:
    return mutual_b(x)


def mutual_b(x: float) -> float:
    return mutual_a(x)


def calls_method(obj, x: float) -> float:
    return obj.transform(x)


def test_callee_call_inlines_through_a_helper_chain():
    # _offset(_scale(x), 1.0), two levels of callee inlining, neither
    # helper a math/numpy function, both plain local functions.
    results = check_conjectures(
        uses_helper, [claim("f(x) == 2*x + 1", route="derive")])
    assert results[0].verdict == "proven"


def test_callee_chain_inlines_up_to_the_default_depth_of_three():
    # chain_a -> chain_b -> chain_c -> chain_d, each +1, closes to x + 4
    # only if all three callee hops are inlined.
    results = check_conjectures(
        chain_a, [claim("f(x) == x + 4", route="derive")])
    assert results[0].verdict == "proven"


def test_callee_chain_declines_past_an_overridden_max_depth():
    facts = analyze_source(chain_a)
    assert lift(chain_a, facts, max_callee_depth=3) is not None
    assert lift(chain_a, facts, max_callee_depth=2) is None


def test_mutual_recursion_through_calls_declines_rather_than_looping():
    # mutual_a calls mutual_b calls mutual_a, not a bare self-call
    # (facts.recursion doesn't catch this), so it's the callee-inlining
    # seen-set that must refuse the second hop back to mutual_a rather
    # than looping forever.
    facts = analyze_source(mutual_a)
    assert lift(mutual_a, facts) is None


def test_method_call_is_never_inlined_as_a_callee():
    # obj.transform(x) is an attribute call, not a bare name, callee
    # inlining only ever attempts a plain name(...) call, so this stays
    # unliftable rather than treating "transform" as some resolvable
    # global name.
    facts = analyze_source(calls_method)
    assert lift(calls_method, facts) is None


def guarded(y: float) -> float:
    if y > 0:
        return y
    else:
        return -y


def caller_passthrough(x: float) -> float:
    return guarded(x) + 1.0


def caller_computed(x: float) -> float:
    return guarded(x + 1.0) + 1.0


def leaf_branch(x: float) -> float:
    if x > 0:
        return x
    else:
        return -x


def mid_no_branch(x: float) -> float:
    return leaf_branch(x) + 1.0


def top_no_branch(x: float) -> float:
    return mid_no_branch(x) + 1.0


def test_callee_branch_resolves_via_bare_parameter_passthrough():
    # guarded(x)'s own branch isn't decidable on its own, but the
    # caller's declared domain over x, passed straight through, not
    # computed; settles it exactly the way it would if guarded's body
    # were inlined by hand.
    results = check_conjectures(
        caller_passthrough, [claim("for x in [1, 5], f(x) == x + 1", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        caller_passthrough, [claim("for x in [-5, -1], f(x) == -x + 1", route="derive")])
    assert results[0].verdict == "proven"


def test_callee_branch_declines_for_a_computed_call_site_argument():
    # guarded(x + 1.0), the argument isn't a bare parameter reference,
    # so no domain is derived for it; this must decline rather than
    # guess at the image of [1, 5] under x + 1.0.
    results = check_conjectures(
        caller_computed, [claim("for x in [1, 5], f(x) == x + 2", route="derive")])
    # declines to guess symbolically; the true claim then holds
    # empirically via the probe fallback
    assert results[0].verdict == "holds"


def test_callee_branch_conditioning_propagates_through_a_branch_free_callee():
    # top calls mid (no branch of its own) calls leaf_branch (has one).
    # mid's own derived domain, itself passed through from top's;
    # must still be there by the time mid's body reaches the call to
    # leaf_branch, or this fails purely because of the extra hop.
    facts = analyze_source(top_no_branch)
    assert lift(top_no_branch, facts, domain={"x": (1.0, 5.0)}) is not None
    assert lift(top_no_branch, facts, max_callee_depth=1, domain={"x": (1.0, 5.0)}) is None
    assert lift(top_no_branch, facts, max_callee_depth=2, domain={"x": (1.0, 5.0)}) is not None


def pick(flag: bool, x: float, y: float) -> float:
    return x if flag else y


def reassigns_flag(flag: bool, x: float, y: float) -> float:
    flag = not flag
    return x if flag else y


def test_ternary_bare_boolean_name_resolves_via_pinned_domain():
    results = check_conjectures(
        pick, [claim("for flag in {True}, x in [0, 1], y in [0, 1], f(flag, x, y) == x",
                     route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        pick, [claim("for flag in {False}, x in [0, 1], y in [0, 1], f(flag, x, y) == y",
                     route="derive")])
    assert results[0].verdict == "proven"


def test_ternary_bare_boolean_name_stays_unresolved_when_domain_is_ambiguous():
    results = check_conjectures(
        pick, [claim("for flag in {True, False}, x in [0, 1], y in [0, 1], "
                     "f(flag, x, y) == x", route="derive")])
    # the ambiguous domain can't pin the branch symbolically, and the
    # claim is genuinely false at flag=False (f returns y), which
    # sampling then witnesses
    assert results[0].verdict == "falsified"


def test_ternary_bare_boolean_name_ignores_a_stale_domain_after_reassignment():
    # flag is reassigned before the ternary, the *original* flag's
    # declared domain no longer describes its value at that point, so
    # this must decline rather than resolve off a stale assumption and
    # risk proving something false.
    results = check_conjectures(
        reassigns_flag, [claim("for flag in {True}, x in [0, 1], y in [0, 1], "
                               "f(flag, x, y) == x", route="derive")])
    # resolving off the stale domain would prove something false; the
    # honest decline then lets sampling expose that falsity for real
    # (flag reassigned to False, f returns y != x)
    assert results[0].verdict == "falsified"


def clamp_ternary(x: float) -> float:
    return 0.0 if x == 0.0 else 1.0 / x


def test_ternary_lifts_to_a_piecewise_and_proves_the_if_side():
    results = check_conjectures(
        clamp_ternary, [claim("for x in [0, 0], f(x) == 0.0", route="derive")])
    assert results[0].verdict == "proven"


def test_ternary_proves_the_else_side():
    results = check_conjectures(
        clamp_ternary, [claim("for x in [1, 5], f(x) == 1.0 / x", route="derive")])
    assert results[0].verdict == "proven"


def test_ternary_straddling_the_condition_stays_undecided_not_a_guess():
    results = check_conjectures(
        clamp_ternary, [claim("for x in [-5, 5], f(x) >= 0", route="derive")])
    # the straddling condition stays symbolically unresolved, and the
    # claim is false on [-5, 0) anyway (1/x < 0), which sampling shows
    assert results[0].verdict == "falsified"


def test_ternary_with_unsupported_condition_still_refuses_cleanly():
    # a bare boolean-name condition isn't a form _cond_to_sympy handles;
    # must refuse, not misinterpret it.
    def flagged(flag: bool, x: float) -> float:
        return 0.0 if flag else x

    results = check_conjectures(flagged, [claim("f(flag, x) >= 0", route="derive")])
    # refuses to misinterpret the bare-name condition; the unbounded
    # claim is then false at flag=False with negative x
    assert results[0].verdict == "falsified"


def denom_local(x: float, y: float) -> float:
    denom = x + y
    if denom == 0.0:
        return 0.0
    return x / denom


def test_affine_local_branch_resolves_when_domain_pins_the_zero_branch():
    # denom = x + y is a *local*, not a signature parameter, resolved
    # by tracing it back to unmodified parameters x, y and reusing the
    # same corner-evaluation fact _affine_sign_by_corners relies on.
    results = check_conjectures(
        denom_local,
        [claim("for x in [1, 1], y in [-1, -1], f(x, y) == 0.0", route="derive")])
    assert results[0].verdict == "proven"


def test_affine_local_branch_resolves_the_other_side_too():
    results = check_conjectures(
        denom_local,
        [claim("for x in [1, 5], y in [1, 5], f(x, y) == x / (x + y)", route="derive")])
    assert results[0].verdict == "proven"


def test_affine_local_branch_straddling_domain_stays_undecided():
    results = check_conjectures(
        denom_local, [claim("for x in [-5, 5], y in [-5, 5], f(x, y) >= 0", route="derive")])
    # symbolically straddling, and genuinely false (x=1, y=-2 gives
    # x/(x+y) = -1), which the probe fallback witnesses
    assert results[0].verdict == "falsified"


def test_affine_local_branch_with_no_domain_lifts_piecewise_but_stays_honest():
    # the full piecewise lift now gets further than pruning (the branch
    # lifts, the sign question remains genuinely open on x/(x + y)),
    # and the actionable domain hint survives in the sketch
    results = check_conjectures(denom_local, [claim("f(x, y) >= 0", route="derive")])
    assert results[0].verdict == "falsified"
    assert "routes attempted" in results[0].note and "derive: undecided" in results[0].note
    assert "needs a domain specific enough" in results[0].note


def sign_from_diff(a: float, b: float) -> float:
    d = a - b
    if d > 0:
        return 1.0
    if d < 0:
        return -1.0
    return 0.0


def test_affine_local_branch_decides_a_strict_inequality_condition():
    results = check_conjectures(
        sign_from_diff, [claim("for a in [5, 10], b in [1, 2], f(a, b) == 1.0", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        sign_from_diff, [claim("for a in [1, 2], b in [5, 10], f(a, b) == -1.0", route="derive")])
    assert results[0].verdict == "proven"


# --- linear accumulator folds ------------------------------------------------

def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def ema_guarded(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        if v > 0:
            y = alpha * v + (1 - alpha) * y
    return y


def ema_nonlinear(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v * y
    return y


def ema_with_constant(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y + 1.0
    return y


def no_loop(x: list, alpha: float) -> float:
    return x[0] * alpha


def ema_external_init(x: list, alpha: float, y0: float) -> float:
    y = y0
    for v in x:
        y = alpha * v + (1 - alpha) * y
    return y


def ema_partial_seq_init(x: list, alpha: float, y0: float) -> float:
    # neither shape: the initial value mixes seq_param with something else
    y = x[0] + y0
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def mean_of_list(x: list) -> float:
    total = 0.0
    for v in x:
        total += v
    return total / len(x)


def ema_scaled(x: list, alpha: float, scale: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y * scale


def sum_with_unliftable_return(x: list) -> float:
    total = 0.0
    for v in x:
        total += v
    return total + undefined_name  # noqa: F821, deliberately unbound


def test_lift_fold_recognizes_ema_and_extracts_its_coefficients():
    fl = lift_fold(ema, analyze_source(ema))
    assert fl is not None
    assert fl.mode == "from_first_element"
    assert fl.coeff_item == sympy.Symbol("alpha", real=True)
    assert fl.coeff_acc == 1 - sympy.Symbol("alpha", real=True)


def test_lift_fold_recognizes_external_init_variant():
    fl = lift_fold(ema_external_init, analyze_source(ema_external_init))
    assert fl is not None
    assert fl.mode == "external_init"
    assert fl.init_expr == sympy.Symbol("y0", real=True)


@pytest.mark.parametrize("fn", [ema_guarded, ema_nonlinear, ema_with_constant, no_loop,
                                ema_partial_seq_init])
def test_lift_fold_declines_shapes_it_does_not_recognize(fn):
    assert lift_fold(fn, analyze_source(fn)) is None


# --- post-processed accumulator returns (`return acc / len(x)`, etc.) -------

def test_lift_fold_recognizes_division_by_length_return():
    fl = lift_fold(mean_of_list, analyze_source(mean_of_list))
    assert fl is not None
    # acc_expr is the accumulator's own closed form (the plain sum);
    # expr is the whole function's, the sum divided by the length,
    # and the two must actually be different now that a return can
    # transform the accumulator rather than just being it.
    assert fl.acc_expr != fl.expr
    assert fl.return_template == fl.acc_sym / sympy.Symbol("L", integer=True, nonnegative=True)


def test_lift_fold_post_processed_return_closed_form_matches_real_execution():
    fl = lift_fold(mean_of_list, analyze_source(mean_of_list))
    rng = random.Random(13)
    for _ in range(50):
        length = rng.randint(1, 8)
        xs = [round(rng.uniform(-20, 20), 4) for _ in range(length)]
        real = mean_of_list(xs)

        closed = fl.expr.subs(fl.length, length).doit()
        closed = closed.subs({fl.seq[i]: xs[i] for i in range(length)})
        assert math.isclose(float(sympy.N(closed)), real, abs_tol=1e-6)


def test_lift_fold_declines_when_return_expression_itself_is_unliftable():
    # the accumulator update is perfectly fine, only the return
    # expression (an unbound name) is the problem, so this must still
    # decline rather than lift a return that doesn't mean anything.
    assert lift_fold(sum_with_unliftable_return,
                     analyze_source(sum_with_unliftable_return)) is None
    report = diagnose_fold(sum_with_unliftable_return,
                           analyze_source(sum_with_unliftable_return))
    assert report["reason"] == "unbound-name"
    assert "return expression" in report["hint"]


def test_fold_claim_scaled_return_and_alpha_one_collapse_together_proven():
    # combines the existing alpha=1 zero-collapse special case
    # (_fold_eval_at rebuilding the accumulator directly rather than
    # asking sympy to simplify Sum(0**(L-1-k)*...) for symbolic L) with
    # the new return-template substitution (`* scale`) in the same
    # claim; the two now have to compose correctly, not just work in
    # isolation.
    results = check_conjectures(
        ema_scaled, [claim("f(x, 1.0, 2.0) == 2 * x[-1]", route="derive")])
    assert results[0].verdict == "proven"


def test_fold_claim_post_processed_return_zero_factor_collapses_proven():
    results = check_conjectures(
        mean_of_list, [claim("f(x) * 0.0 == 0.0", route="derive")])
    assert results[0].verdict == "proven"


def test_fold_claim_law_can_call_a_math_function():
    # _fold_law_to_sympy imports _SYMPY_FUNCS correctly but was missing
    # _unsupported_call_message from its own ._base import, a
    # NameError the moment that branch's own not-found case is reached
    # elsewhere in the same function; see test_dot_claim_law_can_call_a_
    # math_function's own comment for why this checks the sketch text
    # rather than the verdict.
    results = check_conjectures(
        mean_of_list, [claim("abs(f(x)) >= 0.0", route="derive")])
    haystack = (results[0].sketch or "") + (results[0].note or "")
    assert "NameError" not in haystack
    assert "Abs(" in haystack


# --- dot products (lift_dot, try_prove_dot) ----------------------------

def dot_ab(a: list, b: list) -> float:
    return float(np.dot(a, b))


def dot_unwrapped(a: list, b: list) -> float:
    return np.dot(a, b)


def dot_plus_something(a: list, b: list) -> float:
    return np.dot(a, b) + 1.0


def dot_one_seq_param(a: list, scale: float) -> float:
    return float(np.dot(a, a))


def loop_dot(a: list, b: list) -> float:
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


def test_lift_dot_recognizes_float_wrapped_np_dot():
    fl = lift_dot(dot_ab, analyze_source(dot_ab))
    assert fl is not None
    length = sympy.Symbol("L", integer=True, nonnegative=True)
    k = sympy.Symbol("k", integer=True)
    assert fl.expr == sympy.Sum(fl.ib_a[k] * fl.ib_b[k], (k, 0, length - 1))


def test_lift_dot_recognizes_unwrapped_np_dot():
    assert lift_dot(dot_unwrapped, analyze_source(dot_unwrapped)) is not None


@pytest.mark.parametrize("fn", [dot_plus_something, dot_one_seq_param, loop_dot])
def test_lift_dot_declines_shapes_it_does_not_recognize(fn):
    # dot_plus_something: np.dot combined with something else, not the
    # whole body on its own; dot_one_seq_param: only one real sequence
    # parameter (np.dot(a, a) reuses it twice, not two distinct
    # parameters); loop_dot: the same reduction hand-written as a loop,
    # lift_dot() only ever recognizes the literal np.dot(...) call,
    # by design (see its own docstring); the *system* still recognizes
    # loop_dot's shape overall, just via lift_sum() instead; see
    # test_lift_sum_recognizes_index_based_dot_product below.
    assert lift_dot(fn, analyze_source(fn)) is None


def test_lift_dot_closed_form_matches_real_execution():
    fl = lift_dot(dot_ab, analyze_source(dot_ab))
    rng = random.Random(17)
    for _ in range(50):
        length = rng.randint(0, 8)
        a_vals = [round(rng.uniform(-20, 20), 4) for _ in range(length)]
        b_vals = [round(rng.uniform(-20, 20), 4) for _ in range(length)]
        real = dot_ab(a_vals, b_vals)

        closed = fl.expr.subs(fl.length, length).doit()
        closed = closed.subs({fl.ib_a[i]: a_vals[i] for i in range(length)})
        closed = closed.subs({fl.ib_b[i]: b_vals[i] for i in range(length)})
        assert math.isclose(float(sympy.N(closed)), real, abs_tol=1e-6)


def test_dot_claim_reflexivity_proven():
    results = check_conjectures(
        dot_ab, [claim("f(a, b) == f(a, b)", route="derive")])
    assert results[0].verdict == "proven"


def test_dot_claim_wrong_argument_order_is_skipped_not_guessed():
    # f(b, a) would call the real function with its two sequence
    # parameters genuinely swapped, not attempted (only the exact
    # positional match to the real signature is), so this stays
    # unliftable rather than assuming commutativity silently.
    results = check_conjectures(
        dot_ab, [claim("f(a, b) == f(b, a)", route="derive")])
    # never assumed commutative symbolically; sampling then hits two
    # sequences of different lengths, where the swapped call raises,
    # a real counterexample for the unquantified claim
    assert results[0].verdict == "falsified"


def test_derivability_report_dot_weights_shaped_function_is_liftable():
    from mathema.audit import derivability_report
    report = derivability_report(dot_ab)
    assert report == {"liftable": True}


def test_dot_claim_law_can_call_a_math_function():
    # _dot_law_to_sympy's own math-function branch (name in _SYMPY_FUNCS)
    # referenced _SYMPY_FUNCS/_unsupported_call_message without importing
    # either; a NameError on first use, never exercised by any existing
    # test since none of them call a math function from a dot-route
    # claim's own law text. try_prove()'s own outer except swallows that
    # NameError into an ordinary-looking "undecided" sketch, so the
    # regression test checks the sketch text itself (must show the real
    # built expression, not a NameError), not just the verdict, sympy's
    # own sign-decidability gap on an unassumed Abs is a separate,
    # pre-existing limitation this test isn't meant to close.
    results = check_conjectures(
        dot_ab, [claim("abs(f(a, b)) >= 0.0", route="derive")])
    haystack = (results[0].sketch or "") + (results[0].note or "")
    assert "NameError" not in haystack
    assert "Abs(" in haystack


def test_derivability_report_hand_written_loop_dot_is_liftable_via_lift_sum():
    # loop_dot, the same reduction as dot_ab, hand-written as a loop
    # instead of a literal np.dot(...) call, is liftable overall, just
    # via a different mechanism: lift_dot() (tried first, for the
    # no-loop case) still declines it, but derivability_report() also
    # tries lift_sum() before giving up, which recognizes the
    # `for i in range(len(a)): total += a[i]*b[i]` shape directly.
    from mathema.audit import derivability_report
    assert derivability_report(loop_dot) == {"liftable": True}


def test_derivability_report_non_np_dot_two_sequence_function_names_both_params():
    def two_seq_no_loop(a: list, b: list) -> float:
        return a[0] + b[0]

    from mathema.audit import derivability_report
    report = derivability_report(two_seq_no_loop)
    assert report["blocker"] == "non-scalar-parameters"
    assert report["params"] == ["a", "b"]


# --- general sum accumulation (lift_sum, try_prove_sum) -----------------

def index_dot(a: list, b: list) -> float:
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


def non_affine_sum(xs: list) -> float:
    total = 0.0
    for v in xs:
        total += v * v
    return total


def nested_loop_sum(a: list, b: list) -> float:
    total = 0.0
    for x in a:
        for y in b:
            total += x * y
    return total


def two_pass_variance(xs: list) -> float:
    total = 0.0
    for x in xs:
        total += x
    mean = total / len(xs)
    sq = 0.0
    for x in xs:
        sq += (x - mean) ** 2
    return sq / len(xs)


def enumerate_sum(cashflows: list, r: float) -> float:
    pv = 0.0
    for i, cf in enumerate(cashflows):
        pv += cf / (1 + r) ** i
    return pv


def multiplicative_update(xs: list) -> float:
    total = 1.0
    for v in xs:
        total = total * v
    return total


def extra_loop_body_statement(a: list, b: list) -> float:
    total = 0.0
    n = len(a)
    for i in range(n):
        j = (i + 1) % n
        total += a[i] * b[j]
    return total


def test_lift_sum_recognizes_index_based_dot_product():
    sl = lift_sum(index_dot, analyze_source(index_dot))
    assert sl is not None
    i = sympy.Symbol("i", integer=True)
    length = sympy.Symbol("L_a", integer=True, nonnegative=True)
    assert sl.expr == sympy.Sum(sl.seqs["a"][i] * sl.seqs["b"][i], (i, 0, length - 1))


def test_lift_sum_recognizes_non_affine_purely_additive_update():
    # v*v is nonlinear in the loop item; refused by lift_fold() (needs
    # affine in item AND acc), recognized directly here since the
    # accumulator's own coefficient is still exactly 1 (pure addition),
    # so no telescoping is needed at all, just a plain Sum.
    sl = lift_sum(non_affine_sum, analyze_source(non_affine_sum))
    assert sl is not None


def test_lift_sum_recognizes_nested_loops():
    sl = lift_sum(nested_loop_sum, analyze_source(nested_loop_sum))
    assert sl is not None
    assert sl.expr.func is sympy.Sum
    # sympy flattens a Sum-of-Sum built one nesting level at a time into
    # a single Sum with two limit tuples, one per original loop level;
    # confirmed live, not assumed.
    assert len(sl.expr.limits) == 2


def test_lift_sum_recognizes_two_pass_shape_with_intermediate_scalar():
    # a genuine two-pass algorithm: a scalar (`mean`) computed between
    # the two accumulator loops, then used by the second pass, not a
    # rigid [init, loop, init, loop, return] alternation.
    sl = lift_sum(two_pass_variance, analyze_source(two_pass_variance))
    assert sl is not None
    assert set(sl.pieces) == {"total", "sq"}


def test_lift_sum_recognizes_enumerate_iteration():
    sl = lift_sum(enumerate_sum, analyze_source(enumerate_sum))
    assert sl is not None


@pytest.mark.parametrize("fn", [multiplicative_update, extra_loop_body_statement])
def test_lift_sum_declines_shapes_it_does_not_recognize(fn):
    # multiplicative_update: coeff_acc isn't identically 1 (total*v),
    # not purely additive; extra_loop_body_statement: the loop body has
    # more than one statement (a local index computed before the
    # update), both real, disclosed boundaries, not bugs.
    assert lift_sum(fn, analyze_source(fn)) is None


def test_lift_sum_index_dot_closed_form_matches_real_execution():
    sl = lift_sum(index_dot, analyze_source(index_dot))
    rng = random.Random(23)
    for _ in range(50):
        length = rng.randint(0, 8)
        a_vals = [round(rng.uniform(-20, 20), 4) for _ in range(length)]
        b_vals = [round(rng.uniform(-20, 20), 4) for _ in range(length)]
        real = index_dot(a_vals, b_vals)

        closed = sl.expr.subs(sl.lengths["a"], length).doit()
        closed = closed.subs({sl.seqs["a"][i]: a_vals[i] for i in range(length)})
        closed = closed.subs({sl.seqs["b"][i]: b_vals[i] for i in range(length)})
        assert math.isclose(float(sympy.N(closed)), real, abs_tol=1e-6)


def test_lift_sum_two_pass_variance_closed_form_matches_real_execution():
    sl = lift_sum(two_pass_variance, analyze_source(two_pass_variance))
    rng = random.Random(29)
    for _ in range(30):
        length = rng.randint(1, 8)
        xs = [round(rng.uniform(-20, 20), 4) for _ in range(length)]
        real = two_pass_variance(xs)

        closed = sl.expr.subs(sl.lengths["xs"], length).doit()
        closed = closed.subs({sl.seqs["xs"][i]: xs[i] for i in range(length)})
        assert math.isclose(float(sympy.N(closed)), real, abs_tol=1e-6)


def test_sum_claim_index_dot_reflexivity_proven():
    results = check_conjectures(
        index_dot, [claim("f(a, b) == f(a, b)", route="derive")])
    assert results[0].verdict == "proven"


def test_sum_claim_nested_loop_reflexivity_proven():
    results = check_conjectures(
        nested_loop_sum, [claim("f(a, b) == f(a, b)", route="derive")])
    assert results[0].verdict == "proven"


def test_sum_claim_two_pass_variance_reflexivity_proven():
    # exercises _safe_simplify's real sympy-StopIteration workaround,
    # the second pass's own Sum contains the first pass's Sum inside its
    # summand (via `mean`), which plain sympy.simplify() can't handle
    # without raising.
    results = check_conjectures(
        two_pass_variance, [claim("f(xs) == f(xs)", route="derive")])
    assert results[0].verdict == "proven"


def test_sum_claim_enumerate_reflexivity_proven():
    results = check_conjectures(
        enumerate_sum, [claim("f(cashflows, r) == f(cashflows, r)", route="derive")])
    assert results[0].verdict == "proven"


def test_try_prove_dispatches_to_sum_only_after_fold_declines():
    # a function lift_fold() *does* recognize must still go through
    # try_prove_fold(), never try_prove_sum(), confirmed indirectly:
    # ema's own existing alpha=1 collapse test elsewhere in this file
    # already proves via the fold route; here, a non-affine update
    # (which lift_fold() always declines) confirms the sum route picks
    # up exactly where fold leaves off, not before.
    facts = analyze_source(non_affine_sum)
    assert lift_fold(non_affine_sum, facts) is None
    assert lift_sum(non_affine_sum, facts) is not None
    results = check_conjectures(
        non_affine_sum, [claim("f(xs) == f(xs)", route="derive")])
    assert results[0].verdict == "proven"


def test_lift_fold_closed_form_matches_real_execution():
    fl = lift_fold(ema, analyze_source(ema))
    rng = random.Random(7)
    for _ in range(50):
        length = rng.randint(1, 8)
        xs = [round(rng.uniform(-20, 20), 4) for _ in range(length)]
        alpha_val = round(rng.uniform(-3, 3), 4)
        real = ema(xs, alpha_val)

        closed = fl.expr.subs(fl.length, length).doit()
        closed = closed.subs(fl.other_params["alpha"], alpha_val)
        closed = closed.subs({fl.seq[i]: xs[i] for i in range(length)})
        assert math.isclose(float(sympy.N(closed)), real, abs_tol=1e-6)


def test_lift_fold_external_init_closed_form_matches_real_execution():
    fl = lift_fold(ema_external_init, analyze_source(ema_external_init))
    rng = random.Random(11)
    for _ in range(50):
        length = rng.randint(0, 8)
        xs = [round(rng.uniform(-20, 20), 4) for _ in range(length)]
        alpha_val = round(rng.uniform(-3, 3), 4)
        y0_val = round(rng.uniform(-20, 20), 4)
        real = ema_external_init(xs, alpha_val, y0_val)

        closed = fl.expr.subs(fl.length, length).doit()
        closed = closed.subs(fl.other_params["alpha"], alpha_val)
        closed = closed.subs(fl.other_params["y0"], y0_val)
        closed = closed.subs({fl.seq[i]: xs[i] for i in range(length)})
        assert math.isclose(float(sympy.N(closed)), real, abs_tol=1e-6)


def test_lift_fold_alpha_one_collapses_to_last_element():
    fl = lift_fold(ema, analyze_source(ema))
    for length in (1, 2, 5):
        xs = [float(i) for i in range(length)]
        closed = fl.expr.subs(fl.length, length).doit()
        closed = closed.subs(fl.other_params["alpha"], 1)
        closed = closed.subs({fl.seq[i]: xs[i] for i in range(length)})
        assert math.isclose(float(sympy.N(closed)), xs[-1], abs_tol=1e-9)


def test_lift_fold_external_init_empty_sequence_returns_initial_value():
    fl = lift_fold(ema_external_init, analyze_source(ema_external_init))
    closed = fl.expr.subs(fl.length, 0).doit()
    closed = closed.subs(fl.other_params["alpha"], 0.3).subs(fl.other_params["y0"], 42.0)
    assert math.isclose(float(sympy.N(closed)), 42.0, abs_tol=1e-9)
    assert ema_external_init([], 0.3, 42.0) == 42.0


# --- proving claims against a fold lift (try_prove_fold, via check_conjectures) ---

def test_fold_claim_alpha_one_collapses_to_last_element_proven():
    results = check_conjectures(ema, [claim("f(x, 1.0) == x[-1]", route="derive")])
    assert results[0].verdict == "proven"


def test_fold_claim_symbolic_alpha_is_falsified_never_falsely_proven():
    # an unbound alpha quantifies over the whole line, where the claim
    # is genuinely false (at alpha far from 1 the average is nowhere
    # near the last element), falsified with a corroborated
    # counterexample, and above all never proven. Before the disproof
    # sampler snapped integer symbols to the lattice this sat at
    # unknown: the length symbol drew non-integer values the fold
    # expression couldn't evaluate at.
    results = check_conjectures(ema, [claim("f(x, alpha) == x[-1]", route="derive")])
    assert results[0].verdict == "falsified"


def test_fold_claim_wrong_argument_count_is_skipped_not_an_error():
    results = check_conjectures(ema, [claim("f(x) == x[-1]", route="derive")])
    assert results[0].verdict == "unknown"


def test_fold_claim_non_bare_first_argument_is_skipped():
    # the fold lift declines the sliced argument; probing then
    # evaluates the slice for real, and with alpha = 1.0 the average
    # collapses to the last element, so the claim holds empirically
    results = check_conjectures(ema, [claim("f(x[1:], 1.0) == x[-1]", route="derive")])
    assert results[0].verdict == "holds"


def test_fold_claim_len_resolves_against_symbolic_length():
    # a claim that never touches the sequence parameter's own values,
    # only its length, still routes through the fold lift correctly.
    def count_like(x: list, alpha: float) -> float:
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y

    results = check_conjectures(
        count_like, [claim("len(x) == len(x)", route="derive")])
    assert results[0].verdict == "proven"


def ema_first_element_init_wrong_iteration(x: list, alpha: float) -> float:
    y = x[0]
    for v in x:   # should be x[1:]; double-counts x[0]
        y = alpha * v + (1 - alpha) * y
    return y


def ema_external_init_wrong_iteration(x: list, alpha: float, y0: float) -> float:
    y = y0
    for v in x[1:]:   # should be x, silently skips x[0]
        y = alpha * v + (1 - alpha) * y
    return y


def test_diagnose_fold_flags_first_element_init_with_wrong_iteration_as_actionable():
    fn = ema_first_element_init_wrong_iteration
    assert lift_fold(fn, analyze_source(fn)) is None
    diagnosis = diagnose_fold(fn, analyze_source(fn))
    assert diagnosis["reason"] == "first-element-init-wrong-iteration"
    assert diagnosis["derive_unlock"] == "actionable"
    assert "x[1:]" in diagnosis["hint"]


def test_diagnose_fold_flags_external_init_with_wrong_iteration_as_actionable():
    fn = ema_external_init_wrong_iteration
    assert lift_fold(fn, analyze_source(fn)) is None
    diagnosis = diagnose_fold(fn, analyze_source(fn))
    assert diagnosis["reason"] == "external-init-wrong-iteration"
    assert diagnosis["derive_unlock"] == "actionable"


def test_diagnose_fold_flags_partial_seq_init_as_actionable():
    fn = ema_partial_seq_init
    assert lift_fold(fn, analyze_source(fn)) is None
    diagnosis = diagnose_fold(fn, analyze_source(fn))
    assert diagnosis["reason"] == "partial-seq-init"
    assert diagnosis["derive_unlock"] == "actionable"


def test_diagnose_fold_flags_nonlinear_update_as_mathema_limitation():
    fn = ema_nonlinear
    assert lift_fold(fn, analyze_source(fn)) is None
    diagnosis = diagnose_fold(fn, analyze_source(fn))
    assert diagnosis["reason"] == "non-affine-update"
    assert diagnosis["derive_unlock"] == "limitation"


def test_diagnose_fold_flags_guarded_fold_as_mathema_limitation():
    fn = ema_guarded
    assert lift_fold(fn, analyze_source(fn)) is None
    diagnosis = diagnose_fold(fn, analyze_source(fn))
    assert diagnosis["reason"] == "guarded-fold"
    assert diagnosis["derive_unlock"] == "limitation"


def test_diagnose_fold_returns_none_when_lift_fold_actually_succeeds():
    assert diagnose_fold(ema, analyze_source(ema)) is None


def test_diagnose_fold_returns_none_when_there_is_no_loop():
    assert diagnose_fold(no_loop, analyze_source(no_loop)) is None


def test_fold_claim_on_unrecognized_loop_stays_unliftable():
    # total = total * v, multiplicative, not purely additive in the
    # accumulator (coeff_acc depends on v, never identically 1), so
    # neither lift_fold() (needs affine in item AND acc) nor lift_sum()
    # (needs the update to be exactly `acc + <anything>`) recognize it.
    # A non-affine but *purely additive* update (`total = total + v*v`)
    # is a different case; lift_sum() now handles that one, see
    # test_lift_sum_recognizes_non_affine_purely_additive_update below.
    def looped(xs: list) -> float:
        total = 1.0
        for v in xs:
            total = total * v
        return total

    results = check_conjectures(
        looped, [claim("f(xs) * 2 == f(xs) * 2", route="derive")])
    # the loop shape stays unliftable; the tautology then holds
    # empirically, with the derive diagnosis kept in the note
    assert results[0].verdict == "holds"
    assert "not derivable" in results[0].note


def test_proven_fold_claim_reaches_the_reasoning_chain():
    # a real gap this surfaced: spec.reasoning_chain() had no branch at
    # all for verdict == "proven", a derive-route proof's own sketch
    # never made it into the saved record, silently dropped rather than
    # explaining why the claim is true.
    from mathema.spec import reasoning_chain

    class _Record:
        def __init__(self, facts, probes):
            self.facts, self.probes, self.lifted, self.concepts = facts, probes, None, []

    results = check_conjectures(ema, [claim("f(x, 1.0) == x[-1]", route="derive")])
    assert results[0].verdict == "proven"
    chain = reasoning_chain(_Record(analyze_source(ema), results))
    derivation_steps = [c for c in chain if c["step"] == "derivation"]
    assert len(derivation_steps) == 1
    assert derivation_steps[0]["claim"] == "f(x, 1.0) = x[-1]"
    assert derivation_steps[0]["basis"] == results[0].sketch and results[0].sketch


# --- proof quantifiers and readable sketches --------------------------------

def test_proven_scalar_claim_carries_a_quantifier():
    results = check_conjectures(cube, [claim("d(f(x), x) >= 0", route="derive")])
    assert results[0].verdict == "proven"
    assert results[0].condition == "∀ x ∈ ℝ"


def test_proven_scalar_claim_quantifier_reflects_a_declared_domain():
    def clamp01(x: float) -> float:
        return min(1.0, x)

    results = check_conjectures(
        clamp01, [claim("for x in [0, 1], f(x) == x", route="derive")])
    assert results[0].verdict == "proven"
    assert results[0].condition == "∀ x ∈ [0.0, 1.0] ⊂ ℝ ∪ {∅}"


def test_proven_fold_claim_quantifies_over_the_sequence():
    results = check_conjectures(ema, [claim("f(x, 1.0) == x[-1]", route="derive")])
    assert results[0].verdict == "proven"
    assert results[0].condition == "∀ x ∈ Seq(ℝ)"


def test_proven_fold_claim_merges_a_free_scalar_parameter_without_a_name_collision():
    # the sequence parameter happens to be named 'x', which the letter
    # pool would otherwise also assign to a remapped scalar, a real
    # bug this test locks in the fix for.
    results = check_conjectures(
        ema, [claim("f(x, alpha) == f(x, alpha)", route="derive")])
    assert results[0].verdict == "proven"
    assert results[0].condition is not None
    assert "x ∈ Seq(ℝ)" in results[0].condition
    # alpha was remapped to some other letter, and that letter is not x
    assert "=alpha" in results[0].condition
    remapped = results[0].condition.split("=alpha")[0][-1]
    assert remapped != "x"


def test_quantifier_groups_shared_domains_and_remaps_long_names():
    def sum_three(some_var: float, some_other_var: float, other_var: float) -> float:
        return some_var + some_other_var + other_var

    results = check_conjectures(sum_three, [claim(
        "for other_var in [0, 1], f(some_var, some_other_var, other_var) == "
        "some_var + some_other_var + other_var", route="derive")])
    assert results[0].verdict == "proven"
    assert results[0].condition == \
        "where x=some_var, y=some_other_var, z=other_var: ∀ x, y ∈ ℝ, z ∈ [0.0, 1.0] ⊂ ℝ ∪ {∅}"


def test_disproven_and_undecided_claims_have_no_quantifier():
    results = check_conjectures(cube, [claim("d(f(x), x) <= 0", route="derive")])
    assert results[0].verdict != "proven"
    assert results[0].condition is None


def test_humanize_renders_piecewise_as_plain_case_language():
    import sympy
    from mathema.symbolic import _humanize

    x = sympy.Symbol("x", real=True)
    expr = sympy.Piecewise((0, x < 0), (x, True))
    assert _humanize(expr) == "when x < 0: 0; otherwise x"


def test_humanize_renders_eq_and_power_readably():
    import sympy
    from mathema.symbolic import _humanize

    x = sympy.Symbol("x", real=True)
    assert _humanize(sympy.Eq(x, x ** 2)) == "x = x^2"


def test_proof_sketch_uses_humanized_piecewise_not_raw_sympy_repr():
    results = check_conjectures(ema, [claim("f(x, 1.0) == x[-1]", route="derive")])
    assert results[0].verdict == "proven"
    assert "Piecewise" not in results[0].sketch
    assert "when L = 1" in results[0].sketch


# --- finite sets: non-numeric (opaque) values (finite_sets.py) -----------

def cdn_snippet(include_cdn: bool) -> str:
    # the arbital.plot.figure_html-shaped motivating case: a ternary
    # between two string literals, once the bare-boolean-name condition
    # itself is already resolvable (see the ternary tests earlier in
    # this file).
    cdn = ('<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
           if include_cdn else "")
    return cdn


def status_message(ok: bool) -> str:
    return "success" if ok else "failure"


def opt_value(x: float) -> str | None:
    if x > 0:
        return "positive"
    return None


def label(x: float) -> str:
    return "a" if x > 0 else "b"


def mean_label(xs: list) -> str:
    # constructed specifically to exercise opaque-value support through
    # the fold route, no natural real-world example needed one, but
    # the same return-transformation machinery lift_fold() already has
    # (see test_lift_fold_recognizes_division_by_length_return) should
    # compose with an opaque return just as well as a numeric one.
    total = 0.0
    for v in xs:
        total += v
    return "nonneg" if total >= 0 else "neg"


def test_opaque_ternary_string_literal_proves_true_branch():
    results = check_conjectures(
        cdn_snippet, [claim('for include_cdn in {True}, f(include_cdn) == '
                            '"<script src=\\"https://cdn.plot.ly/plotly-2.35.2.min.js\\">'
                            '</script>"', route="derive")])
    assert results[0].verdict == "proven"


def test_opaque_ternary_string_literal_proves_false_branch():
    results = check_conjectures(
        cdn_snippet, [claim('for include_cdn in {False}, f(include_cdn) == ""',
                            route="derive")])
    assert results[0].verdict == "proven"


def test_opaque_same_value_equality_proven():
    results = check_conjectures(
        status_message, [claim("for ok in {True}, f(ok) == 'success'", route="derive")])
    assert results[0].verdict == "proven"


def test_opaque_different_value_equality_falsified():
    # confirms the earlier plan's own stated boundary was too
    # conservative: sympy's existing .equals(0) fallback (already used
    # by _prove_relation for the ordinary numeric case) already
    # distinguishes two different free symbols numerically, so this
    # falsifies outright, no dedicated inequality machinery needed.
    results = check_conjectures(
        status_message, [claim("for ok in {True}, f(ok) == 'failure'", route="derive")])
    assert results[0].verdict == "falsified"


def test_opaque_none_return_proves():
    results = check_conjectures(
        opt_value, [claim("for x in [-5, -1], f(x) == None", route="derive")])
    assert results[0].verdict == "proven"


def test_opaque_none_vs_real_value_falsifies():
    results = check_conjectures(
        opt_value, [claim("for x in [1, 5], f(x) == None", route="derive")])
    assert results[0].verdict == "falsified"


def test_opaque_ordering_declines_even_in_the_degenerate_same_value_case():
    # a real bug found and fixed while building this: f(x) <= 'a' when
    # f(x) really is 'a' used to "prove" via bare reflexivity
    # (diff == 0 trivially satisfies <=), even though ordering was
    # never a meaningful thing to claim about a string at all. Both the
    # degenerate (same-value) and genuine (different-value) cases must
    # decline; proving the degenerate one would be misleading, not
    # just occasionally wrong.
    results = check_conjectures(
        label, [claim("for x in [1, 5], f(x) <= 'a'", route="derive")])
    assert results[0].verdict == "unknown"
    assert "ordering" in results[0].sketch


def test_opaque_ordering_declines_for_genuinely_different_values_too():
    results = check_conjectures(
        label, [claim("for x in [1, 5], f(x) <= 'z'", route="derive")])
    assert results[0].verdict == "unknown"
    assert "ordering" in results[0].sketch


def test_opaque_value_through_fold_route_return_transformation():
    results = check_conjectures(
        mean_label, [claim("f(xs) == f(xs)", route="derive")])
    assert results[0].verdict == "proven"


def test_expr_to_sympy_without_a_registry_still_refuses_non_numeric_constants():
    # every diagnostic-only caller (branch-truth resolution,
    # _derived_locals, ...) passes no registry at all and must stay
    # exactly as conservative as before this module existed, opaque
    # support is strictly additive, never a default-on behavior change.
    import ast

    from mathema.symbolic import NotSymbolic, _expr_to_sympy

    node = ast.parse("'hello'", mode="eval").body
    with pytest.raises(NotSymbolic):
        _expr_to_sympy(node, {})


# --- local symbolic arrays: np.linspace/np.arange -------------------------

def sine_wave(amp: float, freq: float, n: float) -> "np.ndarray":
    t = np.linspace(0.0, 1.0, n)
    return amp * np.sin(2 * np.pi * freq * t)


def ellipse_path(cx: float, cy: float, a: float, b: float, n: float) -> tuple:
    phi = np.linspace(0.0, 2.0 * np.pi, n)
    x = cx + a * np.cos(phi)
    y = cy + b * np.sin(phi)
    return x, y


def ramp(start: float, stop: float, step: float) -> "np.ndarray":
    return np.arange(start, stop, step)


def two_independent_arrays(n: float, m: float) -> "np.ndarray":
    p = np.linspace(0.0, 1.0, n)
    q = np.linspace(0.0, 1.0, m)
    return p + q


def array_sum_reduction(a: float, n: float) -> float:
    p = np.linspace(0.0, a, n)
    return np.sum(p)


def test_linspace_bare_array_return_proves_symbolic_index():
    results = check_conjectures(
        sine_wave, [claim("f(amp, freq, n)[i] == amp*sin(2*pi*freq*i/(n-1))",
                         route="derive")])
    assert results[0].verdict == "proven"


def test_linspace_bare_array_return_proves_literal_index_boundary():
    results = check_conjectures(
        sine_wave, [claim("f(amp, freq, n)[0] == 0", route="derive")])
    assert results[0].verdict == "proven"


def test_linspace_tuple_of_arrays_return_proves_both_elements():
    results = check_conjectures(
        ellipse_path, [claim("f(cx, cy, a, b, n)[0][i] == cx + a*cos(2*pi*i/(n-1))",
                            route="derive")])
    assert results[0].verdict == "proven"
    results = check_conjectures(
        ellipse_path, [claim("f(cx, cy, a, b, n)[1][i] == cy + b*sin(2*pi*i/(n-1))",
                            route="derive")])
    assert results[0].verdict == "proven"


def test_arange_bare_array_return_proves():
    results = check_conjectures(
        ramp, [claim("f(start, stop, step)[i] == start + i*step", route="derive")])
    assert results[0].verdict == "proven"


def test_two_independently_built_arrays_decline_not_crash():
    facts = analyze_source(two_independent_arrays)
    assert lift(two_independent_arrays, facts) is None
    results = check_conjectures(
        two_independent_arrays, [claim("f(n, m)[i] == 0", route="derive")])
    # declines symbolically (no crash); sampling then catches the
    # function raising on its own sampled inputs
    assert results[0].verdict == "falsified"


def test_reduction_over_a_local_array_declines_not_crash():
    facts = analyze_source(array_sum_reduction)
    assert lift(array_sum_reduction, facts) is None
    results = check_conjectures(
        array_sum_reduction, [claim("f(a, n) == a", route="derive")])
    assert results[0].verdict == "falsified"   # raises on sampled inputs


def test_unindexed_array_valued_claim_is_unliftable_not_a_crash():
    results = check_conjectures(
        sine_wave, [claim("f(amp, freq, n) == 0", route="derive")])
    assert results[0].verdict == "falsified"   # raises on sampled inputs
    assert "indexed" in results[0].note


# --- degenerate-domain pinning ---------------------------------------------

def root_product(a: float, b: float, c: float) -> float:
    disc = math.sqrt(b ** 2 - 4 * a * c)
    r1 = (-b + disc) / (2 * a)
    r2 = (-b - disc) / (2 * a)
    return r1 * r2


def test_degenerate_domain_pins_the_literal_value():
    # for a in [1, 1]:, a genuine single point, not a range, must
    # substitute a=1 into the body, not just assume a is nonnegative.
    results = check_conjectures(
        root_product, [claim("for a in [1, 1], b in [-10, 10], c in [-10, -0.1], "
                             "f(a, b, c) == c", route="derive")])
    # c stays negative so the discriminant b^2 - 4ac stays positive:
    # the sqrt's raising region (a real ValueError) is excluded
    assert results[0].verdict == "proven"


def test_nondegenerate_range_still_uses_sign_assumption_only():
    # regression: an ordinary (non-degenerate) range must still behave
    # exactly as before, no accidental pinning to the lower bound.
    results = check_conjectures(
        root_product, [claim("for a in [1, 10], b in [-10, 10], c in [-10, -0.1], "
                             "a*f(a, b, c) == c", route="derive")])
    assert results[0].verdict == "proven"
    results_wrong = check_conjectures(
        root_product, [claim("for a in [1, 10], b in [-10, 10], c in [-10, -0.1], "
                             "f(a, b, c) == c", route="derive")])
    assert results_wrong[0].verdict != "proven"


def test_tight_but_unequal_bounds_are_not_treated_as_degenerate():
    def identity(x: float) -> float:
        return x
    results = check_conjectures(
        identity, [claim("for x in [5, 5.0000001], f(x) >= 5", route="derive")])
    assert results[0].verdict == "proven"


def test_degenerate_domain_pins_through_the_fold_route_too():
    # _domain_assumptions() is shared by try_prove_fold() (fold.other_params)
    #; alpha=1 pinned should telescope EMA down to the last element.
    # Reuses the module's existing `ema` fixture (x: list, alpha: float),
    # defined earlier in this file, a second, differently-parameterized
    # `ema` here would silently shadow it at module scope.
    results = check_conjectures(
        ema, [claim("for alpha in [1, 1], f(x, alpha) == x[-1]", route="derive")])
    assert results[0].verdict == "proven"


def ph_from_concentration(h: float) -> float:
    return -(math.log(h) / math.log(10))


def test_degenerate_pin_stays_exact_through_a_transcendental_call():
    # a real reported bug: pinning h to 1e-7 used to substitute a plain
    # sympy.Float, and sympy.log(Float) evaluates eagerly to another
    # Float (16.1180956509583) rather than staying symbolic, dividing
    # that already-rounded float by the still-symbolic log(10) left a
    # ~1e-15 residue that never cancelled, falsifying an exact identity.
    # _exact_numeric_literal's Rational conversion keeps log(Rational)
    # symbolic (log(10000000)), which does simplify to exactly 7.
    results = check_conjectures(
        ph_from_concentration,
        [claim("for h in [0.0000001, 0.0000001], f(h) == 7", route="derive")])
    assert results[0].verdict == "proven"


def clock_hour(hour: float) -> float:
    return hour % 12


def test_mod_resolves_deterministically_when_domain_fits_inside_the_modulus():
    # a real reported bug: Mod(hour, 12) == hour is true for any real
    # hour in [0, 12) and false past it, but sympy's own .equals() has
    # no domain awareness for Mod at all; it falls back to random
    # sampling, which can find a genuine counterexample past 12 or
    # miss it depending on where it happens to probe, giving a
    # different verdict (falsified vs skipped) run to run for the
    # exact same claim. _resolve_mod collapses Mod(hour, 12) to hour
    # directly once the domain proves it can never wrap, so this must
    # come back proven, identically, every time.
    for _ in range(5):
        results = check_conjectures(
            clock_hour, [claim("for hour in [0, 11], f(hour) == hour", route="derive")])
        assert results[0].verdict == "proven"


def test_mod_does_not_resolve_when_domain_can_exceed_the_modulus():
    # regression: a domain that genuinely straddles the modulus must
    # not be silently pinned; the identity really is false there.
    results = check_conjectures(
        clock_hour, [claim("for hour in [0, 15], f(hour) == hour", route="derive")])
    assert results[0].verdict != "proven"


def test_disproof_is_reproducible_when_it_comes_with_a_witness():
    # a genuine, always-false claim (no free symbols left once x is
    # pinned) must still falsify, the disproof-corroboration check
    # must not turn a real, unconditional disproof into "skipped".
    for _ in range(5):
        results = check_conjectures(
            np_clip_fn, [claim("for x in [-5, -2], f(x) == 1.0", route="derive")])
        assert results[0].verdict == "falsified"


def abs_value_branch(x: float) -> float:
    if x >= 0:
        return x
    return -x


def test_negative_domain_gets_a_sign_assumption_symmetric_to_positive():
    # a real reported gap: _domain_assumptions() only ever derived
    # positive/nonnegative from a lower bound >= 0, never negative/
    # nonpositive from an upper bound <= 0, so a negative-only domain
    # carried no sign assumption at all, and sympy couldn't relate the
    # branch's `-x` to `Abs(x)` even though the fact is exactly as true
    # as it is on the mirror-image positive domain.
    positive = check_conjectures(
        abs_value_branch, [claim("for x in [0.1, 100], f(x) == |x|", route="derive")])
    negative = check_conjectures(
        abs_value_branch, [claim("for x in [-100, -0.1], f(x) == |x|", route="derive")])
    assert positive[0].verdict == "proven"
    assert negative[0].verdict == "proven"


# --- specific branch-pruning failure messages ------------------------------

def implicit_div(r: float) -> float:
    return 1 / (1 + r)


def explicit_guard(a: float, b: float, c: float) -> float:
    if a == 0:
        raise ValueError("a must be nonzero")
    disc = (b ** 2 - 4 * a * c) ** 0.5
    return (-b + disc) / (2 * a)


def voltage_divider(vin: float, r1: float, r2: float) -> float:
    if r1 + r2 <= 0:
        raise ValueError("invalid resistances")
    return vin * r2 / (r1 + r2)


def voltage_divider_named(vin: float, r1: float, r2: float) -> float:
    total_r = r1 + r2
    if total_r <= 0:
        raise ValueError("invalid resistances")
    return vin * r2 / total_r


def test_raises_with_no_explicit_raise_gets_a_specific_message():
    results = check_conjectures(
        implicit_div, [claim("for r in [-1, -1], raises(f(r), ZeroDivisionError)", route="derive")])
    # derive can't prove an implicit arithmetic raise; the pinned point
    # then genuinely divides by zero, so the raises claim holds
    # empirically, with the structural diagnosis kept in the note
    assert results[0].verdict == "holds"
    assert "no explicit raise" in results[0].note


def test_raises_needs_domain_on_the_guards_own_parameter_not_just_a_literal_call_arg():
    # the literal 0 argument alone doesn't settle the guard, branch
    # pruning evaluates the condition against the function's OWN
    # declared parameter domains, before call-site substitution.
    results = check_conjectures(
        explicit_guard, [claim("raises(f(a, b, 0), ValueError)", route="derive")])
    # not settled symbolically; most samples return rather than raise,
    # falsifying the unquantified raises claim for real
    assert results[0].verdict == "falsified"
    assert "needs a domain" in results[0].note
    assert "'a'" not in results[0].note  # names the parameter, not quoted oddly
    results_with_domain = check_conjectures(
        explicit_guard, [claim("for a in [0, 0], raises(f(a, b, c), ValueError)", route="derive")])
    assert results_with_domain[0].verdict == "proven"


def test_inline_expression_branch_condition_resolves_same_as_named_local():
    domain = "for r1 in [-1, -1], r2 in [0, 0], "
    inline = check_conjectures(
        voltage_divider, [claim(domain + "raises(f(vin, r1, r2), ValueError)", route="derive")])
    named = check_conjectures(
        voltage_divider_named, [claim(domain + "raises(f(vin, r1, r2), ValueError)", route="derive")])
    assert inline[0].verdict == "proven"
    assert named[0].verdict == "proven"


def test_inline_expression_branch_condition_declines_cleanly_when_domain_too_wide():
    results = check_conjectures(
        voltage_divider, [claim("for r1 in [-10, 10], r2 in [0.1, 1000], "
                                "raises(f(vin, r1, r2), ValueError)", route="derive")])
    # too wide to settle symbolically, and most of the domain returns
    # normally, so the raises claim is falsified empirically
    assert results[0].verdict == "falsified"
    assert "needs a domain" in results[0].note


# --- bare range(n) loops: no sequence parameter needed ---------------------

def arithmetic_series_sum(a1: float, d: float, n: float) -> float:
    total = 0
    for i in range(n):
        total += a1 + i * d
    return total


def geometric_series_sum(a: float, r: float, n: float) -> float:
    total = 0
    for i in range(n):
        total += a * r ** i
    return total


def compound_balance(P: float, r: float, n: float) -> float:
    balance = P
    for _ in range(n):
        balance = balance * (1 + r)
    return balance


def compound_balance_affine_trip_count(P: float, r: float, n: float) -> float:
    balance = P
    for _ in range(n + 1):
        balance = balance * (1 + r)
    return balance


def compound_balance_non_affine_update(P: float, r: float, n: float) -> float:
    balance = P
    for i in range(n):
        balance = balance * i
    return balance


def test_arithmetic_series_sum_matches_gauss_formula():
    # Gauss's formula: no sequence parameter at all, lift_sum()'s own
    # scalar_index shape, a pure-additive accumulator.
    results = check_conjectures(
        arithmetic_series_sum, [claim("f(a1, d, n) == n*(2*a1 + (n-1)*d)/2", route="derive")])
    assert results[0].verdict == "proven"


def test_arithmetic_series_sum_proves_with_all_literal_arguments():
    # confirms _sum_law_to_sympy's f(...) now genuinely substitutes a
    # scalar literal (a real, pre-existing bug found and fixed
    # alongside this feature; it used to always return the fully
    # symbolic s.expr unchanged, ignoring literal call arguments).
    results = check_conjectures(arithmetic_series_sum, [claim("f(2, 3, 5) == 40", route="derive")])
    assert results[0].verdict == "proven"


def test_geometric_series_sum_proves_at_a_literal_trip_count():
    results = check_conjectures(
        geometric_series_sum, [claim("f(a, r, 3) == a + a*r + a*r**2", route="derive")])
    assert results[0].verdict == "proven"


def test_compound_balance_matches_compound_interest_formula():
    # a genuine fold (coeff_acc = 1+r != 1), no sequence parameter at
    # all, lift_fold()'s own no-sequence shape.
    results = check_conjectures(
        compound_balance, [claim("f(P, r, n) == P*(1+r)**n", route="derive")])
    assert results[0].verdict == "proven"


def test_compound_balance_affine_trip_count_proves():
    # the trip count itself can be any liftable expression, not just a
    # bare name (range(n + 1), not just range(n)).
    results = check_conjectures(
        compound_balance_affine_trip_count,
        [claim("f(P, r, n) == P*(1+r)**(n+1)", route="derive")])
    assert results[0].verdict == "proven"


def test_compound_balance_non_affine_update_declines_not_crashes():
    facts = analyze_source(compound_balance_non_affine_update)
    assert lift_fold(compound_balance_non_affine_update, facts) is None
    assert lift_sum(compound_balance_non_affine_update, facts) is None
    results = check_conjectures(
        compound_balance_non_affine_update, [claim("f(P, r, n) == P", route="derive")])
    assert results[0].verdict == "falsified"   # raises on sampled inputs


# --- d(...)@{...} and integrate(...)|_{...}^{...} evaluation-bar sugar ---

def projectile_range(v0: float, theta: float, g: float) -> float:
    return v0 ** 2 * math.sin(2 * theta) / g


def gaussian_pdf(x: float, mu: float, sigma: float) -> float:
    return (1 / (sigma * math.sqrt(2 * math.pi))) * math.exp(-((x - mu) ** 2) / (2 * sigma ** 2))


def test_derivative_at_a_point_proves_projectile_range_maximized_at_45_degrees():
    results = check_conjectures(
        projectile_range, [claim("for g in [9, 10], "
                                 "d(f(v0,theta,g), theta)@{theta=pi/4} == 0", route="derive")])
    # g bounded away from 0: the division's raising region is excluded
    assert results[0].verdict == "proven"


def test_derivative_at_a_point_with_multiple_substitutions():
    results = check_conjectures(
        projectile_range,
        [claim("for g in [9, 10], d(f(v0,theta,g), theta) "
               "at {theta=0, v0=10, g=9.8} == 200/9.8", route="derive")])
    assert results[0].verdict == "proven"


def test_plain_derivative_claim_without_evaluation_bar_still_works():
    results = check_conjectures(
        projectile_range, [claim("for g in [9, 10], d(f(v0,theta,g), theta) "
                                 "== 2*v0**2*cos(2*theta)/g", route="derive")])
    assert results[0].verdict == "proven"



def geometric_decay(y: float, n: float) -> float:
    return (1 + y) ** (-n)


def test_decimal_literal_is_exact_not_a_binary_float_approximation():
    # a claim-text decimal literal (0.05) must behave as the exact
    # rational it denotes (one twentieth), not sympy.Float's nearest
    # IEEE-754 neighbor of it, raised to a symbolic power (n here),
    # the ~1e-17 relative rounding error a Float carries used to leave
    # a real identity's difference non-zero: a false "falsified", not
    # just an imprecise "undecided".
    results = check_conjectures(
        geometric_decay, [claim("f(0.05,n) == f(1/20,n)", route="derive")])
    assert results[0].verdict == "proven"


def test_integrate_bounds_via_evaluation_bar_proves_gaussian_normalizes():
    results = check_conjectures(
        gaussian_pdf, [claim("for sigma in [0.001, 1000], "
                             "integrate(f(x, mu, sigma), x)|_{-oo}^{oo} == 1", route="derive")])
    assert results[0].verdict == "proven"


# --- derive_status meta tag: undecided vs. unliftable, structured -----------

def test_skipped_derive_claim_tags_unliftable_status_in_meta():
    # the structured why-derive-couldn't tag survives onto the record
    # even though probing then adjudicated the claim
    results = check_conjectures(
        implicit_div, [claim("for r in [-1, -1], raises(f(r), ZeroDivisionError)", route="derive")])
    assert results[0].verdict == "holds"
    assert results[0].meta["mathema.derive_status"] == "unliftable"


def test_skipped_derive_claim_tags_undecided_status_in_meta():
    results = check_conjectures(cube, [claim("f(x) <= f(y)", route="derive")])
    assert results[0].verdict == "falsified"   # x^3 <= y^3 is just false
    assert results[0].meta["mathema.derive_status"] == "undecided"
