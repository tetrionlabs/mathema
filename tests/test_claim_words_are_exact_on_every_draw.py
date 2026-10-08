# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every word on a claim's side is computed exactly at a draw and
rounded once, as `@` and the reductions are: elementwise `+ - * **`
between arrays, `outer`, `kron`, and the words the probe alone
evaluates (`rank`, `eigvals`, `eigvalsh`, `cond`, `pinv`, a matrix's
2-norm). A value beyond float range stays exact. Where an exact value
is irrational it is certified to more digits than a float holds; a
value that cannot be certified leaves the point undecided rather than
decided on a float. Each case is a corner where numpy's float result
is wrong: a cancellation near 1e16, an overflow near 1e300, a matrix
LAPACK reads as singular or misreads."""
from fractions import Fraction

import pytest

np = pytest.importorskip("numpy")
mpmath = pytest.importorskip("mpmath")
sympy = pytest.importorskip("sympy")

from mathema._linalg_eval import FUNCTIONS, as_array  # noqa: E402
from mathema._math_vocab import MATH_CONSTANTS  # noqa: E402
from mathema.conjecture import _SAFE_FUNCS, _validate  # noqa: E402

ENV = {**_SAFE_FUNCS, **FUNCTIONS, **MATH_CONSTANTS}


def evaluate(src: str, **values):
    """`src` compiled and evaluated as a claim side is at one draw."""
    code, _ = _validate(src, set(values))
    return eval(code, {**ENV, **{k: as_array(v) for k, v in values.items()}})  # noqa: S307


def entries(value) -> list:
    return list(np.asarray(value, dtype=object).ravel())


def exactly(value) -> list:
    """Each entry as the exact rational it holds."""
    return [Fraction(v) for v in entries(value)]


BIG = 1e300


@pytest.mark.parametrize("src, values, want", [
    ("x + y", {"x": [1e308, 1.0], "y": [1e308, 2.0]},
     [2 * Fraction(1e308), 3]),
    ("x * y", {"x": [BIG, 2.0], "y": [BIG, 3.0]}, [Fraction(BIG) ** 2, 6]),
    ("x ** 2", {"x": [BIG, -3.0]}, [Fraction(BIG) ** 2, 9]),
    ("(x + y) - y", {"x": [1.0, 0.5], "y": [1e16, 1e16]}, [1, Fraction(1, 2)]),
    ("x * y - x * y", {"x": [BIG, 0.1], "y": [BIG, 0.3]}, [0, 0]),
    ("2 * x - x", {"x": [1e308, 0.1]}, [Fraction(1e308), Fraction(0.1)]),
])
def test_elementwise_arithmetic_is_exact_per_entry(src, values, want):
    assert exactly(evaluate(src, **values)) == [Fraction(w) for w in want]


def test_a_chain_of_elementwise_operations_rounds_once():
    # 0.1 + 0.2 + 0.3 rounded once is 0.6; added in floats it is
    # 0.6000000000000001
    got = evaluate("x + y + z", x=[0.1], y=[0.2], z=[0.3])
    assert entries(got) == [0.6]


@pytest.mark.parametrize("src", ["outer(x, y)", "kron(x, y)"])
def test_outer_and_kron_keep_an_entry_beyond_float_range(src):
    got = evaluate(src, x=[BIG, 1.0], y=[BIG, 3.0])
    assert Fraction(BIG) ** 2 in exactly(got)
    assert 3 in exactly(got)


@pytest.mark.parametrize("A, rank", [
    ([[1.0, 1.0], [1.0, 1.0 + 2 ** -52]], 2),
    ([[1e16, 1.0], [1e16, 1.0]], 1),
    ([[BIG, BIG], [BIG, BIG]], 1),
    ([[0.0, 0.0], [0.0, 0.0]], 0),
])
def test_rank_is_exact(A, rank):
    assert evaluate("rank(A)", A=A) == rank


def _mp(A):
    return mpmath.matrix([[mpmath.mpf(Fraction(v).numerator) / Fraction(v).denominator
                           for v in row] for row in A])


NEAR_SINGULAR = [[1e16, 1.0], [1.0, 1e-16]]


def test_eigvalsh_is_certified_where_lapack_misreads_the_small_one():
    with mpmath.workdps(60):
        want, _ = mpmath.eigsy(_mp(NEAR_SINGULAR))
        want = sorted(float(v) for v in want)
    assert [float(v) for v in entries(evaluate("eigvalsh(A)", A=NEAR_SINGULAR))] == want


def test_cond_and_the_two_norm_are_certified():
    with mpmath.workdps(60):
        s = mpmath.svd_r(_mp(NEAR_SINGULAR), compute_uv=False)
        s = sorted((s[i] for i in range(len(s))), reverse=True)
        cond, two = float(s[0] / s[-1]), float(s[0])
    assert float(evaluate("cond(A)", A=NEAR_SINGULAR)) == cond
    assert float(evaluate("norm(A, 2)", A=NEAR_SINGULAR)) == two


def test_cond_of_a_singular_matrix_is_infinite():
    assert evaluate("cond(A)", A=[[1.0, 2.0], [2.0, 4.0]]) == float("inf")


@pytest.mark.parametrize("A, want", [
    ([[0.0, 1.0], [-1.0, 0.0]], [-1j, 1j]),
    ([[2.0, 1.0], [0.0, 3.0]], [2.0, 3.0]),
    ([[1.0, 1e16], [0.0, 1.0]], [1.0, 1.0]),
])
def test_eigvals_are_certified_and_ordered(A, want):
    assert [complex(v) for v in entries(evaluate("eigvals(A)", A=A))] == \
        [complex(w) for w in want]


@pytest.mark.parametrize("A", [[[1e16, 1.0], [1e16, 1.0]],
                               [[1.0, 2.0], [3.0, 4.0]],
                               [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]])
def test_pinv_is_exact(A):
    exact = sympy.Matrix([[sympy.Rational(Fraction(v)) for v in row]
                          for row in A]).pinv()
    want = [float(Fraction(int(v.p), int(v.q))) for v in exact]
    assert [float(v) for v in entries(evaluate("pinv(A)", A=A))] == want


def test_an_eigenvalue_that_cannot_be_certified_leaves_the_point_undecided():
    """Two eigenvalues 2e-300 apart (1 plus or minus 1e-300 i) cannot be
    told apart by 60-digit approximations: the word raises rather than
    return numpy's floats, and a claim reads that raise as an undecided
    point."""
    from mathema._linalg_exact import Untrusted
    with pytest.raises(Untrusted):
        evaluate("eigvals(A)", A=[[1.0, 1e-300], [-1e-300, 1.0]])
