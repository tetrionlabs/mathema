# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_overflow_safe[param] at the representation extremes (the family
absorbs is_extremity_safe, whose spelling is still accepted): whether
the computation overflows is a fact about float64, settled by
executing it. The probe calls the real function at the
representation-extreme inputs the domain admits, scoped by the claim's
pseudo-infinity range when one is stated, reaching true float extremes
on an unbounded, uncapped domain."""
import math

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims


def exp_of(x: float) -> float:
    return math.exp(x)


def doubled(x: float) -> float:
    return x * 2.0


def _one(fn, law, domain=None):
    (probe,) = check_conjectures(fn, [claim(law, route="best")],
                                 domain=domain, facts=analyze_source(fn))
    return probe


def test_a_bounded_domain_inside_float_range_holds_by_execution():
    # a value hull inside float range says nothing about the
    # intermediate results, so no proof is claimed; every executed point
    # stays in range
    probe = _one(exp_of, "is_overflow_safe(x)", domain={"x": (0.0, 10.0)})
    assert probe.verdict == "holds"


def test_the_retired_spelling_is_the_same_claim():
    old = _one(exp_of, "is_extremity_safe(x)", domain={"x": (0.0, 1000.0)})
    new = _one(exp_of, "is_overflow_safe(x)", domain={"x": (0.0, 1000.0)})
    assert old.name == new.name == "is_overflow_safe[x]"
    assert old.verdict == new.verdict == "falsified"


def test_admitted_overflow_point_falsifies_with_its_witness():
    # exp over [0, 1000]: the hull escapes float range so analysis
    # cannot prove, and the probe watches the real call overflow at
    # the admitted endpoint
    probe = _one(exp_of, "is_overflow_safe(x)", domain={"x": (0.0, 1000.0)})
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "x = 1000" in probe.counterexample


def test_uncapped_unbounded_domain_reaches_true_extremes():
    probe = _one(exp_of, "is_overflow_safe(x)", domain={"x": (0.0, float("inf"))})
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"


def test_pseudo_infinity_scopes_the_extreme_trials():
    fn = exp_of
    (probe,) = check_conjectures(
        fn, [claim("let |inf| be 100, is_overflow_safe(x)", route="best")],
        domain={"x": (0.0, float("inf"))}, facts=analyze_source(fn))
    # exp(100) ~ 2.7e43 is comfortably representable: with infinity
    # operationally bound at 100 the trials stay there and hold
    assert probe.verdict == "holds"
    assert probe.route == "probe:algorithmic"


def test_suggested_only_for_overflow_prone_structure():
    exp_suggestions = {c.name for c in suggest_claims(exp_of)}
    assert "is_overflow_safe[x]" in exp_suggestions
    plain_suggestions = {c.name for c in suggest_claims(doubled)}
    assert not any(n.startswith("is_overflow_safe") for n in plain_suggestions)
