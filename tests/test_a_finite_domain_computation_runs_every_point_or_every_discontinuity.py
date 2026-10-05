# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The computation line of a claim over a finite domain runs every
point when the sweep fits its budget, and otherwise every point where a
discontinuity of the code or the claim, then a seeded sample; its
note says how much of the domain ran. `ceil(active / periods * 100)`
in float64 gives 29 at active = 7, periods = 25, where the exact value
is 28, and 40 such pairs hide among 34,190 points."""
import math
from fractions import Fraction

import mathema

_LAW = ("for periods in [1, 260] subset Z, active in [0, 260] subset Z, "
        "assuming active <= periods, "
        "f(active, periods) == ceil(100*active/periods)/100")


def exposure_formula(active: int, periods: int) -> float:
    return math.ceil(active / periods * 100) / 100


def exposure_exact(active: int, periods: int) -> float:
    return math.ceil(Fraction(active, periods) * 100) / 100


def _failing():
    return {(a, p) for p in range(1, 261) for a in range(0, p + 1)
            if round(exposure_formula(a, p) * 100) != -((-100 * a) // p)}


def _rows(fn):
    return {p.name: p for p in mathema.check(fn, claims=[_LAW]).probes}


def _point(text):
    pairs = dict(part.split(" = ") for part in text.split(":")[0].split(", "))
    return int(pairs["active"]), int(pairs["periods"])


def test_the_float_line_falls_at_a_discontinuity_while_the_mathematics_is_proven():
    failing = _failing()
    assert (7, 25) in failing and len(failing) == 40
    rows = _rows(exposure_formula)
    (math_row,) = [p for n, p in rows.items() if not n.endswith("[float]")
                   and n.startswith("f_active")]
    (float_row,) = [p for n, p in rows.items() if n.endswith("[float]")]
    assert math_row.verdict == "proven"
    assert float_row.verdict == "falsified", float_row.note
    assert _point(float_row.counterexample) in failing, float_row.counterexample


def test_a_small_finite_domain_runs_every_point():
    law = ("for periods in [1, 30] subset Z, active in [0, 30] subset Z, "
           "assuming active <= periods, "
           "f(active, periods) == ceil(100*active/periods)/100")
    rows = {p.name: p for p in mathema.check(exposure_formula, claims=[law]).probes}
    (float_row,) = [p for n, p in rows.items() if n.endswith("[float]")]
    assert float_row.verdict == "falsified", float_row.note
    assert "every point of the domain in order up to the first failure; " \
        "the domain has 495 points)" in float_row.note, float_row.note
    assert float_row.route == "probe"


def test_an_exact_computation_stays_proven():
    rows = _rows(exposure_exact)
    main = [p for n, p in rows.items() if n.startswith("f_active")
            and not n.endswith("[float]")]
    assert [p.verdict for p in main] == ["proven"], [(p.name, p.verdict) for p in main]


def test_a_sweep_over_budget_runs_every_discontinuity_and_says_what_it_covered(monkeypatch):
    from mathema import gates
    monkeypatch.setattr(gates, "_SWEEP_SECONDS", 0.0)
    rows = _rows(exposure_formula)
    (float_row,) = [p for n, p in rows.items() if n.endswith("[float]")]
    assert float_row.verdict == "falsified", float_row.note
    assert _point(float_row.counterexample) in _failing()
    assert " at discontinuities of ceil(100*active/periods)" in float_row.note, \
        float_row.note
    assert "; the domain has 34,190 points)" in float_row.note, float_row.note
    assert float_row.route == "probe:semi_analytical"
