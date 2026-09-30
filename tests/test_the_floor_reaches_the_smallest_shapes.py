# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`^n` holds n = 1, so every claim over vectors or matrices meets the
smallest shapes its binding admits before any random draw: vectors that
share a length all at length 1 together, and a 1 by 1 matrix."""
import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")


def second_plus(xs: np.ndarray, ys: np.ndarray) -> float:
    return float(xs[1] + ys[0])


def coupling(A: np.ndarray) -> float:
    return float(A[0, 1])


def _row(fn, text):
    (row,) = [r for r in check_conjectures(fn, [claim(text, name="c")]) if r.name == "c"]
    return row


def test_vectors_sharing_a_length_meet_length_one_together():
    row = _row(second_plus, "for xs in [0, 1]^n, ys in [0, 1]^n, f(xs, ys) >= 0")
    assert row.verdict == "falsified"
    xs, ys = row.meta["mathema.counterexample_args"]
    assert (len(xs), len(ys)) == (1, 1)
    assert "raised IndexError" in row.counterexample


def test_a_square_matrix_meets_one_by_one():
    row = _row(coupling, "for A in [0, 1]^(n,n), f(A) >= 0")
    assert row.verdict == "falsified"
    (A,) = row.meta["mathema.counterexample_args"]
    assert np.shape(A) == (1, 1)
    assert "raised IndexError" in row.counterexample
