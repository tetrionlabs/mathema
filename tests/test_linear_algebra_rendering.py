# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A rendered linear-algebra claim reads back as the same claim.

The vocabulary words (`matrix_power`, `eigvalsh`) are the grammar's
own names, never display-shortened into a `let`; an explicit `abs` of
a matrix keeps its call spelling, since bars around a matrix read as
its determinant.
"""
from __future__ import annotations

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.spec import render_claim_text
from mathema.types import Mat


def one(A: Mat("n", "n")):
    return A


@pytest.mark.parametrize("unicode", [True, False])
@pytest.mark.parametrize("law", [
    "for A in R^(n,n), matrix_power(A, 2) == A @ A",
    "for A in R^(n,n), abs(A) == abs(-A)",
    "for A in R^(n,n), trace(abs(A)) >= abs(trace(A))",
    "assuming A is positive definite, for A in R^(n,n), "
    "min(eigvalsh(A)) > 0",
])
def test_the_rendering_reads_back_as_the_same_claim(law, unicode):
    cj = claim(law)
    shown = render_claim_text(cj, unicode=unicode)
    again = claim(shown)
    assert render_claim_text(again, unicode=unicode) == shown, shown
    assert ("det" in again.lhs + again.rhs) == ("det" in cj.lhs + cj.rhs), \
        (shown, again.lhs, again.rhs)
    assert "let " not in shown, shown


def test_an_explicit_abs_of_a_marked_matrix_keeps_its_call_spelling():
    (p,) = check_conjectures(one, [claim("abs(A) == abs(A.T).T")])
    assert "det" not in p.statement, p.statement
    assert "|A|" not in p.statement, p.statement


def two(A: Mat("n", "n"), B: Mat("n", "n")):
    return A


@pytest.mark.parametrize("unicode", [True, False])
@pytest.mark.parametrize("law", [
    "for A in R^(n,n), for B in R^(n,n), A * B == B * A",
    "for A in R^(n,n), for B in R^(n,n), A @ B == B @ A",
    "for A in R^(n,n), for B in R^(n,n), C in R^(n,n), "
    "C * (A @ B) == (A @ B) * C",
    "for A in R^(n,n), for B in R^(n,n), (A @ B) ** 2 == (A @ B) * (A @ B)",
])
def test_a_matrix_product_keeps_its_written_order(law, unicode):
    cj = claim(law)
    shown = render_claim_text(cj, unicode=unicode)
    lhs, rhs = shown.split(", ")[-1].split(" = ")
    assert lhs != rhs, shown
    again = claim(shown)
    assert render_claim_text(again, unicode=unicode) == shown, shown


def test_elementwise_and_matrix_commutativity_render_differently():
    (hadamard,) = check_conjectures(two, [claim("A * B == B * A")])
    (product,) = check_conjectures(two, [claim("A @ B == B @ A")])
    assert hadamard.statement == "A*B = B*A", hadamard.statement
    assert product.statement == "A @ B = B @ A", product.statement
    assert hadamard.verdict == "proven"
    assert product.verdict == "falsified"


def test_a_stated_product_reads_back_as_the_same_claim():
    for law in ("A * B == B * A", "A @ B == B @ A", "C * (A @ B) == A",
                "B.T * A.T == (A * B).T"):
        def three(A: Mat("n", "n"), B: Mat("n", "n"), C: Mat("n", "n")):
            return A
        (p,) = check_conjectures(three, [claim(law)])
        (again,) = check_conjectures(three, [claim(p.statement)])
        assert again.statement == p.statement, (law, p.statement,
                                                again.statement)


def test_a_bare_claim_without_matrices_still_reads_scalars():
    assert render_claim_text(claim("x * y == y * x"), unicode=False) \
        == "x*y = x*y"


def test_latex_writes_the_elementwise_product_as_a_circle():
    from mathema.grammar import to_latex
    text = to_latex("for A in R^(n,n), for B in R^(n,n), A * B == B * A")
    assert r"A \circ B = B \circ A" in text, text
    assert to_latex("A * B == B * A", matrix_names=frozenset("AB")) \
        == r"A \circ B = B \circ A"
    assert to_latex("B @ A == A @ B") == "B A = A B"
