# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An `assuming E >= k` premise lets the derive route replace E with
k plus a nonnegative slack. The slack ranges over every nonnegative
value, never only zero, so a premise bound is never read as `E == k`: a
claim false somewhere the premise allows is not proven, and the probe
falsifies it. True claims under the same premises still prove."""
import sympy

from mathema.conjecture import check_conjectures, claim
from mathema.symbolic._proof_support import _assumption_rewrites


def ident(x: float) -> float:
    return x


def product(x: float, y: float) -> float:
    return x * y


def test_the_slack_is_nonnegative_and_not_zero():
    x = sympy.Symbol("x", real=True)
    for predicate in (sympy.Q.nonnegative, sympy.Q.positive):
        ((subtree, replacement),) = _assumption_rewrites(
            predicate(2 * x - 1))
        (slack,) = replacement.free_symbols
        assert slack.is_nonnegative
        assert slack.is_zero is not True
        # 3/5 - slack is not known nonnegative
        assert (sympy.Rational(3, 5) - slack).is_nonnegative is not True
    ((_s, strict),) = _assumption_rewrites(sympy.Q.positive(2 * x - 1))
    (slack,) = strict.free_symbols
    assert slack.is_positive


def _one(fn, statement):
    (p,) = check_conjectures(fn, [claim(statement)])
    return p


def test_a_false_claim_under_a_lower_bound_premise_is_falsified():
    for fn, statement in [
        (ident, "assuming 2 * x >= 0, for x in [0, 1], f(2 * x) <= 0.6"),
        (product, "assuming x + y >= 0, for x in [0, 1], y in [0, 1], "
                  "f(x + y, y) <= 0.5"),
        (product, "assuming x * y >= 0, for x in [0, 1], y in [0, 1], "
                  "f(x * y, y) <= 0.1"),
    ]:
        p = _one(fn, statement)
        assert p.verdict == "falsified", (statement, p.verdict, p.route,
                                          p.sketch)


def test_a_true_claim_under_the_same_premise_still_proves():
    for fn, statement in [
        (ident, "assuming 2 * x >= 0, for x in [0, 1], f(2 * x) <= 2"),
        (product, "assuming x + y >= 0, for x in [0, 1], y in [0, 1], "
                  "f(x + y, y) <= 2"),
    ]:
        p = _one(fn, statement)
        assert p.verdict == "proven", (statement, p.verdict, p.note)
