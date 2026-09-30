# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Lowering vector claims to sums over a sequence of symbolic length.

A vector `x` of length `L` is `x[0], ..., x[L - 1]`; `mean`, `var`,
`std`, `sum`, `prod`, `count` and the running sums close into sums and
products over it, and `linear_sums` is the normaliser sympy lacks:
it splits a sum over `+`, pulls out what does not depend on the index,
and counts a sum of a constant. Each identity below is proven for
every length, and its false sibling is not. A transform that changes
nothing is refused, so an unapplied scaling can never read as `f(xs)`
itself.
"""
from __future__ import annotations

import ast

import pytest
import sympy

from mathema.symbolic._base import NotSymbolic
from mathema.symbolic._seqir import Lowering, linear_sums, normalised

L = sympy.Symbol("L", integer=True, positive=True)
X = sympy.IndexedBase("x", real=True)
C = sympy.Symbol("c", positive=True)
K = sympy.Symbol("k", real=True)


def _lower(src, transforms=None):
    low = Lowering({"x": (X, L)}, {"c": C, "k": K}, dict(transforms or {}))
    return low.lower(ast.parse(src, mode="eval")), low.obligations


def _zero(lhs, rhs, transforms=None) -> bool:
    left, _ = _lower(lhs, transforms)
    right, _ = _lower(rhs, transforms)
    if hasattr(left, "elem"):
        return normalised(left.elem - right.elem, {X: L}) == 0
    return normalised(left - right, {X: L}) == 0


def test_linear_sums_splits_pulls_out_and_counts():
    i = sympy.Symbol("i", integer=True)
    s = sympy.Sum(C * X[i] + K, (i, 0, L - 1))
    out = linear_sums(s)
    k0 = sympy.Symbol("_k0", integer=True, nonnegative=True)
    assert sympy.simplify(out - (C * sympy.Sum(X[k0], (k0, 0, L - 1))
                                 + K * L)) == 0


@pytest.mark.parametrize("lhs, rhs, false", [
    ("mean(x + k)", "mean(x) + k", "mean(x)"),
    ("std(x + k, ddof=1)", "std(x, ddof=1)", "std(x, ddof=1) + k"),
    ("var(c * x)", "c**2 * var(x)", "c * var(x)"),
    ("std(c * x, ddof=1)", "c * std(x, ddof=1)", "std(x, ddof=1)"),
    ("sum(x[::-1])", "sum(x)", "sum(x) + 1"),
    ("prod(c * x)", "c**len(x) * prod(x)", "c * prod(x)"),
    ("count(x)", "len(x)", "len(x) - 1"),
    ("sum(cumsum(x))", "sum(cumsum(x))", "sum(x)"),
    ("dot(x, x)", "sum(x**2)", "sum(x)**2"),
])
def test_each_identity_holds_for_every_length_and_its_sibling_does_not(
        lhs, rhs, false):
    assert _zero(lhs, rhs), (lhs, rhs)
    assert not _zero(lhs, false), (lhs, false)


def test_a_bound_transform_rewrites_every_element_or_is_refused():
    assert _zero("mean(s(x, c))", "c * mean(x)", {"s": "scale"})
    assert not _zero("mean(s(x, c))", "mean(x)", {"s": "scale"})
    assert _zero("mean(s(x, k))", "mean(x) + k", {"s": "shift"})
    with pytest.raises(NotSymbolic, match="unchanged"):
        _lower("s(x - x, c)", {"s": "scale"})


def test_a_sample_statistic_needs_more_positions_than_its_ddof():
    _, obligations = _lower("std(x, ddof=1)")
    assert obligations.min_length == {L: 2}
    _, obligations = _lower("var(x, ddof=0)")
    assert obligations.min_length == {L: 1}
    _, obligations = _lower("mean(x) / std(x)")
    assert [text for _e, text in obligations.nonzero] == ["std(x)"]


@pytest.mark.parametrize("src", ["median(x)", "sqrt(x)", "x ** x",
                                 "x[0]"])
def test_a_construct_outside_the_lowering_is_named(src):
    with pytest.raises(NotSymbolic):
        _lower(src)


def test_a_least_element_and_an_elementwise_quotient_lower():
    _lower("min(x)")
    _, obligations = _lower("x / x")
    assert [text for _e, text in obligations.nonzero] == ["x"]


def test_a_constant_base_to_a_rational_power_lowers():
    assert _zero("mean(x) * 252 ** 0.5", "mean(x) * sqrt(252)")
    assert not _zero("mean(x) * 252 ** 0.5", "mean(x) * 252")
    root, _ = _lower("8 ** (1 / 3)")
    assert root == 2


@pytest.mark.parametrize("src", ["k ** 0.5", "std(x) ** 0.5", "x ** 0.5",
                                 "(-8) ** (1 / 3)", "c ** k"])
def test_a_variable_base_or_a_negative_constant_to_a_fractional_power_does_not(
        src):
    with pytest.raises(NotSymbolic, match="power"):
        _lower(src)
