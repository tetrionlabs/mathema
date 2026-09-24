# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Interval evaluation propagates bounds through `Min` and `Max`: for
arguments in [a_k, b_k], `Min` lies in [min a_k, min b_k] and `Max` in
[max a_k, max b_k]. A clipped value is then bounded by interval
reasoning alone, with no SMT solver, and a bound the clip exceeds is
never proven."""
import pytest
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.symbolic._proof_support import _interval_bounds


def clip(x: float) -> float:
    return min(max(x, 0.0), 1.0)


@pytest.fixture
def no_smt(monkeypatch):
    import mathema.symbolic._smt as smt
    monkeypatch.setattr(smt, "available", lambda: False)


def _probe(law, **kw):
    (probe,) = check_conjectures(clip, [claim(law, **kw)])
    return probe


@pytest.mark.parametrize("route", ["derive", "best"])
def test_the_clip_is_at_most_one_by_interval_evaluation(no_smt, route):
    probe = _probe("for x in [-5, 5], f(x) <= 1", route=route)
    assert probe.verdict == "proven", (probe.verdict, probe.note)
    assert probe.route == "derive"
    assert "interval evaluation" in probe.sketch
    assert "nlsat" not in probe.sketch


@pytest.mark.parametrize("route", ["derive", "best"])
def test_the_clip_is_nonnegative_without_smt(no_smt, route):
    probe = _probe("for x in [-5, 5], f(x) >= 0", route=route)
    assert probe.verdict == "proven", (probe.verdict, probe.note)
    assert probe.route == "derive"
    assert "nlsat" not in probe.sketch


@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_bound_the_clip_exceeds_is_not_proven(route):
    probe = _probe("for x in [-5, 5], f(x) <= 0.5", route=route)
    assert probe.verdict != "proven", (probe.verdict, probe.sketch)
    assert probe.verdict == "falsified", (probe.verdict, probe.note)


x = sympy.Symbol("x", real=True)
y = sympy.Symbol("y", real=True)
_BOX = {"x": (-5.0, 5.0), "y": (2.0, 3.0)}
_PARAMS = {"x": x, "y": y}


@pytest.mark.parametrize("expr, lo, hi", [
    (sympy.Min(1, sympy.Max(0, x)), 0, 1),
    (1 - sympy.Min(1, sympy.Max(0, x)), 0, 1),
    (sympy.Min(x, 2), -5, 2),
    (sympy.Max(x, 2), 2, 5),
    (sympy.Min(x, y), -5, 3),
    (sympy.Max(x, y), 2, 5),
    (sympy.Max(x, y) - sympy.Min(x, y), -1, 10),
])
def test_min_and_max_hulls(expr, lo, hi):
    hull = _interval_bounds(expr, _BOX, _PARAMS)
    assert isinstance(hull, sympy.AccumBounds), hull
    assert (hull.min, hull.max) == (lo, hi)


def test_an_unbounded_argument_keeps_the_hull_unbounded():
    hull = _interval_bounds(sympy.Max(0, x), {}, {"x": x})
    assert isinstance(hull, sympy.AccumBounds), hull
    assert hull.min == 0 and hull.max == sympy.oo
