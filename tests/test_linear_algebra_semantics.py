# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What each operator means on vectors and matrices, the numpy way.

`A @ B` is the matrix product; `A * B` of two matrices or vectors is
the elementwise (Hadamard) product and `c * A` scales; `A ** k` is the
elementwise power and `matrix_power(A, k)` the matrix power; `+`, `-`
and unary `-` are elementwise, never list concatenation or repetition;
`abs(A)` is elementwise while the bars `|A|` stay the determinant of a
declared matrix; `norm(x)` is the Euclidean norm of a vector and the
Frobenius norm of a matrix, with `norm(A, 2)`, `norm(A, 1)` and
`norm(A, inf)`; matrix `~=` compares element by element. Each reading
is pinned by a true identity and a false sibling.
"""
from __future__ import annotations

import pytest

from mathema.claims import check_conjectures, claim
from mathema.types import Mat, Vec


def two(A: Mat("n", "n"), B: Mat("n", "n")):
    return A


def one(A: Mat("n", "n")):
    return A


def vecs(x: Vec("n"), y: Vec("n")):
    return x


def scaled(c: float, x: Vec("n")):
    return x


def plain_pair(x, y):
    return x


def ident(A):
    return A


def doubled(x: Vec("n")):
    return [2 * v for v in x]


def _one(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def _holds(p):
    return p.verdict in ("proven", "holds")


@pytest.mark.parametrize("law, true", [
    ("A * B == B * A", True),           # Hadamard commutes
    ("A @ B == B @ A", False),          # the matrix product does not
    ("A * B == A @ B", False),          # `*` is not the matrix product
    ("A ** 2 == A * A", True),          # `**` is elementwise
    ("A ** 2 == A @ A", False),
    ("matrix_power(A, 2) == A @ A", True),
    ("matrix_power(A, 2) == A * A", False),
    ("-(A + B) == -A - B", True),
    ("A - B == B - A", False),
])
def test_matrix_operators_read_as_numpy(law, true):
    p = _one(two, law)
    assert _holds(p) is true, (law, p.verdict, p.note, p.counterexample)
    if not true:
        assert p.verdict == "falsified" and p.counterexample, (law, p.note)


@pytest.mark.parametrize("route", ["derive", "best"])
def test_the_hadamard_product_commutes_on_derive(route):
    p = _one(two, "A * B == B * A", route)
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)


@pytest.mark.parametrize("law, true", [
    ("norm(x + y) <= norm(x) + norm(y)", True),
    ("norm(x + y)**2 == norm(x)**2 + norm(y)**2", False),
    ("norm(x + y)**2 == norm(x)**2 + norm(y)**2 + 2*dot(x, y)", True),
    ("norm(x - y) == norm(y - x)", True),
    ("norm(x) == sum(x)", False),
    ("x + y == y + x", True),
    ("x - y == y - x", False),
    ("abs(x) >= 0 * x", None),
])
def test_vector_operators_read_as_numpy(law, true):
    if true is None:
        # an ordering on vector-valued sides is refused
        p = _one(vecs, law)
        assert p.verdict == "skipped:misspecified", (p.verdict, p.note)
        return
    p = _one(vecs, law)
    assert _holds(p) is true, (law, p.verdict, p.note, p.counterexample)


@pytest.mark.parametrize("law, true", [
    ("norm(c*x) == abs(c)*norm(x)", True),
    ("norm(c*x) == c*norm(x)", False),
    ("norm(x + c) <= norm(x) + abs(c)*norm(x + 1 - x)", "corner"),
])
def test_a_number_scales_and_shifts_every_element(law, true):
    p = _one(scaled, law)
    if true == "corner":
        # true over the reals; c at the float limit overflows the
        # computation (rulings of 2026-10-01 and 2026-10-05)
        assert _falls_at_a_magnitude_corner(p), (law, p.verdict, p.counterexample)
        return
    assert _holds(p) is true, (law, p.verdict, p.note, p.counterexample)


@pytest.mark.parametrize("law, true", [
    ("for x in R^n, y in R^n, x + y == y + x", True),
    ("for x in R^n, y in R^n, len(x + y) == len(x) + len(y)", False),
    ("for x in R^n, len(2*x) == len(x)", True),
])
def test_plus_on_vectors_is_never_concatenation(law, true):
    # the function takes plain lists, and the claim's `+` and `*` are
    # still elementwise
    p = _one(plain_pair, law, "probe")
    assert _holds(p) is true, (law, p.verdict, p.note, p.counterexample)


def test_a_bound_library_function_sees_the_elementwise_value():
    # `h(2*x)` passes the doubled vector, not the list repeated twice
    p = _one(vecs, "let h = numpy.linalg.norm, h(2*x) == 2*h(x)")
    assert _holds(p), (p.verdict, p.note, p.counterexample)
    p = _one(vecs, "let h = numpy.linalg.norm, "
                   "h(x + y)**2 == h(x)**2 + h(y)**2")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_returned_list_is_read_back_as_a_vector():
    p = _one(doubled, "f(x) == 2*x")
    assert _holds(p), (p.verdict, p.note, p.counterexample)
    p = _one(doubled, "f(x) + f(x) == 4*x")
    assert _holds(p), (p.verdict, p.note, p.counterexample)
    p = _one(doubled, "f(x) == x + x + x")
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.parametrize("law, true", [
    ("norm(A) == sqrt(trace(A.T @ A))", True),       # Frobenius
    ("norm(A) == sqrt(trace(A @ A))", False),
    ("norm(A, 2) <= norm(A)", True),                  # spectral <= Frobenius
    ("norm(A, 2) == norm(A)", False),
    ("norm(A, 1) == max(sum(abs(A), axis=0))", True),
    ("norm(A, inf) == max(sum(abs(A), axis=1))", True),
    ("norm(A, inf) == max(sum(abs(A), axis=0))", False),
])
def test_matrix_norms(law, true):
    p = _one(one, law)
    assert _holds(p) is true, (law, p.verdict, p.note, p.counterexample)


def test_explicit_abs_of_a_matrix_is_elementwise():
    p = _one(one, "abs(A) == abs(-A)")
    assert _holds(p), (p.verdict, p.note, p.counterexample)
    assert "det" not in p.statement, p.statement
    p = _one(one, "abs(A) == A")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_bars_on_a_declared_matrix_stay_the_determinant():
    for law, fn in (("|A| == det(A)", one),
                    ("for A in R^(n,n), |A| == det(A)", ident)):
        cj = claim(law)
        (p,) = check_conjectures(fn, [cj])
        assert _holds(p), (law, p.verdict, p.note, p.counterexample)
    assert claim("for A in R^(n,n), |A| >= 0").lhs == "det(A)"
    assert claim("for A in R^(n,n), abs(A) == abs(A)").lhs == "abs(A)"


def test_matrix_closeness_is_elementwise_with_the_scalar_tolerance():
    p = _one(one, "assuming det(A) != 0, A @ inv(A) ~= I(n)", "probe")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    p = _one(one, "assuming det(A) != 0, A @ inv(A) ~= 2 * I(n)", "probe")
    assert p.verdict == "falsified", (p.verdict, p.note)


def _falls_at_a_magnitude_corner(p):
    """The float computation gives no value, or loses the value, at a
    draw with an entry of magnitude 1e150 or more: a carrier failure,
    which falsifies the computation line (rulings of 2026-10-01 and
    2026-10-05: corners on, a carrier failure falsifies the computation
    line)."""
    import re
    if p.verdict != "falsified" or not p.counterexample:
        return False
    numbers = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?e[+-]?\d+",
                                            p.counterexample)]
    return any(abs(v) >= 1e150 for v in numbers)
