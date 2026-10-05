# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The first tranche of linear-algebra words, each with a true
identity and a false sibling.

`dot`, `outer`, `kron`, `diag`, `rank`, `eigvals`, `eigvalsh`, `cond`,
`solve`, `pinv`, quadratic forms `x.T @ A @ x` (a number), row and
column slices `A[i, :]` and `A[:, j]`, and axis reductions
`sum(A, axis=0)` and `mean(A, axis=1)`. The probe evaluates every
word; the derive route proves the identities sympy's matrix algebra
reaches (`dot`, `outer`, `kron`, `solve`). A decomposition is a claim
about its factors, spelled by binding the numpy function with `let`.
"""
from __future__ import annotations

import pytest

from mathema.claims import check_conjectures, claim
from mathema.types import Mat, Vec


def one(A: Mat("n", "n")):
    return A


def two(A: Mat("n", "n"), B: Mat("n", "n")):
    return A


def vecs(x: Vec("n"), y: Vec("n")):
    return x


def form(A: Mat("n", "n"), x: Vec("n")):
    return A


def column_form(A: Mat("n", "n"), x: Mat("n", 1)):
    return A


def vec(v: Vec("n")):
    return v


def _one(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def _holds(p):
    return p.verdict in ("proven", "holds")


_WORDS = [
    (vecs, "dot(x, y) == dot(y, x)", "dot(x, y) == dot(x, x)"),
    (vecs, "dot(x, x) == norm(x)**2", "dot(x, y) == norm(x)*norm(y)"),
    (vecs, "outer(x, y).T == outer(y, x)", "outer(x, y) == outer(y, x)"),
    (vecs, "trace(outer(x, y)) ~= dot(x, y)",
     "trace(outer(x, y)) ~= dot(x, x)"),
    (two, "kron(A, B).T == kron(A.T, B.T)", "kron(A, B) == kron(B, A)"),
    (two, "trace(kron(A, B)) ~= trace(A) * trace(B)",
     "trace(kron(A, B)) ~= trace(A) + trace(B)"),
    (one, "sum(diag(A)) ~= trace(A)", "sum(diag(A)) ~= sum(A)"),
    (vec, "diag(diag(v)) == v", "diag(diag(v)) == 2*v"),
    (one, "rank(A.T) == rank(A)", "rank(A) < n"),
    (one, "trace(A) ~= sum(eigvals(A))", "trace(A) ~= prod(eigvals(A))"),
    (one, "det(A) ~= prod(eigvals(A))", "det(A) ~= sum(eigvals(A))"),
    (one, "assuming A is symmetric, sum(eigvalsh(A)) ~= trace(A)",
     "assuming A is symmetric, sum(eigvalsh(A)) ~= det(A)"),
    (one, "assuming A is positive definite, min(eigvalsh(A)) > 0",
     "assuming A is symmetric, min(eigvalsh(A)) > 0"),
    (one, "cond(A) >= 1", "cond(A) <= 1"),
    (one, "assuming det(A) != 0, cond(A) ~= norm(A, 2) * norm(inv(A), 2)",
     "assuming det(A) != 0, cond(A) ~= norm(A) * norm(inv(A))"),
    (one, "let b be R^n, assuming det(A) != 0, A @ solve(A, b) ~= b",
     "let b be R^n, assuming det(A) != 0, solve(A, b) ~= A @ b"),
    (one, "A @ pinv(A) @ A ~= A", "pinv(A) @ A @ A ~= A"),
    (form, "assuming A is positive definite, assuming x != 0, "
           "x.T @ A @ x > 0",
     "assuming A is symmetric, assuming x != 0, x.T @ A @ x > 0"),
    (form, "x.T @ (A + A.T) @ x ~= 2 * (x.T @ A @ x)",
     "x.T @ (A + A.T) @ x ~= x.T @ A @ x"),
    (column_form, "assuming A is positive definite, x.T @ A @ x >= 0",
     "x.T @ A @ x >= 0"),
    (one, "A[0, :] == A.T[:, 0]", "A[0, :] == A[:, 0]"),
    (one, "sum(A, axis=0) ~= sum(A.T, axis=1)",
     "sum(A, axis=0) ~= sum(A, axis=1)"),
    (one, "mean(A, axis=1) ~= sum(A, axis=1) / n",
     "mean(A, axis=1) ~= sum(A, axis=0) / n"),
]


#: true identities the probe route meets at a magnitude corner
_AT_A_CORNER = {
    ("x.T @ (A + A.T) @ x ~= 2 * (x.T @ A @ x)", "probe"): "falsified",
}


@pytest.mark.parametrize("route", ["probe", "best"])
@pytest.mark.parametrize("fn, true, false", _WORDS)
def test_each_word_has_a_true_identity_and_a_false_sibling(fn, true, false,
                                                           route):
    p = _one(fn, true, route)
    expected = _AT_A_CORNER.get((true, route))
    if expected == "falsified":
        # true over the reals, broken by the float computation at a
        # magnitude corner (rulings of 2026-10-01 and 2026-10-05)
        assert p.verdict == "falsified", (true, p.verdict, p.note)
        assert "e+300" in p.counterexample or "e+16" in p.counterexample, p.counterexample
    else:
        assert _holds(p), (true, p.verdict, p.note, p.counterexample)
    p = _one(fn, false, route)
    assert p.verdict == "falsified", (false, p.verdict, p.note)


@pytest.mark.parametrize("fn, law", [
    (vecs, "dot(x, y) == dot(y, x)"),
    (vecs, "outer(x, y).T == outer(y, x)"),
    (two, "kron(A, B).T == kron(A.T, B.T)"),
    (one, "let b be R^n, assuming det(A) != 0, A @ solve(A, b) == b"),
    (form, "x.T @ A.T @ x == x.T @ A @ x"),
])
def test_the_derive_route_proves_what_the_matrix_algebra_reaches(fn, law):
    p = _one(fn, law, "derive")
    assert p.verdict == "proven", (law, p.verdict, p.note, p.sketch)


@pytest.mark.parametrize("fn, law", [
    (vecs, "dot(x, y) == dot(x, x)"),
    (vecs, "outer(x, y) == outer(y, x)"),
    (two, "kron(A, B) == kron(B, A)"),
    (one, "let b be R^n, assuming det(A) != 0, solve(A, b) == A @ b"),
    (one, "let b be R^n, A @ solve(A, b) == b"),
])
def test_the_derive_route_does_not_prove_the_false_siblings(fn, law):
    p = _one(fn, law, "derive")
    assert p.verdict != "proven", (law, p.verdict, p.sketch)


_DECOMPOSITIONS = [
    ("let q = numpy.linalg.qr, q(A)[0].T @ q(A)[0] ~= I(n)",
     "let q = numpy.linalg.qr, q(A)[0] ~= I(n)"),
    ("let q = numpy.linalg.qr, q(A)[0] @ q(A)[1] ~= A",
     "let q = numpy.linalg.qr, q(A)[1] @ q(A)[0] ~= A"),
    ("let ch = numpy.linalg.cholesky, assuming A is positive definite, "
     "ch(A) @ ch(A).T ~= A",
     "let ch = numpy.linalg.cholesky, assuming A is positive definite, "
     "ch(A).T @ ch(A) ~= A"),
    ("let s = numpy.linalg.svd, s(A)[0] @ diag(s(A)[1]) @ s(A)[2] ~= A",
     "let s = numpy.linalg.svd, s(A)[0] @ diag(s(A)[1]) ~= A"),
]


@pytest.mark.parametrize("true, false", _DECOMPOSITIONS)
def test_a_decomposition_is_a_claim_about_its_factors(true, false):
    p = _one(one, true)
    assert _holds(p), (true, p.verdict, p.note, p.counterexample)
    p = _one(one, false)
    assert p.verdict == "falsified", (false, p.verdict, p.note)
