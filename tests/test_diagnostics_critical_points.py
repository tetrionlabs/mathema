# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/diagnostics.py's critical_points() and its three detectors:
poles (domain_hazards, reused not duplicated), stationary/inflection
points, and domain-transition points (sqrt/log/Abs/sign argument
crossing zero)."""
import sympy

from mathema.diagnostics import (_fractional_power_and_log_hazards,
                                 _stationary_and_inflection_points,
                                 critical_points, domain_hazards)

x = sympy.symbols("x")


def _dummy_fn():
    """A real function with a real source file, for _source_file()."""


def test_stationary_and_inflection_points_on_a_cubic():
    # x**3 - 3x: stationary at x=-1,1 (slope zero), inflection at x=0
    # (curvature zero), three distinct roots across the two kinds.
    expr = x ** 3 - 3 * x
    points = _stationary_and_inflection_points(expr, "<test>")
    stationary = {p["at"] for p in points if p["kind"] == "stationary"}
    inflection = {p["at"] for p in points if p["kind"] == "inflection"}
    assert stationary == {"-1", "1"}
    assert inflection == {"0"}


def test_fractional_power_hazard_for_a_sqrt_argument():
    points = _fractional_power_and_log_hazards(sympy.sqrt(x - 4), "<test>")
    assert len(points) == 1
    assert points[0]["kind"] == "domain_transition"
    assert points[0]["at"] == "4"


def test_fractional_power_hazard_for_a_log_argument():
    points = _fractional_power_and_log_hazards(sympy.log(x), "<test>")
    assert points[0]["at"] == "0"


def test_fractional_power_hazard_for_an_abs_argument():
    points = _fractional_power_and_log_hazards(sympy.Abs(x - 2), "<test>")
    assert points[0]["at"] == "2"


def test_domain_hazards_still_works_unmodified_after_the_refactor():
    r, c1 = sympy.symbols("r c1")
    hazards = domain_hazards(_dummy_fn, c1 / (1 + r))
    assert len(hazards) == 1
    assert hazards[0]["kind"] == "pole"
    assert hazards[0]["at"] == "-1"
    assert hazards[0]["domain"] == "assumed (-inf, inf), not declared"


def test_critical_points_combines_a_pole_and_a_stationary_point(tmp_path):
    # x's own derivative (-1/(x-3)**2) has no finite root, keeping
    # the pole and the stationary point in separate free symbols
    # keeps each root clean and independently checkable.
    fixture = tmp_path / "fixture.py"
    fixture.write_text(
        "def f(x: float, y: float) -> float:\n"
        "    return 1 / (x - 3) + y ** 2\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        from fixture import f
        points = critical_points(f)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("fixture", None)
    kinds = {p["kind"] for p in points}
    assert "pole" in kinds
    assert "stationary" in kinds
    pole = next(p for p in points if p["kind"] == "pole")
    assert pole["at"] == "3"
    stationary = next(p for p in points if p["kind"] == "stationary")
    assert stationary["at"] == "0"
    assert stationary["variable"] == "y"


def test_critical_points_returns_empty_for_an_unliftable_function(tmp_path):
    fixture = tmp_path / "fixture_unliftable.py"
    fixture.write_text(
        "def f(x):\n"
        "    import os\n"
        "    return os.getpid() + x\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        from fixture_unliftable import f
        assert critical_points(f) == []
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("fixture_unliftable", None)
