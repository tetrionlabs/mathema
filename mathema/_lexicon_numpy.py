# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The lexicon's example functions over numpy vectors and matrices.

Each is a function a working programmer would recognise (a length, a
distance, a normalisation, portfolio weights, a Gram trace), paired in
`EXAMPLE_FUNCTIONS` with the lexicon rows it demonstrates. numpy is
imported at the top, so the derive route reads each body through the
numpy definition rows; `mathema.lexicon` imports this module only when
numpy is installed, and without it these rows stay text.
"""
from __future__ import annotations

import numpy as np


def euclidean_length(x: np.ndarray) -> float:
    """The Euclidean length of a vector, `||x||`, which is also
    `||x||_2`; it lies between `||x||_inf` and `||x||_1` and scales
    with its argument ("norm_bars_euclidean", "norm_bars_two",
    "norm_bars_chain", "norm_bars_homogeneous")."""
    return float(np.linalg.norm(x))


def manhattan_length(x: np.ndarray) -> float:
    """The sum of the magnitudes of a vector's entries, `||x||_1`
    ("norm_bars_one"). Claimed as `||x||_2` it is falsified with a
    witness ("norm_bars_order_trap")."""
    return float(np.sum(np.abs(x)))


def largest_magnitude(x: np.ndarray) -> float:
    """The largest magnitude among a vector's entries, `||x||_inf`
    ("norm_bars_inf")."""
    return float(np.max(np.abs(x)))


def unit_vector(x: np.ndarray) -> np.ndarray:
    """A vector scaled to unit length. It divides by zero at the zero
    vector, which the premise `||x|| > 0` excludes
    ("norm_bars_unit_vector")."""
    return x / np.linalg.norm(x)


def distance(x: np.ndarray, y: np.ndarray) -> float:
    """The Euclidean distance between two vectors, `||x - y||`:
    symmetric, zero between a vector and itself, and at most the sum
    of the two lengths ("norm_bars_distance",
    "norm_bars_distance_symmetric", "norm_bars_distance_zero",
    "norm_bars_triangle")."""
    return float(np.linalg.norm(x - y))


def portfolio_weights(scores: np.ndarray) -> np.ndarray:
    """Long-only portfolio weights from positive scores: each score's
    share of the total, so the weights sum to one and their L1 norm is
    one ("norm_bars_portfolio_weights")."""
    return scores / np.sum(scores)


def squared_length(x: np.ndarray) -> float:
    """A vector's squared length, `dot(x, x)`, which is `||x||^2`, the
    square of the norm ("norm_bars_squared")."""
    return float(np.dot(x, x))


def frobenius_norm(A: np.ndarray) -> float:
    """The Frobenius norm of a matrix, the square root of the trace of
    `A.T @ A` (the sum of its squared entries), which is `||A||`
    ("matrix_norm_bars_frobenius")."""
    return float(np.sqrt(np.trace(A.T @ A)))


def gram_trace(A: np.ndarray) -> float:
    """The trace of the Gram matrix `A @ A.T`, which is the squared
    Frobenius norm of `A` ("matrix_norm_bars_gram_trace")."""
    return float(np.trace(A @ A.T))


def largest_singular_value(A: np.ndarray) -> float:
    """The largest singular value of a matrix, its spectral norm
    `||A||_2`, never above its Frobenius norm `||A||`
    ("matrix_norm_bars_spectral",
    "matrix_norm_bars_spectral_below_frobenius")."""
    return float(np.linalg.svd(A, compute_uv=False)[0])


#: the lexicon rows each function demonstrates, in the shape of
#: `mathema.lexicon.EXAMPLE_FUNCTIONS`
EXAMPLE_FUNCTIONS: dict[str, tuple[object, list[str]]] = {
    "euclidean_length": (euclidean_length, [
        "norm_bars_euclidean", "norm_bars_two", "norm_bars_chain",
        "norm_bars_homogeneous",
    ]),
    "manhattan_length": (manhattan_length, ["norm_bars_one",
                                            "norm_bars_order_trap"]),
    "largest_magnitude": (largest_magnitude, ["norm_bars_inf"]),
    "unit_vector": (unit_vector, ["norm_bars_unit_vector"]),
    "distance": (distance, ["norm_bars_distance",
                            "norm_bars_distance_symmetric",
                            "norm_bars_distance_zero", "norm_bars_triangle"]),
    "portfolio_weights": (portfolio_weights, ["norm_bars_portfolio_weights"]),
    "squared_length": (squared_length, ["norm_bars_squared"]),
    "frobenius_norm": (frobenius_norm, ["matrix_norm_bars_frobenius"]),
    "gram_trace": (gram_trace, ["matrix_norm_bars_gram_trace"]),
    "largest_singular_value": (largest_singular_value, [
        "matrix_norm_bars_spectral",
        "matrix_norm_bars_spectral_below_frobenius",
    ]),
}
