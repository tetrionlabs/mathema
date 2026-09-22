# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The extensive-ladder proof corpus: real-world-shaped claims the fast
derive path can't prove and the strategy ladder proves. Every test
asserts the contrast; `extensive=False` never proves (it holds
empirically or stays unknown), `extensive=True` proves, so a
regression in either direction (the fast path silently absorbing the
cost, or the ladder losing the win) fails loudly.

Each case runs full adjudication twice, so the whole file is opt-in:

    python -m pytest --extensive tests/test_extensive_proofs.py

The first two cases were found live in a field corpus (2026-09-01)."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim

pytestmark = pytest.mark.extensive_proofs


def _run(fn, law, extensive):
    (p,) = check_conjectures(fn, [claim(law, route="derive")],
                             extensive=extensive)
    return p


def _contrast(fn, law):
    # the fast derive attempt never proves: it either declines to the
    # empirical fallback (holds, for a law probing can evaluate) or
    # stays unknown (a d()/integrate() law probing can't touch). The
    # point here is that EXTENSIVE turns the same claim into a proof.
    fast = _run(fn, law, extensive=False)
    assert fast.verdict in ("holds", "unknown"), (fast.verdict, fast.note)
    r = _run(fn, law, extensive=True)
    assert r.verdict == "proven", (r.verdict, r.note, r.sketch)
    assert r.route == "derive:extensive"
    return r


def antiderivative_of_power(x: float, n: float) -> float:
    """x**(n+1)/(n+1), the antiderivative of x**n for n != -1."""
    return x ** (n + 1) / (n + 1)


def weibull_cdf(x: float, scale: float, shape: float) -> float:
    """1 - exp(-(x/scale)**shape), the Weibull distribution function."""
    return 1.0 - math.exp(-((x / scale) ** shape))


def erf_floor(x: float) -> float:
    return math.erf(x)


def tanh_floor(x: float) -> float:
    return math.tanh(x)


def sin_poly(x: float) -> float:
    return math.sin(x) ** 2 - math.sin(x) + 1.0


def cos_poly(x: float) -> float:
    return math.cos(x) ** 2 + math.cos(x)


def rational_floor(x: float) -> float:
    return (x * x - x + 1.0) / (x * x + 1.0)


def test_substitution_proves_negative_power_antiderivative():
    """Originally a t = 1/x substitution-rung contrast case; the fast
    path caught up (deferred integrals now evaluate under the wider
    integral wall clock), so both tiers must prove."""
    law = "for x in [0.1,100], n in [-5,-2], f(x,n) == integrate(x**n, x)"
    assert _run(antiderivative_of_power, law, extensive=False).verdict == "proven"
    assert _run(antiderivative_of_power, law, extensive=True).verdict == "proven"


def test_interval_refinement_certifies_weibull_cdf_monotonicity():
    """The domain-box interval-refinement rung: the Weibull CDF's
    derivative sign at fully general shape (0.5..5, spanning the
    concave/convex regimes), undecided on the fast path, certified
    cell-wise by the ladder."""
    _contrast(weibull_cdf,
              "for scale in [0.1,50], shape in [0.5,5], x in [0,1000], "
              "d(f(x,scale,shape), x) >= 0")


def test_erf_substitution_uses_the_domain_restricted_range():
    # the base interval pass only knows erf's global range [-1, 1],
    # which cannot see that erf(1) ~ 0.84 >= 0.8; t = erf(x) maps the
    # declared domain to [erf(1), erf(5)] exactly.
    r = _contrast(erf_floor, "for x in [1, 5], f(x) >= 0.8")
    assert "erf" in r.sketch


def test_tanh_floor_proves_on_a_restricted_domain():
    # same shape for tanh (tanh(1) ~ 0.76 >= 0.7); the ladder settles
    # it whether the rewrite gallery's exp form or the t = tanh(x)
    # substitution gets there first.
    _contrast(tanh_floor, "for x in [1, 10], f(x) >= 0.7")


def test_trig_polynomial_sign_certifies_by_refinement():
    # min of t**2 - t + 1 over t = sin(x) in [-1, 1] is 3/4 at
    # t = 1/2, comfortably above 1/2, but the one-box hull straddles
    # from the dependency between sin**2 and sin.
    _contrast(sin_poly, "for x in [-1.5, 1.5], f(x) >= 0.5")
    _contrast(cos_poly, "for x in [0.1, 3], f(x) >= -0.3")


def exp_gap(x: float) -> float:
    return math.exp(x) - x


def sqrt_dominates(x: float) -> float:
    return math.sqrt(x) - x


def log_bound(x: float) -> float:
    return x - math.log(1.0 + x)


def test_refinement_isolates_a_transcendental_minimum():
    # min of exp(x) - x is 1 at x = 0; the 0.5 margin is invisible to a
    # one-box hull over a 100-wide interval but certifies cell-wise.
    _contrast(exp_gap, "for x in [-50, 50], f(x) >= 0.5")


def test_sqrt_dominance_now_proves_on_the_fast_pass_via_squaring():
    # sqrt(x) >= x on [0, 1/4]: formerly the t = sqrt(x) substitution
    # showcase (extensive-only); the fast squaring rescue proves it
    # with no extensive at all, both isolated sides nonnegative, the
    # squared difference x - x^2 decidable outright
    r = _run(sqrt_dominates, "for x in [0, 0.25], f(x) >= 0", extensive=False)
    assert r.verdict == "proven", (r.verdict, r.sketch)
    assert r.meta.get("mathema.derive_route") == "squared_comparison"


def test_sqrt_substitution_rung_still_settles_the_endpoint_bound(monkeypatch):
    # ladder-level coverage for this rung specifically: the
    # optional nlsat rung would win first, so it is masked here
    import mathema.symbolic._smt as smt
    monkeypatch.setattr(smt, "available", lambda: False)
    # the t = sqrt(x) ladder rung keeps its own coverage at the ladder
    # level (end-to-end, the fast squaring rescue wins first): interval
    # refinement can never certify the attained zero at x = 0, but the
    # substitution turns the question into t - t**2 on [0, 1/2]
    import sympy
    from mathema.symbolic._extensive import extensive_ladder
    x = sympy.Symbol("x", nonnegative=True)
    result, attempted = extensive_ladder(
        sympy.sqrt(x) - x, sympy.S.Zero, ">=", {"x": (0.0, 0.25)}, None,
        {"x": x})
    assert result is not None and result.status == "proven", attempted
    assert "sqrt" in (result.sketch or "")


def test_refinement_closes_a_thin_margin_near_one_edge():
    # x - log(1 + x) >= 0 on [0.5, 100]: the margin at the left edge is
    # ~0.095, so only the leftmost cells need splitting, adaptive
    # refinement must spend its budget there, not uniformly.
    _contrast(log_bound, "for x in [0.5, 100], f(x) >= 0")


def test_atan_compactification_decides_an_unbounded_claim(monkeypatch):
    # ladder-level coverage for this rung specifically: the
    # optional nlsat rung would win first, so it is masked here
    import mathema.symbolic._smt as smt
    monkeypatch.setattr(smt, "available", lambda: False)
    # no domain at all: (x**2 - x + 1)/(x**2 + 1) >= 0.2 over the whole
    # line. t = atan(x) maps the line into (-pi/2, pi/2), where the
    # transformed expression collapses to 4/5 - sin(2t)/2 and one
    # interval hull settles it.
    r = _contrast(rational_floor, "f(x) >= 0.2")
    assert "atan" in r.sketch


def trig_integral_value(a: float, b: float) -> float:
    return 2.0 * math.pi / math.sqrt(a * a - b * b)


def wrong_trig_integral_value(a: float, b: float) -> float:
    return 2.0 * math.pi / (a * a - b * b)


_TRIG_INTEGRAL_LAW = ("for a in [2, 5], b in [0.1, 1], "
                      "f(a, b) == integrate(1/(a + b*cos(theta)), theta, 0, 2*pi)")


def test_unit_circle_residues_prove_what_sympy_integrates_wrongly():
    # sympy's own integrate returns 0 for this integral (a
    # discontinuous antiderivative read across the range). The fast
    # path never proves: its disproof is vetoed by numeric quadrature
    # of the original, and the lifted-numeric fallback then samples the
    # unevaluated Integral by quadrature; holds, ceiling respected,
    # or the whole attempt stays unknown under the wall clock. The
    # ladder's residue rung then proves the true identity by the
    # unit-circle contour, with the derivation in the sketch.
    fast = _run(trig_integral_value, _TRIG_INTEGRAL_LAW, extensive=False)
    assert fast.verdict in ("holds", "unknown"), (fast.verdict, fast.note)
    if fast.verdict == "holds":
        assert fast.route == "probe:lifted_numeric"
    else:
        assert ("disagrees with numeric quadrature" in fast.sketch
                or "exceeded its wall clock" in fast.sketch)
    r = _run(trig_integral_value, _TRIG_INTEGRAL_LAW, extensive=True)
    assert r.verdict == "proven", (r.verdict, r.sketch)
    assert r.route == "derive:extensive"
    assert "unit-circle contour" in r.sketch


def test_unit_circle_residues_falsify_a_wrong_closed_form():
    # the same integral against a wrong closed form (missing the
    # square root): the residue value is exact, so this is a genuine
    # falsification, not a decline.
    r = _run(wrong_trig_integral_value, _TRIG_INTEGRAL_LAW, extensive=True)
    assert r.verdict == "falsified", (r.verdict, r.sketch)


def fourier_two_factor_value(a: float) -> float:
    return math.pi * math.exp(-a) / 3.0 - math.pi * math.exp(-2.0 * a) / 6.0


def test_jordan_residues_prove_a_two_factor_fourier_integral():
    # sympy's integrate returns this one unevaluated, so the fast path
    # stays unknown; Jordan's lemma closes it from the residues at i
    # and 2i (partial fractions confirm: pi*e^-a/3 - pi*e^-2a/6).
    r = _contrast(fourier_two_factor_value,
                  "for a in [0.5, 3], "
                  "f(a) == integrate(cos(a*x)/((x^2 + 1)*(x^2 + 4)), x, -oo, oo)")
    assert "Jordan" in r.sketch


def pv_value(c: float) -> float:
    return -math.pi * c / (c * c + 1.0)


def test_pv_claim_proves_by_the_indented_contour():
    # the PV(...) form: sympy's own principal_value machinery misfires
    # on the parameterized case (its disproof is vetoed as
    # unconfirmable), and the indented half-residue contour proves the
    # true value.
    law = ("for c in [0.5, 3], "
           "f(c) == P.V.(integrate(1/((x - c)*(x^2 + 1)), x, -oo, oo))")
    r = _contrast(pv_value, law)
    assert "indented contour" in r.sketch


def tangent(theta: float) -> float:
    return math.sin(theta) / math.cos(theta)


def test_interval_sign_survives_a_trig_pole_neighbor():
    # field bug (2026-09-03): theta = 1.5707963267948966 sits BELOW
    # pi/2 by ~2e-17, so tan is +5.1e16 and the claim is TRUE, but
    # sympy's boolean relationals evaluate at too little precision and
    # confidently report the wrong sign, which used to FALSIFY this.
    # The verified-sign discipline (two working precisions or no
    # answer) now proves it outright.
    law = ("for theta in [1.5707963267948966, 1.5707963267948966], "
           "f(theta) >= 1e15")
    r = _run(tangent, law, extensive=True)
    assert r.verdict == "proven", (r.verdict, r.sketch)


def abs_value(x: float) -> float:
    if x >= 0:
        return x
    return -x


def test_branch_lift_follows_each_calls_own_argument():
    # field bug (2026-09-03): the domain-pruned lift baked ONE branch
    # into every f(...) call, so f(-x) on [-100, 0) evaluated the wrong
    # branch and |x| == |-x| falsified. A pruned lift now refuses
    # transformed arguments and the full piecewise lift (valid at any
    # argument) takes over, proven, on the fast path too.
    for law in ("for x in [-100, 100], f(x) == f(-x)",
                "for x in [-100, -1], f(x) == f(-x)"):
        r = _run(abs_value, law, extensive=False)
        assert r.verdict == "proven", (law, r.verdict, r.sketch)


def inverse_square(k: float, x: float) -> float:
    return k / x ** 2


def test_divergence_claims_decide_against_a_literal_infinity():
    # field limitation (2026-09-03), closed: lim(...) == oo used to hit
    # oo - oo = nan inside .equals(). Infinite sides now decide
    # structurally, both ways.
    law = "for k in [1,1000], x in [0.1,100], lim(f(k,x), x, 0) == oo"
    assert _run(inverse_square, law, extensive=False).verdict == "proven"
    wrong = "for k in [1,1000], x in [0.1,100], lim(f(k,x), x, oo) == oo"
    assert _run(inverse_square, wrong, extensive=False).verdict == "falsified"


def am_gm_gap(a: float, b: float) -> float:
    return (a + b) / 2 - math.sqrt(a * b)


def test_am_gm_now_proves_on_the_fast_pass_via_squaring():
    # field limitation (2026-09-03), closed twice over: first by the
    # joint sqrt substitution (extensive), now by the fast squaring
    # rescue with no extensive at all
    law = "for a in [0,100], b in [0,100], f(a,b) >= 0"
    fast = _run(am_gm_gap, law, extensive=False)
    assert fast.verdict == "proven", (fast.verdict, fast.sketch)
    assert fast.meta.get("mathema.derive_route") == "squared_comparison"


def test_am_gm_joint_sqrt_substitution_rung_still_proves(monkeypatch):
    # ladder-level coverage for this rung specifically: the
    # optional nlsat rung would win first, so it is masked here
    import mathema.symbolic._smt as smt
    monkeypatch.setattr(smt, "available", lambda: False)
    # the joint-substitution rung keeps its own coverage at the ladder
    # level: t = sqrt(a), s = sqrt(b) SIMULTANEOUSLY exposes
    # ((t - s)^2)/2, a visible sum of squares
    import sympy
    from mathema.symbolic._extensive import extensive_ladder
    a = sympy.Symbol("a", nonnegative=True)
    b = sympy.Symbol("b", nonnegative=True)
    result, attempted = extensive_ladder(
        (a + b) / 2 - sympy.sqrt(a * b), sympy.S.Zero, ">=",
        {"a": (0.0, 100.0), "b": (0.0, 100.0)}, None, {"a": a, "b": b})
    assert result is not None and result.status == "proven", attempted
    assert "jointly" in (result.sketch or "")


def qm_am_gap(a: float, b: float) -> float:
    return math.sqrt((a * a + b * b) / 2) - (a + b) / 2


def triangle_slack(a: float, b: float) -> float:
    return abs(a) + abs(b) - abs(a + b)


def test_qm_am_proves_via_the_squaring_rescue():
    # was a pinned knife edge ("QM-AM wants a square-both-sides
    # rewrite"); the squaring rescue is exactly that rewrite, and the
    # pin flips as the pin itself predicted
    r = _run(qm_am_gap, "for a in [0,100], b in [0,100], f(a,b) >= 0",
             extensive=True)
    assert r.verdict == "proven", (r.verdict, r.sketch)
    assert r.meta.get("mathema.derive_route") == "squared_comparison"


def test_triangle_inequality_proves_via_the_nlsat_rung():
    # formerly the pinned open limitation (the Abs kinks defeated the
    # sign engine; the claim only ever HELD), flipped deliberately,
    # per the old pin's own instruction, when the nlsat rung landed:
    # Abs is a native if-then-else term there, and the whole claim
    # decides exactly. Without the extra the old honest holds returns.
    import pytest
    pytest.importorskip("z3")
    r = _run(triangle_slack, "for a in [-50,50], b in [-50,50], f(a,b) >= 0",
             extensive=True)
    assert r.verdict == "proven", (r.verdict, r.sketch)
    assert "nlsat" in (r.sketch or "")


def test_catalan_asymptotic_limit_proves():
    # the corpus's Catalan growth-rate claim: a hard asymptotic limit
    # whose computation must fit the tier's own lowering budget
    import math

    def catalan_number_closed_form(n):
        if n < 0:
            raise ValueError("index cannot be negative")
        return math.factorial(2 * n) / (
            math.factorial(n + 1) * math.factorial(n))

    r = _run(catalan_number_closed_form,
             "for n in [1, 100], "
             "lim(f(n)/(4**n/(n**1.5*sqrt(pi))), n, oo) == 1",
             extensive=False)
    assert r.verdict == "proven", (r.verdict, r.sketch)
