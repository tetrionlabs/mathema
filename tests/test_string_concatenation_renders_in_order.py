# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A law over strings keeps its concatenation order when rendered:
`s + "0"` appends a digit and `"0" + s` prepends one, two different
claims, so the canonical text never swaps them the way a commutative
sum could. The rendered statement must denote the claim that was
adjudicated."""
import ast

from mathema.conjecture import claim
from mathema.spec import canonical_claim_text, render_claim_text


def _same_expression(a: str, b: str) -> bool:
    # the canonical spelling of a string literal is the single-quoted
    # one; the structure is what must survive
    return ast.dump(ast.parse(a, mode="eval")) == ast.dump(ast.parse(b, mode="eval"))


def test_a_string_concatenation_keeps_its_order():
    cj = claim('for s in L[digit] \\ {""}, f(s + "0") == 10 * f(s)')
    canon = canonical_claim_text(cj)
    assert "s + " in canon and "+ s" not in canon, canon
    assert _same_expression(claim(canon).lhs, cj.lhs)
    assert "s + " in render_claim_text(cj, unicode=True)


def test_a_prepended_literal_keeps_its_order_too():
    cj = claim('for s in L[digit] \\ {""}, f("0" + s) == f(s)')
    canon = canonical_claim_text(cj)
    assert "+ s" in canon and "s + " not in canon, canon
    assert _same_expression(claim(canon).lhs, cj.lhs)


def test_a_numeric_sum_still_canonicalises():
    cj = claim("for x in [0, 1], f(x + 1) == f(1 + x)")
    canon = canonical_claim_text(cj)
    assert canon.count("x + 1") + canon.count("1 + x") == 2
