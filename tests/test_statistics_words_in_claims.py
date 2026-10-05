# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The grammar's statistics words, read on the probe route.

`mean`, `std(a, ddof=k)`, `var(a, ddof=k)`, `sum`, `prod`, `min`,
`max`, `count`, `len`, `cumsum` and `cumprod` read a vector the way
numpy does, over its value slots: `ddof` defaults to 0 (the population
statistic), `count` is the number of value slots and `len` the number
of positions, `cumsum` and `cumprod` are the running sum and product
with a hole kept at its position. A sample statistic needs two value
slots; over no value slot `sum` is 0, `prod` 1 and `count` 0, and
`mean`, `std`, `var`, `min` and `max` are a hole. Each true statement holds against a function that
computes it, and a false sibling beside it is falsified.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import mathema

from mathema.claims import check_conjectures, claim
from mathema.conjecture import InvalidConjecture


def sample_std(xs: np.ndarray):
    return float(np.std(xs, ddof=1))


def population_var(xs: pd.Series):
    return float(xs.var(ddof=0))


def running_total(xs: np.ndarray):
    return np.cumsum(xs)


def running_product(xs: pd.Series):
    return xs.cumprod()


def positions(xs: pd.Series):
    return int(xs.count())


def column_means(A: np.ndarray):
    return A.mean(axis=0)


def column_sample_std(A: np.ndarray):
    return A.std(axis=0, ddof=1)


def _verdict(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="probe")])
    return p


@pytest.mark.parametrize("fn, true, false", [
    (sample_std, "for xs in R^n, assuming count(xs) >= 2, f(xs) ~= std(xs, ddof=1)",
     "for xs in R^n, assuming count(xs) >= 2, f(xs) ~= std(xs)"),
    (sample_std, "for xs in R^n, assuming count(xs) >= 2, "
                 "f(xs) ~= sqrt(var(xs, ddof=1))",
     "for xs in R^n, assuming count(xs) >= 2, f(xs) ~= sqrt(var(xs, ddof=0))"),
    (population_var, "for xs in R^n, f(xs) ~= var(xs)",
     "for xs in R^n, f(xs) ~= var(xs, ddof=1)"),
    (running_total, "for xs in R^n, f(xs) ~= cumsum(xs)",
     "for xs in R^n, f(xs) ~= cumprod(xs)"),
    (running_product, "for xs in [0.5, 2]^n, f(xs) ~= cumprod(xs)",
     "for xs in [0.5, 2]^n, f(xs) ~= cumsum(xs)"),
    (positions, "for xs in R^n, f(xs) == count(xs)",
     "for xs in R^n, f(xs) == count(xs) - 1"),
    (positions, "for xs in R^n \\ {missing}, f(xs) == len(xs)",
     "for xs in R^n \\ {missing}, f(xs) == len(xs) + 1"),
    (running_total, "for xs in R^n, f(xs)[-1] ~= sum(xs)",
     "for xs in R^n, f(xs)[-1] ~= prod(xs)"),
])
def test_each_word_holds_where_true_and_falsifies_its_sibling(fn, true,
                                                              false):
    p = _verdict(fn, true)
    if fn in (sample_std, population_var):
        # true over the reals; the code's float spread overflows to inf
        # at a cancelling pair [1e300, -1e300, ...], a carrier failure
        # that falsifies the computation (rulings of 2026-10-01 and
        # 2026-10-05)
        assert p.verdict == "falsified", (true, p.verdict, p.note)
        assert "1e+300, -1e+300" in p.counterexample and "returned inf" in \
            p.counterexample, p.counterexample
    else:
        assert p.verdict == "holds", (true, p.verdict, p.note, p.counterexample)
    p = _verdict(fn, false)
    assert p.verdict == "falsified", (false, p.verdict, p.note)


@pytest.mark.parametrize("law", [
    "for xs in R^n, f(xs) ~= std(xs, ddof=1)",
    "for xs in R^n, f(xs) ~= sqrt(var(xs, ddof=1))",
])
def test_a_sample_spread_has_no_value_at_length_one(law):
    # R^n holds the one-element vector, where the sample deviation
    # divides by zero: the claim needs `assuming dim(xs) >= 2`
    p = _verdict(sample_std, law)
    assert p.verdict == "falsified", (law, p.verdict, p.note)
    shown = p.counterexample.split("]")[0]
    assert shown.count(",") == 0, p.counterexample


@pytest.mark.parametrize("fn, true, false", [
    (column_means, "for A in R^(m,n), f(A) ~= mean(A, axis=0)",
     "for A in R^(m,n), f(A) ~= mean(A, axis=1)"),
    (column_sample_std, "for A in R^(m,n), assuming dim(A, 0) >= 2, "
                        "f(A) ~= std(A, axis=0, ddof=1)",
     "for A in R^(m,n), assuming dim(A, 0) >= 2, "
     "f(A) ~= std(A, axis=0)"),
])
def test_a_matrix_reduces_along_an_axis(fn, true, false):
    p = _verdict(fn, true)
    assert p.verdict == "holds", (true, p.verdict, p.note, p.counterexample)
    p = _verdict(fn, false)
    assert p.verdict == "falsified", (false, p.verdict, p.note)


def test_the_statistics_words_accept_their_keywords_and_no_others():
    claim("for xs in R^n, f(xs) ~= std(xs, ddof=1)")
    claim("for A in R^(m,n), f(A) ~= var(A, axis=0, ddof=1)")
    claim("for A in R^(m,n), f(A) ~= cumsum(A, axis=1)")
    with pytest.raises(InvalidConjecture, match="ddof=` on std and var"):
        claim("for xs in R^n, f(xs) ~= mean(xs, ddof=1)")
    with pytest.raises(InvalidConjecture, match="keyword arguments"):
        claim("for xs in R^n, f(xs) ~= norm(xs, ord=2)")


def test_len_counts_every_slot_and_the_hole_goes_to_its_policy_line():
    # count reads the value slots and len every slot: over hole-free
    # vectors the two agree, so the value claim holds, and the hole a
    # Series admits is judged by the missing-policy line, which records
    # that f answers with the number of values, dropping the hole
    rec = mathema.check(positions,
                        claims=["for xs in R^n, f(xs) == len(xs)"])
    row = next(p for p in rec.probes if "len(xs)" in (p.statement or ""))
    assert row.verdict == "holds", (row.verdict, row.note)
    assert "drops the nan slot" in (row.note or ""), row.note
