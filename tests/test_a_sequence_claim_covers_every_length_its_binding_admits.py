# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim over sequences covers every call its binding admits.

An unbound list admits every length, the empty list included; one
bound over a dimension name (`x in R^n`) admits every length from one,
and may admit the empty list; two sequences bound apart admit
different lengths. Where the code raises on one of those
calls (an empty list it divides by the length of, two lists of
different lengths it reads position by position) the claim is false
there, so the derive route never proves it. A premise that excludes
the call (`assuming len(x) >= 1`), or one binding that ties two
lengths (`for a in R^n, b in R^n`), is how a claim narrows itself, and
then the proof stands. A literal index (`x[2]`) needs a sequence long
enough to hold it in the same way.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from mathema.claims import check_conjectures, claim


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
    (rms, "f(signal) == f(signal)"),
    (rms, "for signal in R^n, f(signal) == f(signal)"),
    (sample_variance_two_pass, "f(xs) == f(xs)"),
    (ema, "f(x, 1.0) == x[-1]"),
    (dot_product, "f(a, b) == f(a, b)"),
    (dot_product, "assuming len(a) >= 1, assuming len(b) >= 1, "
                  "f(a, b) == f(a, b)"),
    (dot_weights, "assuming len(weights) >= 1, assuming len(features) >= 1, "
                  "f(weights, features) == f(weights, features)"),
    (total, "f(xs) >= xs[0] - 100"),
    (total, "for xs in [0, 1]^n, f(xs) >= xs[2]"),
])
def test_a_claim_whose_domain_admits_a_raising_call_is_not_proven(fn, law):
    p = _derive(fn, law)
    assert p.verdict != "proven", (law, p.verdict, p.sketch, p.note)


@pytest.mark.parametrize("fn, law", [
    (rms, "f(signal) == f(signal)"),
    (sample_variance_two_pass, "f(xs) >= 0"),
    (dot_product, "f(a, b) == f(a, b)"),
])
def test_the_empty_list_is_an_executed_witness(fn, law):
    p = _derive(fn, law)
    assert p.verdict == "falsified", (law, p.verdict, p.sketch, p.note)
    assert "[]" in (p.counterexample or ""), p.counterexample


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, law", [
    (ema, "assuming len(x) >= 1, f(x, 1.0) == x[-1]"),
    (dot_product, "for a in R^n, b in R^n, assuming len(a) >= 1, "
                  "f(a, b) == f(a, b)"),
    (dot_product, "assuming len(a) == len(b), assuming len(a) >= 1, "
                  "f(a, b) == f(a, b)"),
    (dot_product, "for a in R^3, b in R^3, f(a, b) == f(a, b)"),
    (total, "for xs in [0, 1]^3, f(xs) >= xs[2]"),
    (total, "f(xs) == f(xs)"),
])
def test_a_claim_that_narrows_itself_is_proven(fn, law):
    p = _derive(fn, law)
    assert (p.verdict, p.route) == ("proven", "derive"), (law, p.verdict,
                                                          p.sketch, p.note)


def test_a_tied_binding_never_draws_one_empty_list_beside_a_full_one():
    p = _derive(dot_product, "for a in R^n, b in R^n, assuming len(a) >= 1, "
                             "f(a, b) == f(a, b)")
    assert p.verdict != "falsified", (p.verdict, p.counterexample)


def test_a_dimension_name_leaves_the_empty_list_open():
    p = _derive(sample_variance_two_pass, "for xs in R^n, f(xs) >= 0")
    assert p.verdict not in ("proven", "falsified"), (p.verdict, p.sketch)
    assert "empty list" in (p.sketch or p.note or ""), (p.sketch, p.note)


def test_two_lengths_that_differ_are_an_executed_witness():
    p = _derive(dot_product, "assuming len(a) >= 1, assuming len(b) >= 1, "
                             "f(a, b) == f(a, b)")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert "a = [1.0, 2.0], b = [1.0]" in (p.counterexample or ""), \
        p.counterexample
