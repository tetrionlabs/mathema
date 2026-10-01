# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A literal index into an array a function returns reads the array as
numpy does: `[-1]` is the last element, and an index past the end
raises `IndexError`, which inside the claim's domain counts against
the claim.

`ellipse_path(cx, cy, a, b, n)[0]` is `cx + a*cos(2*pi*k/(n - 1))` at
position `k`, so its last element `[-1]` is `cx + a` (the path closes),
never the closed form read at `k = -1`. At `n = 5`, `[9]` is past the
end: the call raises, the claim is not proven, and its computation row
never counts that raise as a pass.
"""
from __future__ import annotations

import numpy as np
import pytest

from mathema.claims import check_conjectures, claim


def ellipse_path(cx, cy, a, b, n):
    phi = np.linspace(0.0, 2.0 * np.pi, n)
    x = cx + a * np.cos(phi)
    y = cy + b * np.sin(phi)
    return x, y


_N = "for n in [2, 50] subset Z, "


def _all(law, route="best"):
    return check_conjectures(ellipse_path, [claim(law, route=route)],
                             float_companions=True)


def test_minus_one_is_never_the_closed_form_read_at_minus_one():
    (p, *_rest) = _all(_N + "f(cx, cy, a, b, n)[0][-1] == "
                       "cx + a*cos(2*pi*(-1)/(n-1))", "derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)


@pytest.mark.needs_full_proof_budget
def test_minus_one_is_the_last_element():
    (p, *_rest) = _all(_N + "f(cx, cy, a, b, n)[0][-1] == cx + a", "derive")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_an_index_past_the_end_is_not_proven():
    (p, *_rest) = _all("for n in [5, 5] subset Z, "
                       "f(cx, cy, a, b, n)[0][9] == cx", "derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    (p, *_rest) = _all(_N + "f(cx, cy, a, b, n)[0][9] == "
                       "cx + a*cos(2*pi*9/(n-1))", "derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_an_index_past_the_end_is_falsified_and_its_computation_too():
    probes = _all("for n in [5, 5] subset Z, f(cx, cy, a, b, n)[0][9] == cx")
    assert probes[0].verdict == "falsified", (probes[0].verdict,
                                              probes[0].note)
    for p in probes[1:]:
        assert p.verdict != "holds", (p.name, p.verdict, p.note)


def test_a_point_whose_claim_evaluation_fails_is_never_counted_as_a_pass():
    from mathema.corroboration import INCONCLUSIVE, sweep_stability
    sweep = sweep_stability(lambda point: INCONCLUSIVE, ["x"],
                            sample=lambda name, rng: 0.5,
                            corners=[{"x": 0.0}], admits=lambda p: True,
                            budget=5)
    assert sweep.checked == 0
    assert sweep.fragile_point is None


def less_one(x: float) -> float:
    return x - 1


def test_a_claim_with_no_value_at_a_point_never_passes_there():
    (p,) = check_conjectures(less_one, [claim(
        "for x in [1, 1], f(x) / f(x) == 1", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ZeroDivisionError" in (p.counterexample or ""), p.counterexample
