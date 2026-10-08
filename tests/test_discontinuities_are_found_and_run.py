# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Discontinuities of a computation are found from the lifted body, or
the claim's own text when the body does not lift, and run on purpose:
floor, ceil and int() where their argument is whole, round where it is
a half-integer, a remainder where its quotient is whole, sign at zero, a
branch where its two sides are equal. On an integer domain they are
enumerated exactly; on a real interval each is solved for and run with
its float neighbours."""
import math
from fractions import Fraction

import sympy

import mathema
from mathema import _discontinuities as D
from mathema.analysis import analyze_source
from mathema.conjecture import claim


def rounded(x: float) -> float:
    return round(x)


def stepped(x: float, n: float) -> float:
    if x > n:
        return math.floor(x) - n
    return x % n


def tenths(x: float) -> float:
    return math.floor(10 * x) / 10


def _found(fn, law):
    return {(str(d.expr), d.kind) for d in
            D.discontinuities(claim(law), fn, analyze_source(fn))}


def test_each_kind_is_found_in_the_body():
    found = _found(stepped, "for x in [0, 5], n in [1, 2], f(x, n) >= 0")
    assert ("x", "whole") in found, found            # floor(x)
    assert ("x/n", "whole") in found, found          # x % n
    assert ("n - x", "zero") in found, found         # the branch x > n


def test_sign_is_found_at_zero():
    found = D._from_expr(sympy.sign(sympy.Symbol("x") - 1))
    assert [(str(d.expr), d.kind) for d in found] == [("x - 1", "zero")]


def test_round_is_found_in_the_claim_at_half_integers():
    found = _found(rounded, "for x in [0, 5], f(x) == round(x)")
    assert ("x", "half") in found


def test_an_integer_grid_is_enumerated_exactly():
    a, p = sympy.symbols("active periods")
    found = [D.Discontinuity(100 * a / p, "whole", "ceil(100*active/periods)")]
    points = [{"active": i, "periods": j} for j in range(1, 261)
              for i in range(0, j + 1)]
    hits = D.on_grid(found, points)
    assert {(h["active"], h["periods"]) for h in hits} == {
        (pt["active"], pt["periods"]) for pt in points
        if (100 * pt["active"]) % pt["periods"] == 0}


def test_a_real_interval_is_solved_with_float_neighbours():
    x = sympy.Symbol("x")
    values, skipped = D.on_interval(
        [D.Discontinuity(10 * x, "whole", "floor(10*x)")], "x", 0.0, 1.0)
    assert skipped == 0
    assert 0.3 in values
    assert math.nextafter(0.3, 0) in values and math.nextafter(0.3, 1) in values


def test_a_long_range_is_capped_and_says_how_many_were_skipped():
    x = sympy.Symbol("x")
    _values, skipped = D.on_interval(
        [D.Discontinuity(x, "whole", "floor(x)")], "x", 0.0, 1000.0)
    assert skipped == 1001 - D.SOLVE_CAP


def test_a_real_domain_computation_falls_at_a_discontinuity():
    # the float nearest 0.3 lies just below 3/10, so floor(10*x)/10 is
    # 2/10 there in exact arithmetic, while 10 * x rounds up to 3.0 in
    # float64 and f returns 0.3 (the claim side is read exactly on the
    # computation line, ruling of 2026-10-01)
    assert tenths(0.3) == 0.3
    assert math.floor(10 * Fraction(0.3)) == 2
    rows = {p.name: p for p in mathema.check(
        tenths, claims=["for x in [0, 1], f(x) == floor(10*x)/10"]).probes}
    (float_row,) = [p for n, p in rows.items() if n.endswith("[float]")]
    assert float_row.verdict == "falsified", float_row.note
    x = float(float_row.counterexample.split(":")[0].split("=")[1])
    assert Fraction(tenths(x)) != Fraction(math.floor(10 * Fraction(x)), 10)
    assert float_row.route == "probe:semi_analytical"
    assert " at discontinuities of " in float_row.note
    assert "the domain has" not in float_row.note
