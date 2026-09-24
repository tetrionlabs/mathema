# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Absolute-value bars wrap any expression, not only a single term:
`|x + y - f(x, y)|` is the absolute value of the whole difference, and
on a matrix expression the same bars are the determinant. `||x||` stays
a norm, `||a| - |b||` is an absolute value of a difference of absolute
values, and floor and ceiling brackets wrap any expression too. Every
spelling round-trips through the canonical text, and bars that do not
pair up are refused."""
import pytest

from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.grammar import normalize
from mathema.spec import canonical_claim_text, declare, entry_claims


@pytest.mark.parametrize("text,expected", [
    ("|x + y - f(x, y)|", "abs(x + y - f(x, y))"),
    ("|x| + |y|", "abs(x) + abs(y)"),
    ("||x||", "norm(x)"),
    ("||a| - |b||", "abs(abs(a) - abs(b))"),
    ("|-x|", "abs(-x)"),
    ("|x - |y||", "abs(x - abs(y))"),
    ("|(x + 1) * 2|", "abs((x + 1) * 2)"),
    ("2 * |x - 1| + 1", "2 * abs(x - 1) + 1"),
    ("|n!|", "abs(factorial(n))"),
    ("⌊x + 0.5⌋", "floor(x + 0.5)"),
    ("⌈x / 2⌉ - ⌊x / 2⌋", "ceil(x / 2) - floor(x / 2)"),
])
def test_bars_wrap_the_whole_expression(text, expected):
    assert normalize(text).replace(" ", "") == expected.replace(" ", "")


@pytest.mark.parametrize("law", [
    "for x in [0, 1], y in [0, 1], |x + y - f(x, y)| <= 1e-9",
    "for x in [0, 1], y in [0, 1], ||x| - |y|| <= 1",
    "for x in [0, 1], y in [0, 1], |f(x, y) - (x + y)| <= 1e-9",
])
def test_compound_bars_round_trip(law):
    cj = claim(law)
    once = canonical_claim_text(cj)
    assert canonical_claim_text(claim(once)) == once
    (back,) = entry_claims({"claims": [declare(cj)]})
    assert canonical_claim_text(back) == once


def add(x: float, y: float) -> float:
    return x + y


def add_off(x: float, y: float) -> float:
    return x + y + 0.5


@pytest.mark.parametrize("route,supported", [("derive", "proven"),
                                             ("probe", "holds")])
def test_compound_bars_adjudicate(route, supported):
    law = "for x in [0, 1], y in [0, 1], |x + y - f(x, y)| <= 1e-9"
    (p,) = check_conjectures(add, [claim(law, route=route)])
    assert p.verdict == supported, (p.verdict, p.note)
    (q,) = check_conjectures(add_off, [claim(law, route=route)])
    assert q.verdict == "falsified" and q.counterexample


def test_bars_on_a_matrix_expression_are_the_determinant():
    cj = claim("for A in R^(n*n), B in R^(n*n), |A @ B| == |A| * |B|")
    assert "det(A @ B)" in cj.lhs.replace(" ", "").replace("det(A@B)", "det(A @ B)") \
        or "det(A@B)" in cj.lhs.replace(" ", "")
    assert "abs" not in cj.lhs + cj.rhs


@pytest.mark.parametrize("bad", [
    "f(x) <= |x + 1",
    "|x| + y| <= 1",
])
def test_bars_that_do_not_pair_are_refused(bad):
    with pytest.raises(InvalidConjecture):
        claim(bad)


@pytest.mark.parametrize("fname,key", [
    ("add_two", "abs_bars_compound"),
    ("matmul", "matrix_determinant_bars_compound"),
])
def test_the_lexicon_bar_entries_prove_against_their_example(fname, key):
    from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON
    fn, keys = EXAMPLE_FUNCTIONS[fname]
    assert key in keys
    (p,) = check_conjectures(fn, [claim(LEXICON[key])])
    assert p.verdict == "proven", (key, p.verdict, p.note)


def test_the_matrix_bars_are_the_same_claim_as_the_det_spelling():
    bars = claim("for A in R^(n*n), B in R^(n*n), |A @ B| == |A| * |B|")
    calls = claim("for A in R^(n*n), B in R^(n*n), det(A @ B) == det(A) * det(B)")
    assert canonical_claim_text(bars) == canonical_claim_text(calls)
