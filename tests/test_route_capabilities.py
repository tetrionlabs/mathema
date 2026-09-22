# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The route-capability model (mathema.routes): which claim forms each
route can adjudicate, as one table rather than scattered conditionals."""
from mathema import routes
from mathema.conjecture import claim


def test_required_forms_finds_calculus_and_predicates():
    assert routes.required_forms(claim("for x in [1,5], d(f(x),x) >= 0")) == {"d"}
    assert routes.required_forms(claim("integrate(f(x), x, 0, 1) == 1")) \
        == {"integrate"}
    assert routes.required_forms(claim("for x in [1,5], f(x) >= 0")) == set()
    assert routes.required_forms(claim("raises(f(x), ValueError)")) == {"raises"}
    assert routes.required_forms(claim("is_pole_safe(x)")) == {"is_pole_safe"}


def test_probe_cannot_evaluate_calculus_forms():
    assert routes.unsupported_forms("probe", claim("d(f(x),x) >= 0")) == ["d"]
    assert routes.unsupported_forms(
        "probe", claim("integrate(f(x), x, 0, 1) == 1")) == ["integrate"]


def test_raises_predicates_and_plain_relations_are_on_both_routes():
    for route in ("derive", "probe"):
        assert routes.unsupported_forms(route, claim("raises(f(x))")) == []
        assert routes.unsupported_forms(route, claim("f(x) >= 0")) == []
        for predicate in sorted(routes.SAFETY_PREDICATES):
            assert routes.unsupported_forms(
                route, claim(f"{predicate}(x)")) == []


def test_derive_supports_every_form():
    for law in ("d(f(x),x) >= 0", "integrate(f(x),x,0,1)==1",
                "is_pole_safe(x)", "raises(f(x))"):
        assert routes.unsupported_forms("derive", claim(law)) == []


def test_cascading_route_reports_nothing_unsupported():
    # best cascades; capability is decided per concrete route
    assert routes.unsupported_forms("best", claim("d(f(x),x) >= 0")) == []


def test_auto_is_fully_retired_not_an_alias():
    # the hard purge: "auto" is an unknown route like any other,
    # a calculus claim reports its forms unsupported, and
    # adjudication skips it loudly (see check_conjectures' gate)
    assert routes.unsupported_forms("auto", claim("d(f(x),x) >= 0")) == ["d"]
    from mathema.conjecture import check_conjectures
    from dataclasses import replace

    def double(x: float) -> float:
        return 2.0 * x
    cj = replace(claim("f(x) >= 0"), route="auto")
    (probe,) = check_conjectures(double, [cj])
    assert probe.verdict == "skipped"
    assert "unknown route" in probe.note


def test_examine_owns_exactly_the_safety_predicates():
    for predicate in sorted(routes.SAFETY_PREDICATES):
        assert routes.unsupported_forms(
            "examine", claim(f"{predicate}(x)")) == []
    # an ordinary relation has nothing to examine
    assert routes.unsupported_forms("examine", claim("f(x) >= 0")) == []
    assert routes.unsupported_forms(
        "examine", claim("d(f(x),x) >= 0")) == ["d"]
