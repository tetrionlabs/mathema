# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The generalized ClaimFamily mechanism (mathema/families.py):
detection by claim name, multiple routes per family. Covers the two
concrete families this unlocks, monotonic/affine/convex/concave via
probe:algorithmic (pairwise sampling / finite-difference curvature),
and is_numerically_stable via a domain_hazards-based derive route,
directly against the mechanism, and end to end through
check_conjectures()."""
import math
import random

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.claim_families import (_monotone_probe, _is_numerically_stable_derive,
                                    _second_difference_probe)


def clamp01(x: float) -> float:
    return max(0.0, min(x, 1.0))


def sq(x: float) -> float:
    return x ** 2


def line(x: float) -> float:
    return 3.0 * x + 2.0


def npv_two_period(c1: float, r: float) -> float:
    return c1 / (1 + r)


# --- the mechanism, directly -------------------------------------------

def test_monotone_probe_holds_for_a_genuinely_increasing_direction():
    facts = analyze_source(clamp01)
    cj = claim("d(f(x), x) >= 0", name="monotonic_increasing[x]")
    result = _monotone_probe(clamp01, facts, cj, {}, random.Random(1), 200,
                             increasing=True)
    assert result[0] == "holds"


def test_monotone_probe_falsifies_a_genuinely_wrong_direction():
    facts = analyze_source(clamp01)
    cj = claim("d(f(x), x) <= 0", name="monotonic_decreasing[x]")
    result = _monotone_probe(clamp01, facts, cj, {}, random.Random(1), 200,
                             increasing=False)
    assert result[0] == "falsified"
    assert result[2] is not None   # a real counterexample


def test_monotone_probe_declines_when_the_claim_names_no_real_parameter():
    facts = analyze_source(clamp01)
    cj = claim("f(x) == f(x)", name="not_a_real_param[y]")
    assert _monotone_probe(clamp01, facts, cj, {}, random.Random(1), 50,
                           increasing=True) is None


def test_second_difference_probe_holds_for_a_genuinely_affine_function():
    facts = analyze_source(line)
    cj = claim("d(f(x), x, x) == 0", name="affine[x]")
    result = _second_difference_probe(line, facts, cj, {}, random.Random(2), 100,
                                      kind="affine")
    assert result[0] == "holds"


def test_second_difference_probe_falsifies_affine_for_a_genuinely_convex_function():
    facts = analyze_source(sq)
    cj = claim("d(f(x), x, x) == 0", name="affine[x]")
    result = _second_difference_probe(sq, facts, cj, {}, random.Random(3), 100,
                                      kind="affine")
    assert result[0] == "falsified"


def test_second_difference_probe_holds_convex_for_a_genuinely_convex_function():
    facts = analyze_source(sq)
    cj = claim("d(f(x), x, x) >= 0", name="convex[x]")
    result = _second_difference_probe(sq, facts, cj, {}, random.Random(4), 100,
                                      kind="convex")
    assert result[0] == "holds"


def test_second_difference_probe_falsifies_concave_for_a_genuinely_convex_function():
    facts = analyze_source(sq)
    cj = claim("d(f(x), x, x) <= 0", name="concave[x]")
    result = _second_difference_probe(sq, facts, cj, {}, random.Random(5), 100,
                                      kind="concave")
    assert result[0] == "falsified"


def test_is_numerically_stable_derive_disproven_when_domain_contains_a_pole():
    facts = analyze_source(npv_two_period)
    result = _is_numerically_stable_derive(npv_two_period, facts, "", "", "==",
                                        domain={"r": (-2.0, 0.0)})
    assert result is not None
    assert result.status == "disproven"


def test_is_numerically_stable_derive_undecided_when_domain_excludes_the_pole():
    # every pole excluded still leaves overflow and NaN open, so the
    # probe decides
    facts = analyze_source(npv_two_period)
    result = _is_numerically_stable_derive(npv_two_period, facts, "", "", "==",
                                        domain={"r": (0.0, 5.0)})
    assert result is None


def test_is_numerically_stable_derive_declines_with_no_declared_domain():
    facts = analyze_source(npv_two_period)
    assert _is_numerically_stable_derive(npv_two_period, facts, "", "", "==",
                                      domain=None) is None


# --- end to end, through check_conjectures() ----------------------------

def test_clamp01_monotonic_claims_resolve_via_probe_algorithmic_end_to_end():
    facts = analyze_source(clamp01)
    results = check_conjectures(
        clamp01,
        [claim("d(f(x), x) >= 0", name="monotonic_increasing[x]", route="best"),
         claim("d(f(x), x) <= 0", name="monotonic_decreasing[x]", route="best")],
        facts=facts)
    by_name = {r.name: r for r in results}
    assert by_name["monotonic_increasing[x]"].verdict == "holds"
    assert by_name["monotonic_increasing[x]"].route == "probe:algorithmic"
    assert by_name["monotonic_decreasing[x]"].verdict == "falsified"
    assert by_name["monotonic_decreasing[x]"].route == "probe:algorithmic"


def test_a_derive_route_claim_falls_back_to_the_family_with_the_route_named():
    # a route="derive" claim whose proof attempt can't decide is now
    # adjudicated by the family's probe:algorithmic technique, an
    # unknown is superseded by empirical evidence, with the route
    # field naming the mechanism that actually decided, never a
    # silently relabeled "derive".
    facts = analyze_source(clamp01)
    results = check_conjectures(
        clamp01, [claim("d(f(x), x) >= 0", name="monotonic_increasing[x]",
                       route="derive")],
        facts=facts)
    assert results[0].verdict == "holds"
    assert results[0].route == "probe:algorithmic"


def exp_over_x(x: float) -> float:
    return math.exp(x) / x


def test_pole_exclusion_alone_does_not_prove_numerical_stability():
    # no pole of exp(x)/x lies in [1, 1000], but exp overflows past
    # 709.78, where finite_no_error(f, x) is 0
    (p,) = check_conjectures(exp_over_x, [claim(
        "for x in [1, 1000], g(f, x) == 1", name="is_numerically_stable",
        route="best", funcs={"g": "mathema.f.finite_no_error"})])
    assert p.verdict != "proven", (p.verdict, p.sketch)
    assert p.verdict == "falsified"
