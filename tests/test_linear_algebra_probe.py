# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The probe evaluates the whole linear-algebra vocabulary.

`route="probe"` evaluates `@`, `.T`, `trace`, `inv`, `det`, `I(n)`,
`transpose` and `matrix_power` through the one namespace every probe
of a claim shares; so does the sampling a `best` claim falls to. A
claim may use the identity sized by a drawn dimension, unary minus,
scalar parameters, `abs` and subscripts. A finiteness guard is tried
against matrices holding a NaN or an infinity. A structure premise
combines with a relation premise, and the identity and skew-symmetric
premises carry to the derive route.
"""
from __future__ import annotations

import numpy as np
import pytest

from mathema.claims import check_conjectures, claim
from mathema.types import Mat


def one(A: Mat("n", "n")):
    return A


def two(A: Mat("n", "n"), B: Mat("n", "n")):
    return A


def scaled(c: float, A: Mat("n", "n")):
    return A


def transpose(A: Mat("n", "n")):
    return np.asarray(A, float).T.tolist()


def inverse(A: Mat("n", "n")):
    return np.linalg.inv(np.asarray(A, float)).tolist()


def trace_loop(A: Mat("n", "n")):
    t = 0.0
    for i in range(len(A)):
        t = t + A[i][i]
    return t


def guarded(A: Mat("n", "n")):
    a = np.asarray(A, float)
    if not np.isfinite(a).all():
        raise ValueError("not finite")
    return A


def unguarded(A: Mat("n", "n")):
    return A


def _one(fn, law, route="probe"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def _holds(p):
    return p.verdict in ("proven", "holds")


@pytest.mark.parametrize("fn, law, true", [
    (transpose, "f(A) == A.T", True),
    (transpose, "f(A) == A", False),
    (transpose, "f(A) == transpose(A)", True),
    (transpose, "f(f(A)) == A", True),
    (inverse, "assuming det(A) != 0, f(A) @ A ~= I(n)", True),
    (inverse, "assuming det(A) != 0, f(A) @ A ~= 2 * I(n)", False),
    (inverse, "assuming det(A) != 0, det(f(A)) ~= 1 / det(A)", True),
    (inverse, "assuming det(A) != 0, det(f(A)) ~= det(A)", False),
    (trace_loop, "f(A) == trace(A)", True),
    (trace_loop, "f(A) == trace(A @ A)", False),
    (one, "matrix_power(A, 3) ~= A @ A @ A", True),
    (one, "matrix_power(A, 3) ~= A * A * A", False),
    (one, "inv(A.T) ~= inv(A).T", True),
    (two, "trace(A @ B) ~= trace(B @ A)", True),
    (two, "trace(A @ B) ~= trace(A) * trace(B)", False),
])
def test_the_plain_probe_evaluates_the_matrix_vocabulary(fn, law, true):
    p = _one(fn, law)
    assert _holds(p) is true, (law, p.verdict, p.note, p.counterexample)


@pytest.mark.parametrize("route", ["probe", "best"])
@pytest.mark.parametrize("fn, law, true", [
    (one, "A + I(n) - I(n) == A", True),
    (one, "A + I(n) == A", False),
    (one, "-(-A) == A", True),
    (one, "-A == A", False),
    (scaled, "trace(c * A) ~= c * trace(A)", True),
    (scaled, "trace(c * A) ~= trace(A)", False),
    (one, "abs(A)[0, 0] == abs(A[0][0])", True),
    (one, "A[0, :] == A[0]", True),
    (one, "A[:, 0] == A[0]", False),
    (one, "sum(A, axis=0) == sum(A.T, axis=1)", True),
    (one, "sum(A, axis=0) == sum(A, axis=1)", False),
])
def test_identity_minus_scalars_abs_and_subscripts_sample(fn, law, true,
                                                          route):
    p = _one(fn, law, route)
    if route == "probe" and law == "trace(c * A) ~= c * trace(A)":
        # c is unbounded, so the computation runs it out to the float
        # maximum, where c * A overflows: the probe is the computation
        # and reports it
        assert p.verdict == "falsified", (p.verdict, p.note)
        c = float(p.counterexample.split("c = ", 1)[1].split(",", 1)[0])
        assert abs(c) > 1e300, p.counterexample
        return
    assert _holds(p) is true, (law, p.verdict, p.note, p.counterexample)


def test_a_finiteness_guard_has_trials():
    p = _one(guarded, "is_finite(A)", "examine")
    assert p.verdict == "holds" and p.n > 0, (p.verdict, p.n, p.note)
    p = _one(unguarded, "is_finite(A)", "examine")
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.parametrize("law, true", [
    ("assuming A is symmetric and det(A) != 0, inv(A) ~= inv(A).T", True),
    ("assuming A is symmetric and det(A) > 0, det(A) > 0", True),
    ("assuming A is symmetric and det(A) != 0, inv(A) ~= A", False),
    ("assuming A is symmetric, assuming det(A) != 0, "
     "inv(A) ~= inv(A).T", True),
])
def test_a_structure_premise_combines_with_a_relation_premise(law, true):
    p = _one(one, law, "best")
    assert _holds(p) is true, (law, p.verdict, p.note, p.counterexample)


@pytest.mark.parametrize("law, true", [
    ("assuming A is identity, A == I(n)", True),
    ("assuming A is identity, A @ A == A", True),
    ("assuming A is skew_symmetric, A.T == -A", True),
    ("assuming A is skew_symmetric, trace(A) == 0", True),
])
def test_identity_and_skew_premises_reach_the_derive_route(law, true):
    p = _one(one, law, "derive")
    assert p.verdict == "proven", (law, p.verdict, p.note, p.sketch)


@pytest.mark.parametrize("law", [
    "assuming A is identity, A == 2 * I(n)",
    "assuming A is skew_symmetric, A.T == A",
])
def test_the_false_siblings_of_the_structure_premises_are_not_proven(law):
    p = _one(one, law, "derive")
    assert p.verdict != "proven", (law, p.verdict, p.sketch)
    p = _one(one, law, "best")
    assert p.verdict == "falsified", (law, p.verdict, p.note)
