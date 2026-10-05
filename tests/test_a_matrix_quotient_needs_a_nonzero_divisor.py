# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A matrix claim that divides needs its divisor nonzero.

`A / np.trace(A)` has trace 1 only where `trace(A)` is not zero; at
the zero matrix numpy returns NaN. The matrix algebra reads `x / x`
as 1, so a proof through it stands only where the claim's premises
keep every divisor away from zero (`assuming trace(A) != 0`), or the
divisor is a determinant of a matrix the claim already states is
invertible. Without that, the claim is not proven. The quotient also
keeps its divisor in the claim's own text: `f(A) / f(A) == 1` is never
stored as `1 == 1`.
"""
from __future__ import annotations

import numpy as np
import pytest

import mathema
from mathema.claims import check_conjectures, claim


def normalized(A: np.ndarray) -> np.ndarray:
    return A / np.trace(A)


def det_ratio(A: np.ndarray, B: np.ndarray) -> float:
    return np.linalg.det(A @ B) / np.linalg.det(A)


def inv_det(A: np.ndarray) -> float:
    return 1 / np.linalg.det(A)


def tr(A: np.ndarray) -> float:
    return np.trace(A)


def _derive(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


@pytest.mark.parametrize("fn, law", [
    (normalized, "for A in R^(n,n), trace(f(A)) == 1"),
    (det_ratio, "for A in R^(n,n), B in R^(n,n), f(A, B) == det(B)"),
    (inv_det, "for A in R^(n,n), f(A) * det(A) == 1"),
    (tr, "for A in R^(n,n), f(A) / f(A) == 1"),
])
def test_a_quotient_whose_divisor_can_be_zero_is_not_proven(fn, law):
    p = _derive(fn, law)
    assert p.verdict != "proven", (law, p.verdict, p.sketch)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, law", [
    (normalized, "for A in R^(n,n), assuming trace(A) != 0, "
                 "trace(f(A)) == 1"),
    (det_ratio, "for A in R^(n,n), B in R^(n,n), assuming det(A) != 0, "
                "f(A, B) == det(B)"),
    (inv_det, "for A in R^(n,n), assuming det(A) != 0, f(A) * det(A) == 1"),
])
def test_a_premise_that_excludes_zero_lets_the_quotient_prove(fn, law):
    p = _derive(fn, law)
    assert p.verdict == "proven", (law, p.verdict, p.sketch)


def test_the_divisor_names_the_premise_that_would_exclude_it():
    p = _derive(normalized, "for A in R^(n,n), trace(f(A)) == 1")
    assert "assuming trace(A) != 0" in (p.note or ""), p.note


def test_a_cancelling_quotient_keeps_its_divisor_in_the_claim():
    r = mathema.check(tr, claims=["for A in R^(n,n), f(A) / f(A) == 1"])
    (p,) = [p for p in r.probes if p.name == "f_a_f_a_eq_1"]
    assert "f(A) / f(A)" in p.statement, p.statement
