# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`numpy.linalg.matrix_rank` counts the singular values above a
tolerance (`S.max() * max(M, N) * eps`), so it is not the rank of the
matrix: `A = diag(1, 1e-9)` has rank 2, and `A @ A.T = diag(1, 1e-18)`
has rank 2 too, but numpy's `matrix_rank(A @ A.T)` is 1. The bundled
row says only what holds of every real matrix, `matrix_rank(A) <=
rank(A)`, and the derive route does not read `matrix_rank` as `rank`.
`numpy.linalg.pinv` reads a singular value at most `1e-15` times the
largest as zero, so its rows are stated where every singular value is
above that cutoff.
"""
from __future__ import annotations

import os

import numpy as np
import yaml

from mathema.claims import check_conjectures, claim
from mathema.compendium import _bundled_dir


def gram_rank(A: np.ndarray) -> int:
    return np.linalg.matrix_rank(A @ A.T)


def _rows(key: str) -> dict:
    with open(os.path.join(_bundled_dir(), "numpy",
                           "linalg.claims.yaml")) as fh:
        entry = yaml.safe_load(fh)[key]
    return {r["name"]: r["statement"] for r in entry["claims"]}


def test_numpy_disagrees_with_the_rank_at_a_small_singular_value():
    A = np.diag([1.0, 1e-9])
    assert gram_rank(A) == 1
    assert np.linalg.matrix_rank(A) == 2


def test_the_gram_rank_through_numpy_is_not_proven():
    (p,) = check_conjectures(gram_rank, [claim(
        "for A in R^(m,n), f(A) == rank(A)", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_matrix_rank_has_no_definition_row():
    rows = _rows("numpy.linalg.matrix_rank")
    assert "definition" not in rows, rows
    assert rows == {"at_most_rank": "for A in R^(m,n), f(A) <= rank(A)"}


def test_the_pinv_rows_are_stated_above_the_cutoff():
    rows = _rows("numpy.linalg.pinv")
    assert "assuming cond(a) < 1e15" in rows["definition"], rows
    assert "assuming cond(a) < 1e15" in rows["inverse_when_nonsingular"], \
        rows
