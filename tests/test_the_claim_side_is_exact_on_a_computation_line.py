# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""On a computation line the function runs in floats, and the claim's
own arithmetic is mathematics: its sides are evaluated exactly, so a
claim written in a form that cancels in float (`(x + 1e16) - 1e16`,
numpy.clip's midpoint-and-half-gap definition on wide bounds) never
falsifies correct code (rulings of 2026-10-01: the mathematics is exact,
tolerance belongs to the computation)."""
import numpy as np

from mathema.conjecture import check_conjectures, claim


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
