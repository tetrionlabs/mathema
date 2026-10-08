# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""On a computation line the function runs in floats, and the claim's
own arithmetic is mathematics: its sides are evaluated exactly, so a
claim written in a form that cancels in float (`(x + 1e16) - 1e16`,
numpy.clip's midpoint-and-half-gap definition on wide bounds) never
falsifies correct code (rulings of 2026-10-01: the mathematics is exact,
tolerance belongs to the computation)."""

import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402


def ident(x: float) -> float:
    return x


def clip(a: np.ndarray, a_min: float, a_max: float) -> np.ndarray:
    return np.clip(a, a_min, a_max)


def test_a_claim_side_that_cancels_in_float_does_not_falsify():
    (p,) = check_conjectures(ident, [claim(
        "for x in [0, 1], f(x) == (x + 1e16) - 1e16", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_numpys_clip_definition_holds_on_its_natural_bounds():
    (p,) = check_conjectures(clip, [claim(
        "for a in R^n, a_min in R, a_max in R, assuming a_min <= a_max, "
        "f(a, a_min, a_max) ~= ((a + a_min + abs(a - a_min)) / 2 + a_max "
        "- abs((a + a_min + abs(a - a_min)) / 2 - a_max)) / 2",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_a_wrong_function_still_falls_with_an_exact_claim_side():
    def off(x: float) -> float:
        return x + 1.0
    (p,) = check_conjectures(off, [claim(
        "for x in [0, 1], f(x) == (x + 1e16) - 1e16", route="probe")])
    assert p.verdict == "falsified"


def test_the_float_line_reads_the_claim_side_exactly():
    import mathema
    rows = {p.name: p for p in mathema.check(ident, claims=[
        "for x in [0, 1], f(x) == (x + 1e16) - 1e16"]).probes}
    (math_row,) = [p for n, p in rows.items() if n.startswith("f_x")
                   and not n.endswith("[float]")]
    (float_row,) = [p for n, p in rows.items() if n.endswith("[float]")]
    assert math_row.verdict == "proven"
    assert float_row.verdict == "holds", (float_row.counterexample, float_row.note)


def test_numpys_own_clip_holds_its_definition_where_inputs_may_be_missing():
    import mathema
    (p,) = [p for p in mathema.check(np.clip, claims=[mathema.claim(
        "for a in R^n, a_min in R, a_max in R, f(a, a_min, a_max) ~= "
        "((a + a_min + abs(a - a_min)) / 2 + a_max "
        "- abs((a + a_min + abs(a - a_min)) / 2 - a_max)) / 2",
        name="definition")]).probes if p.name == "definition"]
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def floor_tenths_by_product(x: float) -> float:
    import math
    return math.floor(10 * x) / 10


def test_a_float_claim_side_that_rounds_like_the_code_does_not_hide_it():
    # at the float nearest 0.3 (just below 3/10) the code computes
    # floor(3.0) / 10 = 0.3, while the claim read exactly gives 2/10:
    # the float claim side makes the same rounding and would agree
    import mathema
    rows = {p.name: p for p in mathema.check(
        floor_tenths_by_product,
        claims=["for x in [0, 1], f(x) == floor(10*x)/10"]).probes}
    (float_row,) = [p for n, p in rows.items() if n.endswith("[float]")]
    assert float_row.verdict == "falsified", float_row.note
    from fractions import Fraction
    import math
    x = float(float_row.counterexample.split(":")[0].split("=")[1])
    assert Fraction(floor_tenths_by_product(x)) != \
        Fraction(math.floor(10 * Fraction(x)), 10)


def test_the_probe_line_reads_the_claim_exactly_too():
    (p,) = check_conjectures(floor_tenths_by_product, [claim(
        "for x in {0.3, 0.5}, f(x) == floor(10*x)/10", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "read exactly" in p.counterexample


def sign_of(x: float) -> float:
    import math
    return math.copysign(1.0, x)


def test_a_negative_zero_literal_stays_negative_zero():
    # the computation reads -0.0 as the float it is, which code like
    # copysign tells apart from 0.0
    (p,) = check_conjectures(sign_of, [claim(
        "for x in [1, 2], f(-0.0) == -1", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_the_computation_reading_keeps_integer_literals_exact():
    # small integer literals may not sit among a code object's constants
    # (Python 3.14 loads them by an instruction of their own); the
    # computation's reading still divides them exactly
    from fractions import Fraction

    from mathema._exact_side import exact_sides
    from mathema.conjecture import _validate
    code_l, _ = _validate("x", {"x"}, set())
    code_r, _ = _validate("7 / 10", {"x"}, set())
    sides = exact_sides(code_l, code_r, {"x": 0.5}, {})
    assert sides is not None and sides[1] == Fraction(7, 10), sides
