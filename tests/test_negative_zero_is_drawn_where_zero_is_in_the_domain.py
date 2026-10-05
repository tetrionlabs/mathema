# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""-0.0 is a float input wherever 0 is in the domain, and some code
tells it apart from 0.0: atan2(-0.0, -1.0) is -pi while atan2(0.0,
-1.0) is pi. The computation line draws it."""
import math

import mathema


def angle(y: float) -> float:
    return math.atan2(y, -1.0)


def test_the_computation_line_reaches_negative_zero():
    rows = {p.name: p for p in mathema.check(
        angle, claims=["for y in [0, 1], f(y) >= 0"]).probes}
    (float_row,) = [p for n, p in rows.items() if n.endswith("[float]")]
    assert float_row.verdict == "falsified", float_row.note
    y = float(float_row.counterexample.split(":")[0].split("=")[1])
    assert y == 0.0 and math.copysign(1.0, y) == -1.0, float_row.counterexample
