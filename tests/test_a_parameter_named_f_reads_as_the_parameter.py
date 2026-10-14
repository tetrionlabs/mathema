# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function whose own parameter is named `f` (a Fahrenheit reading, a
frequency) gets the verdicts the same function gets with the parameter
renamed: in a claim, `f(...)` is the call to the function under test and
a bare `f` is the parameter, on every route."""
import pytest

import mathema
from mathema.types import Mat


def to_celsius(f):
    return (f - 32) * 5 / 9


def to_celsius_deg(deg):
    return (deg - 32) * 5 / 9


def warmest(f):
    best = 32.0
    for value in (f, 32.0):
        if value > best:
            best = value
    return best


def warmest_deg(deg):
    best = 32.0
    for value in (deg, 32.0):
        if value > best:
            best = value
    return best


def _verdicts(fn, claims=None):
    record = mathema.check(fn, claims=claims)
    return {p.name.replace("[f]", "[deg]"): (p.verdict, p.route)
            for p in record.probes}


@pytest.mark.parametrize("route", [None, "probe"])
def test_a_claim_on_f_gets_the_renamed_twins_verdicts(route):
    kw = {"route": route} if route else {}
    named_f = _verdicts(to_celsius, [mathema.claim(
        "for f in [32, 212], f(f) >= 0", name="above_freezing", **kw)])
    renamed = _verdicts(to_celsius_deg, [mathema.claim(
        "for deg in [32, 212], f(deg) >= 0", name="above_freezing", **kw)])
    assert named_f["above_freezing"] == renamed["above_freezing"]
    if route is None:
        assert named_f["above_freezing[float]"] == ("holds", "probe")


def test_an_unliftable_body_is_decided_by_the_probe_for_f_too():
    named_f = _verdicts(warmest, [mathema.claim(
        "for f in [0, 100], f(f) >= 32", name="at_least_freezing")])
    renamed = _verdicts(warmest_deg, [mathema.claim(
        "for deg in [0, 100], f(deg) >= 32", name="at_least_freezing")])
    assert named_f["at_least_freezing"] == renamed["at_least_freezing"]
    assert named_f["at_least_freezing"][0] == "holds"


def test_the_suggested_rows_agree_with_the_renamed_twin():
    named_f = _verdicts(to_celsius)
    renamed = _verdicts(to_celsius_deg)
    for name in ("even", "odd", "idempotent"):
        assert named_f[name] == renamed[name], name
        assert named_f[name][0] == "falsified", name


def test_a_property_of_the_result_gets_the_renamed_twins_verdict():
    named_f = _verdicts(to_celsius, [mathema.claim(
        "for f in [32, 212], is_finite(f(f))", name="finite")])
    renamed = _verdicts(to_celsius_deg, [mathema.claim(
        "for deg in [32, 212], is_finite(f(deg))", name="finite")])
    assert named_f["finite"] == renamed["finite"]
    assert named_f["finite"][0] == "holds"


def scaled(f: Mat("n", "n")):
    return [[2 * x for x in row] for row in f]


def scaled_a(a: Mat("n", "n")):
    return [[2 * x for x in row] for row in a]


def test_a_matrix_property_of_the_result_gets_the_renamed_twins_verdict():
    named_f = _verdicts(scaled, [mathema.claim(
        "is_symmetric(f(f))", name="symmetric")])
    renamed = _verdicts(scaled_a, [mathema.claim(
        "is_symmetric(f(a))", name="symmetric")])
    assert named_f["symmetric"] == renamed["symmetric"]
    assert named_f["symmetric"][0] == "falsified"


def test_an_indexed_sum_over_f_gets_the_renamed_twins_verdicts():
    named_f = _verdicts(to_celsius, [mathema.claim(
        "for f in [0, 10], Sum(f(f) + i, i, 1, 3) >= -100", name="summed")])
    renamed = _verdicts(to_celsius_deg, [mathema.claim(
        "for deg in [0, 10], Sum(f(deg) + i, i, 1, 3) >= -100",
        name="summed")])
    for name in ("summed", "summed[float]"):
        assert named_f[name] == renamed[name], name
    assert named_f["summed[float]"] == ("holds", "probe")
