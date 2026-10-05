# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""numpy's `.T` on a 1-D array returns the array unchanged, so for a
vector `x`, `x @ x.T` is the inner product `x . x`, a number, and
`A + x @ x.T` adds that number to every entry of `A`. The matrix
algebra reads a vector the way numpy does: `A + x @ x.T` is not
`A + outer(x, x)` (at `A = 0`, `x = [1, 2]` numpy gives a matrix of
fives), and `x.T @ A @ x` is still the quadratic form.
"""
from __future__ import annotations

import numpy as np
import pytest

from mathema.claims import check_conjectures, claim
from mathema.types import Mat, Vec


def rank_one_update(A: np.ndarray, x: np.ndarray) -> np.ndarray:
    return A + x @ x.T


def form(A: Mat("n", "n"), x: Vec("n")):
    return A


def _one(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def test_a_vector_times_its_transpose_is_not_the_outer_product():
    law = "for A in R^(n,n), x in R^n, f(A, x) == A + outer(x, x)"
    assert _one(rank_one_update, law, "derive").verdict != "proven"
    p = _one(rank_one_update, law)
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
def test_in_claim_text_a_vector_times_its_transpose_is_its_inner_product():
    p = _one(form, "x @ x.T == dot(x, x)", "derive")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    p = _one(form, "x @ x.T == outer(x, x)", "derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)


@pytest.mark.needs_full_proof_budget
def test_a_quadratic_form_still_reads_through_the_transpose():
    def form(A: np.ndarray, x: np.ndarray) -> float:
        return x.T @ A @ x
    p = _one(form, "for A in R^(n,n), x in R^n, f(A, x) == x @ A @ x",
             "derive")
    assert p.verdict == "proven", (p.verdict, p.sketch)
