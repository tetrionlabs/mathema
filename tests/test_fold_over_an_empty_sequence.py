# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A fold claim that admits the empty sequence is judged on what the
code does with one.

A sequence parameter's default domain is the nonempty lists (an empty
one is a precondition the code states by reading `xs[0]` or dividing by
`len(xs)`). A premise such as `assuming len(xs) == 0` puts the empty
list inside the claim's domain, and there `mean([])` raises
ZeroDivisionError, whatever the closed form says at length zero.
"""
from mathema.conjecture import check_conjectures, claim


def mean(xs: list) -> float:
    s = 0.0
    for v in xs:
        s = s + v
    return s / len(xs)


def total(xs: list) -> float:
    y = 0.0
    for v in xs:
        y = y + v
    return y


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def _v(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


def test_a_raise_on_the_admitted_empty_list_falsifies():
    for fn, law in ((mean, "assuming len(xs) == 0, f(xs) == 0"),
                    (mean, "assuming len(xs) <= 1, f(xs) * len(xs) == 0"),
                    (ema, "assuming len(x) == 0, for alpha in [0, 1], "
                          "f(x, alpha) == 0")):
        p = _v(fn, law)
        assert p.verdict == "falsified", (law, p.verdict, p.sketch, p.note)
        assert "[]" in (p.counterexample or ""), p.counterexample


def test_a_fold_that_returns_on_the_empty_list_still_proves():
    p = _v(total, "assuming len(xs) == 0, f(xs) == 0")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_a_premise_excluding_the_empty_list_leaves_the_proof_alone():
    p = _v(mean, "assuming len(xs) >= 1, f(xs) * len(xs) == f(xs) * len(xs)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
