# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Matrices and vectors are real in this release.

A claim over `C^n` or `C^(m,n)` is refused as misspecified with the
reason, on every route; a claim over complex numbers keeps working.
"""
from __future__ import annotations

import pytest

from mathema.claims import check_conjectures, claim


def ident(A):
    return A


def square(z: complex):
    return z * z


@pytest.mark.parametrize("route", ["derive", "best", "probe"])
@pytest.mark.parametrize("law", [
    "for A in C^(n,n), det(A @ A) == det(A)**2",
    "for A in C^(n,n), A.T == A",
    "for A in C^n, A + A == 2*A",
])
def test_a_complex_matrix_or_vector_is_refused(law, route):
    (p,) = check_conjectures(ident, [claim(law, route=route)])
    assert p.verdict == "skipped:misspecified", (p.verdict, p.note)
    assert "matrices and vectors are real-only in this release" in p.note


@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_complex_scalar_claim_still_adjudicates(route):
    (p,) = check_conjectures(square, [claim("for z in C, f(z) == z*z",
                                            route=route)])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)
    (p,) = check_conjectures(square, [claim("for z in C, f(z) == 2*z",
                                            route=route)])
    assert p.verdict == "falsified", (p.verdict, p.note)
