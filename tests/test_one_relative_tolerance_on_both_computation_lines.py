# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Both computation lines, the probe standing in for a claim no proof
settles and the `[float]` line beside a proof, compare with one rule:
an absolute 1e-9 plus 1e-7 times the larger result, with no floor, so
the two lines agree on the same computation and a tiny result cannot
hide a large relative error (ruling of 2026-10-01: tolerance belongs to
the computation, one rule on both lines)."""
import math

import mathema
from mathema.conjecture import check_conjectures, claim


def nearly(x: float) -> float:
    return 1.0000005 * x


def gap(x: float) -> float:
    return math.sqrt(x * x + 1) - x


def test_a_relative_error_of_5e_7_falls_on_the_probe():
    (p,) = check_conjectures(nearly, [claim(
        "for x in [1, 1000], f(x) == x", route="probe")])
    assert p.verdict == "falsified", p.note


def test_a_cancelled_small_result_falls_on_the_float_line():
    rows = {p.name: p for p in mathema.check(gap, claims=[
        mathema.claim("for x in [1, 1e8], f(x) == 1 / (sqrt(x**2 + 1) + x)",
                      name="conjugate")]).probes}
    assert rows["conjugate"].verdict == "proven"
    assert rows["conjugate[float]"].verdict == "falsified", \
        rows["conjugate[float]"].note
