# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`x / 10` at x = 100 returns 10.0, the exact tenth. The claim's own side
`x * 0.1` is read exactly with the literal as float64 holds it (the
computation's reading of a literal), 10.000000000000000555, so under a
zero tolerance the `[float]` line misses by that literal's rounding. The
note puts the loss in the claim's own expression, never in f, and never
tells the reader to rearrange f."""
import pytest

from mathema.conjecture import check_conjectures, claim


def tenth(x: float) -> float:
    return x / 10


@pytest.mark.parametrize("tolerance", [0, {"ulp": 0}, {"abs": 0}, {"rel": 0}])
def test_the_tenths_miss_is_the_claims_own_expression(tolerance):
    rows = check_conjectures(tenth, [claim("for x in {100}, f(x) ~= x * 0.1",
                                           tolerance=tolerance)],
                             float_companions=True)
    line = next(p for p in rows if p.name.endswith("[float]"))
    found = line.meta["mathema.conditioning"]
    assert found["inherent"] is True, found
    assert "the claim's own expression" in found["words"], found
    assert "different arrangement" not in found["words"], found
