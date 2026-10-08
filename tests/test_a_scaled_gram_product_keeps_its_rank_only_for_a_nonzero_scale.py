# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""For a real matrix `A`, `rank(A @ A.T) == rank(A)`, and scaling by a
nonzero number keeps a rank. Scaling by a number that can be zero does
not: `rank(t * (A @ A.T))` is 0 at `t = 0`, whatever `A` is. So the
Gram rank lemma reads `c * (A @ A.T)` as `rank(A)` only for a nonzero
number `c`.
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from mathema.claims import check_conjectures, claim  # noqa: E402
from mathema.types import Mat  # noqa: E402


def scaled(A: Mat("m", "n"), t: float):
    return A


def scaled_gram_rank(A: np.ndarray, t: float) -> int:
    return np.linalg.matrix_rank(t * (A @ A.T))


def _one(fn, law, route="derive"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def test_a_scale_that_can_be_zero_does_not_keep_the_rank():
    p = _one(scaled, "for t in [-1, 1], rank(t * (A @ A.T)) == rank(A)")
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_through_numpy_the_scaled_gram_rank_is_falsified():
    law = "for A in R^(m,n), t in [-1, 1], f(A, t) == rank(A)"
    assert _one(scaled_gram_rank, law).verdict != "proven"
    p = _one(scaled_gram_rank, law, "best")
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
def test_a_nonzero_number_keeps_the_rank():
    p = _one(scaled, "rank(-2 * (A @ A.T)) == rank(A)")
    assert p.verdict == "proven", (p.verdict, p.sketch)
