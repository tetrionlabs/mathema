# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`nan` in claim text is the float nan, never a variable to sample.

A claim that appends a nan to a vector (`f(c(xs, [nan])) ~= f(xs)`)
states what the function does with one missing element; reading `nan`
as a free name drew it as an ordinary number and falsified a function
that skips nan correctly.
"""
from __future__ import annotations

import math

from mathema.conjecture import check_conjectures, claim


def nan_mean(xs: list) -> float:
    """The mean of the elements that are not nan."""
    vals = [x for x in xs if not math.isnan(x)]
    return sum(vals) / len(vals)


def plain_mean(xs: list) -> float:
    """The mean of every element."""
    return sum(xs) / len(xs)


_LAW = ("let c = mathema.f.concat_seq, for xs in [-1, 1]^n \\ {∅}, "
        "f(c(xs, [nan])) ~= f(xs)")


def test_a_function_that_skips_nan_holds():
    (p,) = check_conjectures(nan_mean, [claim(_LAW)])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample,
                                              p.note)
    assert "nan =" not in (p.counterexample or "")


def test_a_function_that_propagates_nan_is_falsified_at_the_nan():
    (p,) = check_conjectures(plain_mean, [claim(_LAW)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "nan =" not in (p.counterexample or ""), p.counterexample
