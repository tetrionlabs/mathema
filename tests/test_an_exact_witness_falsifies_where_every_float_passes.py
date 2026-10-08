# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When the mathematics is false at a point no float reaches, the
mathematics line is falsified by its exact witness, checked by exact
evaluation independent of the solver that found it: a rational witness
run exactly, an algebraic one as the root of its polynomial inside an
isolating interval, a transcendental one by certified interval balls
(ruling of 2026-10-01: mathematics false while every float passes)."""
import math

import mathema


def ident(x: float) -> float:
    return x


def square(x: float) -> float:
    return x * x


def tangent(x: float) -> float:
    return math.tan(x)


def _row(fn, law):
    (p,) = [p for p in mathema.check(fn, claims=[mathema.claim(law, name="c")]).probes
            if p.name == "c"]
    return p


def test_a_rational_witness_no_float_reaches():
    p = _row(ident, "for x in [0, 0.3], f(x) <= 0.3 - 10**-20")
    assert p.verdict == "falsified", p.note
    assert p.counterexample == "x = 3/10"


def test_an_algebraic_witness():
    p = _row(square, "for x in [1, 2], f(x) != 2")
    assert p.verdict == "falsified", p.note
    assert p.counterexample == "x = sqrt(2)"


def test_a_pole_certified_by_interval_balls():
    p = _row(tangent, "for x in [1, 2], f(x) < 1e17")
    assert p.verdict == "falsified", p.note
    assert "certified by interval arithmetic" in p.note


def test_true_claims_stay_unfalsified():
    assert _row(square, "for x in [1, 2], f(x) != 5").verdict == "proven"
    assert _row(ident, "for x in [0, 0.3], f(x) <= 0.3").verdict == "proven"
    assert _row(tangent, "for x in [0, 1], f(x) < 1e17").verdict != "falsified"


def test_is_defined_falls_at_a_pole_no_float_reaches():
    p = _row(tangent, "for x in [0, 2], is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "certified by interval arithmetic" in (p.note or "") + (p.sketch or "")


def test_is_defined_still_holds_away_from_the_pole():
    assert _row(tangent, "for x in [0, 1], is_defined(f)").verdict in ("proven", "holds")
