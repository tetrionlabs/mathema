# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When f returns its exact value correctly rounded and the claim still
misses on its `[float]` line, the loss is in the claim's own expression
run in float64: the note says so, the loss counts as inherent (no
float64 computation of f does better), and it never tells the reader to
rearrange f's formula."""
import math

from mathema.conjecture import check_conjectures, claim


def root(x: float) -> float:
    return math.sqrt(x)


def test_squaring_a_correctly_rounded_root_blames_the_claims_expression():
    rows = check_conjectures(root, [claim("for x in [1, 100], f(x) ** 2 ~= x",
                                          tolerance={"ulp": 0})],
                             float_companions=True)
    line = next(p for p in rows if p.name.endswith("[float]"))
    assert line.verdict == "falsified", line
    found = line.meta["mathema.conditioning"]
    assert found["inherent"] is True, found
    assert "the claim's own expression" in found["words"], found
    assert "different arrangement" not in found["words"], found
