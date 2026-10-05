# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A reversal, `scale_seq` and `shift_seq` act on the vector they are
given, not on every element of the input sequence inside it.

`cumsum(x)[::-1]` is the running sum read backwards: its first element
is the whole sum. Rewriting every `x[k]` inside the running sum to
`x[L - 1 - k]` instead gives the running sum of the reversed input,
a different vector. In the same way `scale_seq(np.square(x), 2)` is
`2*x[i]**2`, not `(2*x[i])**2`, and `shift_seq(cumsum(x), c)` adds `c`
once to each running total. Each false claim below is falsified by
the reproduction beside it; none of them may be proven, and each true
sibling is.
"""
from __future__ import annotations

import ast

import numpy as np
import pandas as pd
import pytest
import sympy

import mathema
from mathema.compendium import _installed_version, _version_in_range
from mathema.symbolic._seqir import Lowering, normalised


def running(x: np.ndarray) -> np.ndarray:
    return np.cumsum(x)


def squares(x: np.ndarray) -> np.ndarray:
    return np.square(x)


def demean(x: np.ndarray) -> np.ndarray:
    return x - np.mean(x)


def running_pd(s: pd.Series) -> pd.Series:
    return s.cumsum()


def peak(s: pd.Series) -> pd.Series:
    return s.cummax()


_REVERSE = "let s = mathema.f.reverse_seq, "
_SHIFT = "let g = mathema.f.shift_seq, let c be [-5, 5], "
_SCALE = "let s = mathema.f.scale_seq, "


def _verdict(fn, law):
    r = mathema.check(fn, claims=[law])
    (p,) = [p for p in r.probes if p.statement and "f(" in p.statement
            and "[float" not in (p.name or "")]
    return p


@pytest.mark.parametrize("fn, law", [
    (running, "for x in R^n, f(x)[::-1] == cumsum(x[::-1])"),
    (running, _REVERSE + "for x in R^n, s(f(x)) == f(s(x))"),
    (running_pd, "for s in R^n, f(s)[::-1] == f(s[::-1])"),
    (running, _SHIFT + "for x in R^n, g(f(x), c) == f(g(x, c))"),
    (squares, _SCALE + "for x in R^n, s(f(x), 2) == f(x) * 4"),
    (demean, _SHIFT + "for x in R^n, g(f(x), c) == f(x)"),
    (peak, "for s in R^n, (f(s) + s)[::-1] == f(s) + s[::-1]"),
])
def test_a_false_transform_identity_is_never_proven(fn, law):
    p = _verdict(fn, law)
    assert p.verdict != "proven", (law, p.verdict, p.sketch)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, law", [
    (running, _REVERSE + "for x in R^n, s(s(f(x))) == f(x)"),
    (running, _SHIFT + "for x in R^n, g(f(x), c) == f(x) + c"),
    (demean, _SHIFT + "for x in R^n, f(g(x, c)) == f(x)"),
])
def test_the_true_sibling_is_proven(fn, law):
    p = _verdict(fn, law)
    assert p.verdict == "proven", (law, p.verdict, p.sketch)


# `numpy.square`'s definition row applies from numpy 2.4; below it the
# squares are sampled
_SQUARE_ROW = _version_in_range(_installed_version("numpy") or "0", ">=2.4")


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("law", [
    _SCALE + "for x in [-1e6, 1e6]^n, s(f(x), 2) == f(x) * 2",
    _SCALE + "for x in [-1e6, 1e6]^n, f(s(x, 2)) == f(x) * 4",
])
def test_the_true_sibling_through_a_numpy_ufunc_is_proven_from_its_row(law):
    p = _verdict(squares, law)
    assert p.verdict == ("proven" if _SQUARE_ROW else "holds"), (
        law, p.verdict, p.sketch)


L = sympy.Symbol("L", integer=True, positive=True)
X = sympy.IndexedBase("x", real=True)
C = sympy.Symbol("c", real=True)


def _lowered(src, transforms):
    low = Lowering({"x": (X, L)}, {"c": C}, transforms)
    return low.lower(ast.parse(src, mode="eval"))


def _same(a, b, transforms) -> bool:
    left, right = _lowered(a, transforms), _lowered(b, transforms)
    return normalised(left.elem - right.elem, {X: L}) == 0


def test_the_lowering_reverses_a_running_sum_as_a_whole():
    t = {"r": "reverse", "s": "scale", "g": "shift"}
    assert not _same("cumsum(x)[::-1]", "cumsum(x[::-1])", t)
    assert not _same("r(cumsum(x))", "cumsum(r(x))", t)
    assert _same("r(r(cumsum(x)))", "cumsum(x)", t)
    assert not _same("s(x**2, c)", "(c * x)**2", t)
    assert _same("s(x**2, c)", "c * x**2", t)
    assert not _same("g(cumsum(x), c)", "cumsum(g(x, c))", t)
    assert _same("g(cumsum(x), c)", "cumsum(x) + c", t)
