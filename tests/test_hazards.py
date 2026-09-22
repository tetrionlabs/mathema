# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/hazards.py: the shared hazard registry; one home for
where an implementation can diverge from the mathematics, queried by
kind, extensible by registration."""
import math

from mathema.analysis import analyze_source
from mathema.hazards import (HazardPoint, _GENERATORS, hazard_points,
                             register_hazard_generator)


def reciprocal_shift(x: float) -> float:
    return 1.0 / (x - 2.0)


def log_of(x: float) -> float:
    import math
    return math.log(x)


def guarded(x: float) -> float:
    if x != x:
        raise ValueError("missing")
    return x + 1.0


def test_pole_generator_finds_the_shifted_pole():
    facts = analyze_source(reciprocal_shift)
    points = hazard_points(reciprocal_shift, facts, kinds=["pole"])
    assert any(p.kind == "pole" and p.param == "x" and p.value == 2.0
               for p in points)


def test_builtin_edge_generator_names_logs_zero_edge():
    facts = analyze_source(log_of)
    points = hazard_points(log_of, facts, kinds=["builtin_domain"])
    edges = [p for p in points if p.param == "x" and p.source == "log"]
    assert edges and any(p.value == 0.0 for p in edges)


def test_missing_generator_emits_one_nan_point_per_scalar_param():
    facts = analyze_source(guarded)
    points = hazard_points(guarded, facts, kinds=["missing"])
    assert len(points) == 1
    (point,) = points
    assert point.param == "x" and math.isnan(point.value)


def test_unrequested_kinds_stay_out():
    facts = analyze_source(log_of)
    kinds = {p.kind for p in hazard_points(log_of, facts,
                                           kinds=["builtin_domain"])}
    assert kinds <= {"builtin_domain"}


def test_registered_generator_joins_the_sweep_and_a_failing_one_is_skipped():
    facts = analyze_source(guarded)

    def custom(fn, facts, domain):
        return [HazardPoint("custom", "x", "7", 7.0, source="test")]

    def broken(fn, facts, domain):
        raise RuntimeError("generator bug")

    register_hazard_generator("custom", custom)
    register_hazard_generator("broken", broken)
    try:
        points = hazard_points(guarded, facts)
        assert any(p.kind == "custom" and p.value == 7.0 for p in points)
        # the broken generator contributes nothing and breaks nothing
        assert all(p.kind != "broken" for p in points)
    finally:
        del _GENERATORS["custom"]
        del _GENERATORS["broken"]
