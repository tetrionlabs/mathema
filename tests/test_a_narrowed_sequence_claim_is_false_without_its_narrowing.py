# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Each sequence claim the suite narrows (`assuming len(x) >= 1`, or two
lists tied to one length) is narrowed because the unnarrowed claim is
false: an unbound list admits the empty list, and two unbound lists
admit different lengths, and the code raises there. Every unnarrowed
claim below is falsified with the executed witness, so no narrowing
elsewhere in the suite hides a defect.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from mathema.claims import check_conjectures, claim


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def ema_scaled(x: list, alpha: float, scale: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y * scale


def guarded_ema(x: list, alpha: float) -> float:
    if alpha < 0:
        raise ValueError("negative weight")
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def mean_of_list(x: list) -> float:
    total = 0.0
    for v in x:
        total += v
    return total / len(x)


def two_pass_variance(xs: list) -> float:
    total = 0.0
    for x in xs:
        total += x
    mean = total / len(xs)
    sq = 0.0
    for x in xs:
        sq += (x - mean) ** 2
    return sq / len(xs)


def rms(signal: list) -> float:
    total = 0.0
    for v in signal:
        total += v * v
    return math.sqrt(total / len(signal))


def dot_ab(a: list, b: list) -> float:
    return float(np.dot(a, b))


def index_dot(a: list, b: list) -> float:
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


def manhattan(x: list, y: list) -> float:
    t = 0.0
    for i in range(len(x)):
        t = t + abs(x[i] - y[i])
    return t


#: (function, the claim without the narrowing the suite adds to it)
UNNARROWED = [
    (ema, "f(x, 1.0) == x[-1]"),
    (ema, "f(x, alpha) == x[-1]"),
    (ema, "f(x, alpha) == f(x, alpha)"),
    (ema, "for alpha in [1, 1], f(x, alpha) == x[-1]"),
    (ema, "for alpha in [0, 1], min(x) <= f(x, alpha)"),
    (ema, "for alpha in [0, 1], f(x, alpha) <= max(x)"),
    (ema, "for alpha in [0, 1], f(x, alpha) >= min(x)"),
    (ema, "for alpha in [0,1], let c be [0.1, 10], "
          "c*f(x, alpha) == f(mathema.f.scale_seq(x, c), alpha)"),
    (ema_scaled, "f(x, 1.0, 2.0) == 2 * x[-1]"),
    (guarded_ema, "for alpha in [0, 1], f(x, 1.0) == x[-1]"),
    (mean_of_list, "f(x) * 0.0 == 0.0"),
    (mean_of_list, "abs(f(x)) >= 0.0"),
    (two_pass_variance, "f(xs) == f(xs)"),
    (rms, "f(signal) == f(signal)"),
    (dot_ab, "f(a, b) == f(a, b)"),
    (dot_ab, "abs(f(a, b)) >= 0.0"),
    (index_dot, "f(a, b) == f(a, b)"),
    (manhattan, "f(x, y) >= 0"),
]


def _law(law: str):
    if "mathema.f.scale_seq" in law:
        return claim(law.replace("mathema.f.scale_seq", "g"),
                     funcs={"g": "mathema.f.scale_seq"})
    return claim(law)


@pytest.mark.parametrize("fn, law", UNNARROWED,
                         ids=[f"{fn.__name__}: {law}" for fn, law in UNNARROWED])
def test_the_unnarrowed_claim_is_falsified_with_its_witness(fn, law):
    (p,) = check_conjectures(fn, [_law(law)])
    assert p.verdict == "falsified", (law, p.verdict, p.note, p.sketch)
    assert (p.meta or {}).get("mathema.corroboration") == "reproduced", p.meta
    assert "= []" in (p.counterexample or ""), p.counterexample
