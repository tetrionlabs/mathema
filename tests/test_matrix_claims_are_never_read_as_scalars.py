# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim over vectors or matrices is never decided by reading them as
numbers.

The scalar derive route treats every name as a real number, so a
matrix or vector reaching it becomes one: `(A + B)**2 == A**2 + 2*A*B
+ B**2` reads as the binomial square and `norm(x)*norm(y) ==
norm(x*y)` as `|x||y| == |xy|`, both "proven" for values they say
nothing about. A name declared as a vector or matrix (an `R^n` or
`R^(m,n)` domain, a `Vec`/`Mat` marker, or a vector, matrix or table
runtime type) that the claim uses as a value takes the linear-algebra
path or is declined with its reason. An ordering between a matrix and
anything is not defined, so `A >= 0` is refused.
"""
from __future__ import annotations

import pytest

from mathema.claims import check_conjectures, claim
from mathema.types import Mat, Vec


def ident(A):
    return A


def two_plain(A, B):
    return A


def two(A: Mat("n", "n"), B: Mat("n", "n")):
    return A


def pair(x, y):
    return x


def vec_pair(x: Vec("n"), y: Vec("n")):
    return x


def sum_of_squares(x):
    return float(sum(v * v for v in x))


def _one(fn, law, route):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


_SQUARE = "(A + B)**2 == A**2 + 2*A*B + B**2"


@pytest.mark.parametrize("route", ["derive", "best"])
@pytest.mark.parametrize("fn, law", [
    (two_plain, f"for A in R^(n,n), B in R^(n,n), {_SQUARE}"),
    (two, _SQUARE),
    (pair, "for x in R^n, y in R^n, norm(x)*norm(y) == norm(x*y)"),
    (pair, "for x in R^n, y in R^n, abs(x + y) <= abs(x) + abs(y)"),
    (two_plain, "for A in R^(n,n), B in R^(n,n), A + B == 2*A"),
])
def test_a_matrix_or_vector_claim_is_not_proven_as_scalars(fn, law, route):
    p = _one(fn, law, route)
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch)


@pytest.mark.parametrize("route", ["derive", "best"])
def test_the_false_product_of_norms_is_not_proven(route):
    pytest.importorskip("numpy")
    # |x||y| == |x*y| is a scalar identity; with x*y the elementwise
    # product of two vectors it is false
    p = _one(vec_pair, "norm(x)*norm(y) == norm(x*y)", route)
    assert p.verdict != "proven", (p.verdict, p.sketch)
    if route == "best":
        assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_matrix_binomial_square_falsifies_with_a_witness():
    pytest.importorskip("numpy")
    p = _one(two_plain, "for A in R^(n,n), B in R^(n,n), "
                        "(A + B) @ (A + B) == A @ A + 2 * A @ B + B @ B",
             "best")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample


@pytest.mark.parametrize("route", ["derive", "best", "probe"])
@pytest.mark.parametrize("law", [
    "for A in R^(n,n), A*A >= 0",
    "for A in R^(n,n), A >= 0",
    "for A in R^(n,n), 0 <= A @ A.T",
])
def test_an_ordering_on_a_matrix_is_refused(law, route):
    p = _one(ident, law, route)
    assert p.verdict == "skipped:misspecified", (p.verdict, p.note)
    assert "ordering" in p.note and "all(" in p.note, p.note


def test_a_scalar_ordering_on_a_matrix_claim_still_adjudicates():
    # det and trace are numbers, so their ordering is an ordinary claim,
    # decided here by the lemma that a Gram product is semidefinite
    p = _one(ident, "for A in R^(n,n), det(A @ A.T) >= 0", "best")
    assert p.verdict == "proven", (p.verdict, p.note, p.counterexample)
    assert p.route == "derive"


def test_a_vector_passed_only_to_f_keeps_the_sequence_proof():
    # the sequence route models x element by element, so it may decide
    # a claim that only hands x to f
    p = _one(sum_of_squares, "for x in R^n, f(x) >= 0", "derive")
    assert p.verdict == "proven", (p.verdict, p.note)
