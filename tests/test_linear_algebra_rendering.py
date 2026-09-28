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
