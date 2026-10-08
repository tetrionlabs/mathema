# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The curvature probe reads the bend of f at a point on the scale of
that point and of f there: log over (0, oo) bends down everywhere
(its second derivative is -1/x^2), so it is neither affine nor convex
however small that bend is far out, and a straight line near the
largest double stays affine."""
import math
import random

from mathema.analysis import analyze_source
from mathema.claim_families import _second_difference_probe
from mathema.conjecture import claim


def line(x: float) -> float:
    return 0.5 * x + 1.0


def log(x: float) -> float:
    return math.log(x)


def square(x: float) -> float:
    return x * x


def _verdict(fn, law, name):
    cj = claim(law, name=name)
    out = _second_difference_probe(fn, analyze_source(fn), cj, cj.domain,
                                   random.Random(0), 200,
                                   kind=name.split("[")[0])
    return out[0]


def test_log_is_neither_affine_nor_convex_over_the_positive_line():
    assert _verdict(log, "for x in (0, oo), d(f(x), x, x) == 0", "affine[x]") == "falsified"
    assert _verdict(log, "for x in (0, oo), d(f(x), x, x) >= 0", "convex[x]") == "falsified"
    assert _verdict(log, "for x in (0, oo), d(f(x), x, x) <= 0", "concave[x]") == "holds"


def test_a_line_near_the_float_limit_is_affine():
    assert _verdict(line, "for x in [1e300, 1e308], d(f(x), x, x) == 0",
                    "affine[x]") == "holds"


def test_a_square_is_convex_and_not_affine():
    assert _verdict(square, "for x in [-1e6, 1e6], d(f(x), x, x) >= 0", "convex[x]") == "holds"
    assert _verdict(square, "for x in [-1e6, 1e6], d(f(x), x, x) == 0", "affine[x]") == "falsified"
