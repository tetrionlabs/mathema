# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The lexicon's example functions over numpy vectors and matrices.

Each is a function a working programmer would recognise (a length, a
distance, a normalisation, a stopping criterion, a nearest neighbour,
portfolio weights, a tracking error, a root mean square error, a Gram
trace), paired in `EXAMPLE_FUNCTIONS` with the lexicon rows it
demonstrates. numpy is imported at the top, so the derive route reads
each body through the numpy definition rows; `mathema.lexicon` imports
this module only when numpy is installed, and without it these rows
stay text.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import pandas


def euclidean_length(x: np.ndarray) -> float:
    """The Euclidean length of a vector, `||x||`, which is also
    `||x||_2`; it lies between `||x||_inf` and `||x||_1` and scales
    with the magnitude of a factor ("norm_bars_euclidean",
    "norm_bars_two", "norm_bars_chain", "norm_bars_homogeneous",
    "norm_bars_homogeneous_sign_trap")."""
    return float(np.linalg.norm(x))


def manhattan_length(x: np.ndarray) -> float:
    """The sum of the magnitudes of a vector's entries, `||x||_1`
    ("norm_bars_one"). Claimed as `||x||_2` or as `||x||^2` it is
    falsified with a witness ("norm_bars_order_trap",
    "norm_bars_squared_trap")."""
    return float(np.sum(np.abs(x)))


def largest_magnitude(x: np.ndarray) -> float:
    """The largest magnitude among a vector's entries, `||x||_inf`
    ("norm_bars_inf")."""
    return float(np.max(np.abs(x)))


def p_norm(x: np.ndarray, p: int) -> float:
    """The p-norm of a vector for a whole number `p`, `||x||_p`
    ("norm_bars_integer_order")."""
    return float(np.sum(np.abs(x) ** p) ** (1.0 / p))


def unit_vector(x: np.ndarray) -> np.ndarray:
    """A vector scaled to unit length, pointing along its argument. It
    divides by zero at the zero vector, which the premise `||x|| > 0`
    excludes ("norm_bars_unit_vector", "norm_bars_direction")."""
    return x / np.linalg.norm(x)


def distance(x: np.ndarray, y: np.ndarray) -> float:
    """The Euclidean distance between two vectors, `||x - y||`:
    symmetric, and at most the sum of the two lengths
    ("norm_bars_distance", "norm_bars_distance_symmetric",
    "norm_bars_triangle")."""
    return float(np.linalg.norm(x - y))


def converged(x_new: np.ndarray, x_old: np.ndarray, tol: float) -> bool:
    """A stopping criterion: the step from `x_old` to `x_new` is within
    `tol` in Euclidean length ("norm_bars_stopping_criterion")."""
    return bool(np.linalg.norm(x_new - x_old) <= tol)


def nearest_distance(points: np.ndarray, q: np.ndarray) -> float:
    """The distance from `q` to the nearest row of `points`, which is
    no farther than the first row ("norm_bars_nearest_distance",
    "norm_bars_nearest_distance_trap")."""
    return float(np.min(np.linalg.norm(points - q, axis=1)))


def tracking_error(port: "pandas.Series", bench: "pandas.Series") -> float:
    """The tracking error of a portfolio's returns against a benchmark's,
    the Euclidean length of their difference over two pandas Series
    ("norm_bars_series_tracking_error")."""
    return float(np.linalg.norm(port - bench))


def rmse(pred: np.ndarray, actual: np.ndarray) -> float:
    """The root mean square error of predictions against actual values
    ("norm_bars_rmse")."""
    return float(np.linalg.norm(pred - actual) / np.sqrt(len(pred)))


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


def max_column_sum(A: np.ndarray) -> float:
    """The largest column sum of magnitudes, numpy's `ord=1` matrix
    norm, `||A||_1` ("matrix_norm_bars_one"). Claimed as `||A||_inf` it
    is falsified with a witness ("matrix_norm_bars_order_trap")."""
    return float(np.max(np.sum(np.abs(A), axis=0)))


def max_row_sum(A: np.ndarray) -> float:
    """The largest row sum of magnitudes, numpy's `ord=inf` matrix norm,
    `||A||_inf` ("matrix_norm_bars_inf")."""
    return float(np.max(np.sum(np.abs(A), axis=1)))


def largest_singular_value(A: np.ndarray) -> float:
    """The largest singular value of a matrix, its spectral norm
    `||A||_2`, never above its Frobenius norm `||A||`
    ("matrix_norm_bars_spectral",
    "matrix_norm_bars_spectral_below_frobenius")."""
    return float(np.linalg.svd(A, compute_uv=False)[0])


#: the lexicon rows each function demonstrates, in the shape of
#: `mathema.lexicon.EXAMPLE_FUNCTIONS`
def simulated_return(mu: float, rng: np.random.Generator) -> float:
    """One simulated return around a mean, drawn from the generator the
    caller passes in, what "state_safe_passed_generator" and
    "reproducible_passed_generator" demonstrate."""
    return mu + 0.01 * rng.standard_normal()


EXAMPLE_FUNCTIONS: dict[str, tuple[object, list[str]]] = {
    "simulated_return": (simulated_return, ["state_safe_passed_generator",
                                            "reproducible_passed_generator"]),
    "euclidean_length": (euclidean_length, [
        "norm_bars_euclidean", "norm_bars_two", "norm_bars_chain",
        "norm_bars_homogeneous", "norm_bars_homogeneous_sign_trap",
    ]),
    "manhattan_length": (manhattan_length, [
        "norm_bars_one", "norm_bars_order_trap", "norm_bars_squared_trap",
    ]),
    "largest_magnitude": (largest_magnitude, ["norm_bars_inf"]),
    "p_norm": (p_norm, ["norm_bars_integer_order"]),
    "unit_vector": (unit_vector, ["norm_bars_unit_vector",
                                  "norm_bars_direction"]),
    "distance": (distance, ["norm_bars_distance",
                            "norm_bars_distance_symmetric",
                            "norm_bars_triangle"]),
    "converged": (converged, ["norm_bars_stopping_criterion"]),
    "nearest_distance": (nearest_distance, [
        "norm_bars_nearest_distance", "norm_bars_nearest_distance_trap",
    ]),
    "tracking_error": (tracking_error, ["norm_bars_series_tracking_error"]),
    "rmse": (rmse, ["norm_bars_rmse"]),
    "portfolio_weights": (portfolio_weights, ["norm_bars_portfolio_weights"]),
    "squared_length": (squared_length, ["norm_bars_squared"]),
    "frobenius_norm": (frobenius_norm, ["matrix_norm_bars_frobenius"]),
    "gram_trace": (gram_trace, ["matrix_norm_bars_gram_trace"]),
    "max_column_sum": (max_column_sum, ["matrix_norm_bars_one",
                                        "matrix_norm_bars_order_trap"]),
    "max_row_sum": (max_row_sum, ["matrix_norm_bars_inf"]),
    "largest_singular_value": (largest_singular_value, [
        "matrix_norm_bars_spectral",
        "matrix_norm_bars_spectral_below_frobenius",
    ]),
}
