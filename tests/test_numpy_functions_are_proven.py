# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Claims about small numpy functions, decided through numpy's rows.

`np.linalg.norm(x)` reads through `numpy.linalg.norm`'s definition row
as `sqrt(sum(x ** 2))`, so `f(x) >= 0` and `f(c * x) == c * f(x)` are
proven for every length; `np.negative`, `np.square`, `np.maximum` and
the nan-ignoring reductions read the same way. Each proof stands
beside a false sibling that does not prove and, sampled, is falsified.

Some claims here are pinned at `holds`: the probe finds no
counterexample, and the derive route does not read the call (numpy's
`abs` and `clip` state no definition row; an index into a vector and
a definition row over a matrix and a vector together are outside
it). Each is marked with the row that
carries it or the row it lacks.
"""
from __future__ import annotations

import numpy as np
import pytest

from mathema.claims import check_conjectures, claim

#: numpy's ufuncs, `matmul` and `sum` state signatures a row binds to
#: from numpy 2.4 on, and the rows for them apply from there
_FROM_2_4 = pytest.mark.skipif(
    tuple(int(p) for p in np.__version__.split(".")[:2]) < (2, 4),
    reason="the rows for this function apply from numpy 2.4")


def solve_for(A: np.ndarray, b: np.ndarray):
    return np.linalg.solve(A, b)


def norm_of(x: np.ndarray):
    return np.linalg.norm(x)


def l1_norm(x: np.ndarray):
    return np.linalg.norm(x, 1)


def clipped(x: np.ndarray):
    return np.clip(x, 0.0, 1.0)


def magnitudes(x: np.ndarray):
    return np.abs(x)


def absolutes(x: np.ndarray):
    return np.absolute(x)


def negated(x: np.ndarray):
    return np.negative(x)


def squared(x: np.ndarray):
    return np.square(x)


def larger(x: np.ndarray, y: np.ndarray):
    return np.maximum(x, y)


def spread(x: np.ndarray, y: np.ndarray):
    return np.maximum(x, y) - np.minimum(x, y)


def running(x: np.ndarray):
    return np.cumsum(x)


def total_np(x: np.ndarray):
    return np.sum(x)


def nan_total(x: np.ndarray):
    return np.nansum(x)


def nan_volatility(x: np.ndarray):
    return np.nanstd(x, ddof=1)


def mean_np(x: np.ndarray):
    return np.mean(x)


def spread_of_prices(x: np.ndarray):
    return x.var()


def gram(A: np.ndarray):
    return np.matmul(A, A.T)


def _one(fn, law, route="best", extensive=False):
    (p,) = check_conjectures(fn, [claim(law, route=route)],
                             extensive=extensive)
    return p


def _rows_used(p) -> list:
    return [f"{u['key']} {u['row']}"
            for u in (p.meta or {}).get("mathema.definitions", [])]


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, law, rows", [
    (norm_of, "for x in R^n, f(x) >= 0",
     ["numpy.linalg.norm definition"]),
    (norm_of, "for x in R^n, let c be [0, 10], f(c * x) == c * f(x)",
     ["numpy.linalg.norm definition"]),
    (l1_norm, "for x in R^n, f(-x) == f(x)",
     ["numpy.linalg.norm definition@ord=1"]),
    pytest.param(absolutes, "for x in R^n, f(-x) == f(x)",
                 ["numpy.absolute definition"], marks=_FROM_2_4),
    pytest.param(negated, "for x in R^n, f(f(x)) == x",
                 ["numpy.negative definition"], marks=_FROM_2_4),
    pytest.param(squared, "for x in R^n, f(-x) == f(x)",
                 ["numpy.square definition"], marks=_FROM_2_4),
    pytest.param(larger, "for x in R^n, y in R^n, f(x, y) ~= f(y, x)",
                 ["numpy.maximum definition"], marks=_FROM_2_4),
    pytest.param(spread, "for x in R^n, y in R^n, f(x, y) ~= abs(x - y)",
                 ["numpy.maximum definition", "numpy.minimum definition"],
                 marks=_FROM_2_4),
    (mean_np, "for x in R^n, min(x) <= f(x) <= max(x)",
     ["numpy.mean definition"]),
    pytest.param(total_np, "for x in R^n, f(x) == sum(x)",
                 ["numpy.sum definition"], marks=_FROM_2_4),
    (nan_total, "for x in R^n, f(x) == sum(x)", ["numpy.nansum definition"]),
    (nan_volatility, "for x in R^n, let s = mathema.f.shift_seq, "
                     "let c be [0.1, 10], assuming dim(x) >= 2, "
                     "f(s(x, c)) ~= f(x)",
     ["numpy.nanstd definition@ddof=1"]),
    (spread_of_prices, "for x in R^n, let s = mathema.f.shift_seq, "
                       "let c be [0.1, 10], f(s(x, c)) ~= f(x)",
     ["numpy.ndarray.var definition"]),
    pytest.param(gram, "for A in R^(n,n), f(A).T == f(A)",
                 ["numpy.ndarray.T definition", "numpy.matmul definition"],
                 marks=_FROM_2_4),
])
def test_proven_through_numpy_rows(fn, law, rows):
    p = _one(fn, law)
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
    assert _rows_used(p) == rows
    used = p.meta["mathema.definitions"]
    assert all(u["status"] == "bundled" for u in used), used
    assert all(u["source"].startswith("mathema/compendium/numpy/")
               for u in used), used


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, law", [
    (absolutes, "for x in R^n, f(x) == x"),
    (magnitudes, "for x in R^n, f(x) == x"),
    (negated, "for x in R^n, f(x) == x"),
    (squared, "for x in R^n, f(-x) == -f(x)"),
    (larger, "for x in R^n, y in R^n, f(x, y) ~= x"),
    (gram, "for A in R^(n,n), f(A) == A"),
    (solve_for, "for A in R^(n,n), b in R^n, assuming det(A) != 0, "
                "f(A, b) == b"),
])
def test_a_false_sibling_is_falsified(fn, law):
    p = _one(fn, law, route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    p = _one(fn, law, extensive=True)
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
def test_solve_holds_and_its_row_is_stated_over_a_matrix_and_a_vector():
    law = ("for A in R^(n,n), b in R^n, assuming det(A) != 0, "
           "A @ f(A, b) == b")
    p = _one(fn=solve_for, law=law)
    # numpy.linalg.solve definition carries this on derive once the
    # matrix route reads a row with a vector parameter
    assert (p.verdict, p.route) == ("holds", "probe"), (p.verdict, p.note)
    p = _one(solve_for, law, route="derive")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "numpy.linalg.solve definition is stated over vectors" in p.note


@pytest.mark.needs_full_proof_budget
def test_a_norm_is_not_positive_at_the_zero_vector():
    law = "for x in R^n, f(x) > 0"
    p = _one(norm_of, law, route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
    # false at x = [0.0, ...], the zero vector every claim over R^n meets
    p = _one(norm_of, law, extensive=True)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "[0, 0" in p.counterexample, p.counterexample


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, law, why", [
    # numpy.clip states no definition row
    (clipped, "for x in R^n, 0 <= f(x) <= 1", "every link"),
    # numpy.abs states no definition row
    (magnitudes, "for x in R^n, f(x) >= 0", "underivable"),
    (magnitudes, "for x in R^n, f(-x) == f(x)", "underivable"),
    # numpy.cumsum definition carries this once an index into a vector
    # lowers
    (running, "for x in R^n, f(x)[dim(x) - 1] == sum(x)",
     "only the reversal"),
])
def test_held_on_the_probe_until_the_derive_route_reads_the_row(fn, law,
                                                                  why):
    p = _one(fn, law)
    assert (p.verdict, p.route) == ("holds", "probe"), (p.verdict, p.note)
    assert why in p.note, p.note
