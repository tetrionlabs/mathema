# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Floating-point boundary raises on the probe route: a raise inside a
value claim's domain falsifies it, even where the same inputs nudged
within epsilon evaluate cleanly. That sub-epsilon case is named in the
counterexample with the clamp remedy and stratum 5.6, the same way the
is_numerically_stable axis reports it."""
import math

import pytest

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


def test_sub_epsilon_boundary_raise_falsifies_with_the_clamp_remedy():
    # the degenerate domain pins every sample to the knife edge itself:
    # each call raises there, and each nudge within epsilon escapes,
    # so the raise is sub-epsilon, yet still a raise in the domain
    (p,) = check_conjectures(
        knife_edge, [claim("for x in [1, 1], f(x) == 0", route="probe",
                           tolerance=1e-6)])
    assert p.verdict == "falsified"
    assert "floating-point boundary" in p.counterexample
    assert "clamp" in p.counterexample
    assert p.stratum["cause"] == "implementation:sub-epsilon-boundary"
    assert p.meta["mathema.counterexample_args"] == [1.0]
    with pytest.raises(ValueError):
        knife_edge(*p.meta["mathema.counterexample_args"])


def _reciprocal(x: float) -> float:
    return 1.0 / x


def _log(x: float) -> float:
    return math.log(x)


@pytest.mark.parametrize("fn, law", [
    (_reciprocal, "for x in [0, 1], f(x) >= 1"),
    (_log, "for x in [0, 1], f(x) <= 0"),
])
def test_a_raise_at_a_closed_endpoint_falsifies_on_the_probe_route(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="probe")])
    assert p.verdict == "falsified"
    witness = p.meta["mathema.counterexample_args"]
    assert witness == [0.0] or witness == [0]
    with pytest.raises((ZeroDivisionError, ValueError)):
        fn(*witness)
    assert "mathema.boundary_fragility" not in p.meta


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
