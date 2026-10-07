# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A random square matrix has a nonzero trace and is invertible with
probability one, so a claim false only where the trace vanishes or the
matrix is singular needs those matrices drawn on purpose, as the zero
matrix and length 1 already are."""

import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.matrices import rank_edge  # noqa: E402


def normalized(A: np.ndarray) -> np.ndarray:
    return A / np.trace(A)


def inverse_det(A: np.ndarray) -> float:
    return 1.0 / np.linalg.det(A)


_PREMISE = "for A in R^(n,n), assuming n >= 2 and max(abs(A)) >= 1, "


def test_a_trace_zero_matrix_is_drawn():
    (p,) = check_conjectures(normalized, [claim(
        _PREMISE + "trace(f(A)) ~= 1", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_singular_matrix_is_drawn():
    (p,) = check_conjectures(inverse_det, [claim(
        _PREMISE + "f(A) * det(A) ~= 1", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_edges_include_a_trace_zero_draw():
    m = [[1.0, 2.0], [3.0, 4.0]]
    traces = {sum(rank_edge(m, d)[i][i] for i in range(2)) for d in range(40)}
    assert 0.0 in traces
