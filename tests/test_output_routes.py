# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Output routes state the actual evidence mechanism, never the
input-side "auto": `route="best"` only tells the verifier to try the
strongest route first and fall back, so an adjudicated Probe's own
`route` is always the mechanism that really ran ("derive", "probe", a
colon subroute), and a claim skipped before any mechanism engaged
carries `route=None`, not a copy of whatever the input said."""
from mathema.conjecture import check_conjectures, claim


def add(a: float, b: float) -> float:
    return a + b


def test_no_adjudicated_probe_ever_reports_route_auto():
    cjs = [
        claim("f(a, b) == f(b, a)", name="commutative", route="best"),
        claim("f(a, b) <= a + b + 1", name="bounded", route="best"),
    ]
    for probe in check_conjectures(add, cjs):
        assert probe.route != "auto", (probe.name, probe.verdict, probe.route)


def test_validation_skip_carries_no_route_at_all():
    bad_relation = claim("f(a, b) == f(b, a)", route="best")
    bad_relation.relation = "~~"   # force an unknown relation past parsing
    (probe,) = check_conjectures(add, [bad_relation])
    assert probe.verdict == "skipped"
    assert probe.route is None

    unknown_route = claim("f(a, b) == f(b, a)", route="quantum")
    (probe,) = check_conjectures(add, [unknown_route])
    assert probe.verdict == "skipped"
    assert probe.route is None
    assert "quantum" in (probe.note or "")


def test_auto_claim_that_proves_reports_derive():
    (probe,) = check_conjectures(
        add, [claim("f(a, b) == f(b, a)", name="commutative", route="best")])
    assert probe.verdict == "proven"
    assert probe.route == "derive"


def test_best_route_cascades_and_reports_the_winning_mechanism():
    # route="best" is the cascade derive -> derive:extensive -> probe,
    # in one adjudication pass (the fast attempt runs once; the ladder
    # starts where it left off). The output route names whichever
    # mechanism actually settled it.
    import math

    def straddler(x: float) -> float:
        return x * math.sin(x)

    # ladder-provable: the fast attempt can't settle it, refinement can
    (p,) = check_conjectures(
        straddler, [claim("for x in [-1, 1], f(x) >= 0", route="best")])
    assert p.verdict == "proven"
    assert p.route == "derive:extensive"

    # nothing derives: falls through to the probe stage
    (p,) = check_conjectures(straddler, [claim("f(x) >= -x^2", route="best")])
    assert p.verdict == "holds"
    assert p.route == "probe"


def test_auto_spelling_normalizes_to_best():
    # "auto" is the legacy spelling, kept free of the route vocabulary
    # so the word stays available for automatic differentiation.
    assert claim("f(a, b) == f(b, a)", route="best").route == "best"
    assert claim("f(a, b) == f(b, a)", route="best").route == "best"
