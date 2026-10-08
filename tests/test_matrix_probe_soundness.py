# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Sampling a matrix claim never reports a counterexample the claim
does not have.

A premise over numbers (`assuming det(A) > 0`) narrows the matrices a
claim is sampled over, the same parsed premise the ordinary probe
filters by. The output-structure check (`is_symmetric(f(A))`) draws
its inputs with their structure markers and premises. A draw whose two
sides differ only by the round-off its own magnitudes produce (entries
near 1e6 and 1e-9 cancelling in a determinant) is not a
counterexample. A fixed size, `Mat(2, 2)`, holds in every draw. And
`inv(A) @ A == I(n)` keeps both of its sides wherever it is shown.
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from mathema.claims import check_conjectures, claim  # noqa: E402
from mathema.types import Mat, Symmetric  # noqa: E402


def one(A: Mat("n", "n")):
    return A


def sym_ret(A: Mat("n", "n", Symmetric)):
    return A


def matmul(A: Mat("n", "n"), B: Mat("n", "n")):
    return (np.asarray(A, float) @ np.asarray(B, float)).tolist()


def fixed2(A: Mat(2, 2)):
    return A


def _one(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


@pytest.mark.parametrize("route", ["best", "probe"])
@pytest.mark.parametrize("law", [
    "assuming det(A) > 0, det(A) > 0",
    "assuming det(A) > 0, det(inv(A)) > 0",
    "assuming det(A) < 0, det(A @ A) > 0",
    "assuming trace(A) > 0, trace(A) > 0",
])
def test_a_scalar_premise_narrows_the_matrices_sampled(law, route):
    p = _one(one, law, route)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note,
                                               p.counterexample)


def test_a_scalar_premise_does_not_hide_a_false_claim():
    p = _one(one, "assuming det(A) > 0, det(A @ A) < 0")
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.parametrize("fn, law", [
    (sym_ret, "is_symmetric(f(A))"),
    (one, "assuming A is symmetric, is_symmetric(f(A))"),
    (one, "assuming A is positive definite, is_positive_definite(f(A))"),
])
def test_the_output_structure_check_draws_inputs_with_their_structure(fn,
                                                                       law):
    p = _one(fn, law)
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_the_output_structure_check_still_falsifies_without_structure():
    p = _one(one, "is_symmetric(f(A))")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_round_off_at_extreme_draws_is_not_a_counterexample():
    p = _one(matmul, "det(f(A, B)) == det(A) * det(B)", "probe")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_the_round_off_allowance_does_not_hide_a_false_claim():
    p = _one(matmul, "det(f(A, B)) == det(A) + det(B)", "probe")
    assert p.verdict == "falsified", (p.verdict, p.note)
    p = _one(matmul, "f(A, B) == f(B, A)", "probe")
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.parametrize("route", ["best", "probe"])
def test_a_fixed_size_is_held_in_every_draw(route):
    p = _one(fixed2, "dim(A, 0) == 2", route)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note,
                                               p.counterexample)
    p = _one(fixed2, "det(A) == A[0][0]*A[1][1] - A[0][1]*A[1][0]", route)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note,
                                               p.counterexample)
    p = _one(fixed2, "dim(A, 1) == 3", route)
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_the_resolver_keeps_an_integer_dimension_fixed():
    import random

    import mathema
    from mathema import dimensions
    from mathema.types import shapes_from_signature

    resolver = dimensions.resolve(mathema.analyze(fixed2),
                                  shapes_from_signature(fixed2))
    rng = random.Random(3)
    for _ in range(20):
        sizes = resolver.draw_sizes(rng)
        assert set(sizes.values()) == {2}, sizes


def test_the_inverse_identity_keeps_both_sides():
    from mathema import grammar

    law = "inv(A) @ A == I(n)"
    latex = grammar.to_latex(law)
    assert "A^{-1} A" in latex and "\\mathbb{I}" in latex, latex
    p = _one(one, f"assuming det(A) != 0, {law}", "derive")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "inv(A) @ A" in p.sketch and "I = I" not in p.sketch, p.sketch
    assert "inv(A)" in p.statement, p.statement
