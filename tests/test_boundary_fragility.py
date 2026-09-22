# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Floating-point boundary fragility on the probe route: a raise the
declared tolerance absorbs (the same inputs nudged within epsilon
evaluate cleanly and satisfy the claim) is machine noise, not a
mathematical counterexample, surfaced in the note with the clamp
remedy, and caught as a real falsification by the is_numerically_stable
axis, whose whole question is the raw machine."""
import mathema
from mathema.conjecture import claim, check_conjectures


def knife_edge(x: float) -> float:
    """Raises only in a ~2-ulp band around x*x == 1, the acos-style
    fragility shape, deterministic for tests (the sampler's specials
    include x = 1.0 exactly)."""
    if 1.0 <= x * x <= 1.0000000000000002:
        raise ValueError("edge")
    return 0.0


def hard_edge(x: float) -> float:
    if x > 0.5:
        raise ValueError("no")
    return x


def test_sub_epsilon_boundary_raise_is_absorbed_within_tolerance():
    # the degenerate domain pins every sample to the knife edge itself:
    # each call raises, each nudge within epsilon escapes and satisfies
    # the claim, so every sample is absorbed fragility
    (p,) = check_conjectures(
        knife_edge, [claim("for x in [1, 1], f(x) == 0", route="probe",
                           tolerance=1e-6)])
    assert p.verdict == "holds"
    assert "floating-point boundary" in p.note
    assert "clamp" in p.note
    assert p.meta.get("mathema.boundary_fragility", 0) >= 1


def test_is_numerically_stable_still_falsifies_the_same_fragility():
    rec = mathema.check(knife_edge)
    ns = next(p for p in rec.probes if p.name == "is_numerically_stable")
    assert ns.verdict == "falsified"
    assert "clamp" in ns.counterexample
    assert "floating-point boundary" in ns.counterexample


def test_a_real_raise_region_is_never_absorbed():
    # jittering within epsilon cannot escape a half-line raise region:
    # the pedantic falsification stands, with the claims-side remedy
    (p,) = check_conjectures(
        hard_edge, [claim("for x in [0, 1], f(x) <= 1", route="probe",
                          tolerance=1e-6)])
    assert p.verdict == "falsified"
    assert "narrow the claim's domain" in p.counterexample


def test_empirical_fallback_handles_domain_typed_integer_bounds(monkeypatch):
    # regression: the sampling-shorthand renderer subscripted a
    # Domain-typed bound (a `⊂ Z` refinement) as if it were a (lo, hi)
    # tuple and crashed with TypeError on the empirical-fallback path.
    # The sweep budget is dropped below this domain's four points so the
    # empirical path is the one actually taken; without that the
    # brute-force route settles the claim and the renderer this guards
    # is never reached.
    import math

    from mathema import _brute_force
    monkeypatch.setattr(_brute_force, "BRUTE_FORCE_POINT_BUDGET", 1)

    def choose(n, k):
        return math.factorial(n) / (math.factorial(k) * math.factorial(n - k))

    (p,) = check_conjectures(
        choose, [claim("for n in [10,11] ⊂ Z, k in [5,6] ⊂ Z, f(n,k) >= 1",
                       route="derive")])
    assert p.verdict == "holds"
    assert ":int" in p.meta.get("mathema.sampling", "")
