# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim over sequences covers every length its binding admits.

An unbound list, and one bound over a dimension name (`x in R^n`),
admits every length from one; two sequences bound apart admit
different lengths. Where the code raises on one of those calls (two
lists of different lengths it reads position by position, a literal
index `x[2]` past the end of a short list) the claim is false there,
so the derive route never proves it, and an executed call is its
witness. One binding that ties two lengths (`for a in R^n, b in R^n`),
or a premise that does (`assuming len(a) == len(b)`), is how a claim
narrows itself, and then the proof stands. The empty list is the
claim's empty-input line (see
`test_a_value_claim_is_its_mathematics_and_its_empty_input_line.py`).
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")

import math  # noqa: E402

import numpy as np  # noqa: E402

from mathema.claims import check_conjectures, claim  # noqa: E402


def rms(signal: list) -> float:
    total = 0.0
    for v in signal:
        total += v * v
    return math.sqrt(total / len(signal))


def sample_variance_two_pass(xs: list) -> float:
    total = 0.0
    for x in xs:
        total += x
    mean = total / len(xs)
    sq = 0.0
    for x in xs:
        sq += (x - mean) ** 2
    return sq / len(xs)


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def dot_product(a: list, b: list) -> float:
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total


def dot_weights(weights: list, features: list) -> float:
    return float(np.dot(weights, features))


def total(xs: list) -> float:
    y = 0.0
    for v in xs:
        y = y + v
    return y


def _derive(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


@pytest.mark.parametrize("fn, law", [
    (dot_product, "f(a, b) == f(a, b)"),
    (dot_product, "assuming len(a) >= 1, assuming len(b) >= 1, "
                  "f(a, b) == f(a, b)"),
    (dot_weights, "assuming len(weights) >= 1, assuming len(features) >= 1, "
                  "f(weights, features) == f(weights, features)"),
    (total, "for xs in [0, 1]^n, f(xs) >= xs[2]"),
])
def test_a_claim_whose_domain_admits_a_raising_call_is_not_proven(fn, law):
    p = _derive(fn, law)
    assert p.verdict != "proven", (law, p.verdict, p.sketch, p.note)


def test_two_lengths_that_differ_are_an_executed_witness():
    p = _derive(dot_product, "f(a, b) == f(a, b)")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert p.counterexample == "a = [1.0, 2.0], b = [1.0]", p.counterexample


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, law", [
    (ema, "f(x, 1.0) == x[-1]"),
    (dot_product, "for a in R^n, b in R^n, f(a, b) == f(a, b)"),
    (dot_product, "assuming len(a) == len(b), f(a, b) == f(a, b)"),
    (dot_product, "for a in R^3, b in R^3, f(a, b) == f(a, b)"),
    (total, "for xs in [0, 1]^3, f(xs) >= xs[2]"),
    (total, "f(xs) == f(xs)"),
    (rms, "f(signal) == f(signal)"),
    (sample_variance_two_pass, "f(xs) == f(xs)"),
])
def test_a_claim_over_lengths_it_can_read_is_proven(fn, law):
    p = _derive(fn, law)
    assert (p.verdict, p.route) == ("proven", "derive"), (law, p.verdict,
                                                          p.sketch, p.note)
