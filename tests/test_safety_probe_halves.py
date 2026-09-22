# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The empirical halves of is_pole_safe and is_builtin_safe: targeted
trials at hazard-informed points (admitted pole locations, restricted
builtins' domain edges), reachable both by route="probe" directly and
as route="best"'s fallback. Sampling witnesses violation, never
absence: a clean run holds, avoidance proofs stay derive's alone."""
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim


def shifted_reciprocal(x: float) -> float:
    return 1.0 / (x - 2.0)


def log_bare(x: float) -> float:
    import math
    return math.log(x)


def log_guarded(x: float) -> float:
    import math
    return math.log(x) if x > 0 else 0.0


def _one(fn, law, route, domain):
    (probe,) = check_conjectures(fn, [claim(law, route=route)],
                                 domain=domain, facts=analyze_source(fn))
    return probe


def test_admitted_pole_falsifies_structurally_whatever_route_was_asked():
    # the examine cascade runs the structural half first: the pole of
    # the lifted form sits inside the declared bound, an established
    # fact about this code, falsified with the location as witness
    probe = _one(shifted_reciprocal, "is_pole_safe(x)", "probe",
                 domain={"x": (0.0, 5.0)})
    assert probe.verdict == "falsified"
    assert probe.route == "examine"
    assert "x = 2" in probe.counterexample


def test_excluded_pole_proves_structurally_beside_the_boundary():
    # the domain stops just past the pole: containment establishes
    # exclusion, so the examination proves, the trial half never
    # needs to run
    probe = _one(shifted_reciprocal, "is_pole_safe(x)", "probe",
                 domain={"x": (2.001, 5.0)})
    assert probe.verdict == "proven"
    assert probe.route == "examine"


def test_route_is_advisory_for_an_implementation_fact():
    # the fact doesn't depend on the declared route: even asking for
    # route="probe", the examine cascade runs the structural half
    # first, which proves the far domain excludes the pole, the
    # same verdict any other spelling of the route would get
    probe = _one(shifted_reciprocal, "is_pole_safe(x)", "probe",
                 domain={"x": (10.0, 20.0)})
    assert probe.verdict == "proven"
    assert probe.route == "examine"


def test_builtin_probe_falsifies_logs_admitted_zero_edge():
    probe = _one(log_bare, "is_builtin_safe(x)", "probe",
                 domain={"x": (0.0, 10.0)})
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "log" in probe.counterexample


def test_builtin_probe_holds_when_the_implementation_handles_the_edge():
    # the body guards the unsafe region (log only on the positive
    # branch), so trials AT the admitted edge values return cleanly:
    # the empirical half reports what the code actually does
    probe = _one(log_guarded, "is_builtin_safe(x)", "probe",
                 domain={"x": (-1.0, 10.0)})
    assert probe.verdict == "holds"
    assert probe.n > 0


def test_best_route_cascades_to_the_pole_probe_on_underived_bounds():
    # a frozenset bound isn't the plain interval the derive half's
    # containment reasoning takes, so route="best" falls through to
    # the empirical half, which witnesses the admitted pole for real
    probe = _one(shifted_reciprocal, "is_pole_safe(x)", "best",
                 domain={"x": frozenset({2.0, 3.0})})
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "x = 2" in probe.counterexample
