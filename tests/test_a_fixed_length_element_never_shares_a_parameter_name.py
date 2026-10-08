# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A binding that fixes a sequence's length (`x in [0, 1]^2`) lets the
derive route expand its sums and decide the claim over each element as
a bounded number. Each element is its own number: `x[1]` is never the
same symbol as a parameter named `x_1`, so `sum(x) - x_1 >= x[0]` is
not proven (it fails at `x = [0, 0], x_1 = 5`), while
`sum(x) - x_1 >= x[0] - x_1` is.
"""
from __future__ import annotations

import mathema


def total_less(x: list, x_1: float) -> float:
    s = 0.0
    for v in x:
        s += v
    return s - x_1


def _row(law):
    r = mathema.check(total_less, claims=[law])
    (p,) = [p for p in r.probes if p.statement and "f(x" in p.statement
            and "[float" not in (p.name or "")]
    return p


def test_an_element_and_a_parameter_with_a_similar_name_stay_apart():
    p = _row("for x in [0, 1]^2, x_1 in [-5, 5], f(x, x_1) >= x[0]")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)


def test_the_true_sibling_is_proven_at_the_fixed_length():
    p = _row("for x in [0, 1]^2, x_1 in [-5, 5], f(x, x_1) >= x[0] - x_1")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
