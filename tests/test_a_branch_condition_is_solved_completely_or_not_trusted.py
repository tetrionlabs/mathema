# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A branch guarded by an equality is zero only if it is zero at every
solution of that equality. `sin(n) == 0` has infinitely many real
solutions, not just the two a solver lists, so a branch zero at 0 and
pi and nowhere else does not prove the difference zero. A Float of
more than double precision reaches the solver as the number it holds."""
import sympy
from fractions import Fraction

from mathema.symbolic import _smt
from mathema.symbolic._proof_support import _sum_closed_zero


def test_an_incomplete_solution_list_proves_nothing():
    n = sympy.Symbol("n", real=True)
    diff = sympy.Piecewise((n * (n - sympy.pi), sympy.Eq(sympy.sin(n), 0)),
                           (0, True))
    assert _sum_closed_zero(diff) is None


def test_a_complete_finite_solution_set_still_proves():
    n = sympy.Symbol("n", real=True)
    diff = sympy.Piecewise((n * (n - 2), sympy.Eq(n ** 2 - 2 * n, 0)),
                           (0, True))
    assert _sum_closed_zero(diff) is True


def test_a_high_precision_float_keeps_its_digits_in_the_solver():
    if not _smt.available():
        return
    import z3
    t = _smt._Translator(z3, {})
    value = sympy.Float("0.30000000000000000001", 40)
    q = t._rational(value)
    assert Fraction(str(q)) == Fraction(*sympy.Rational(value).as_numer_denom())
    assert Fraction(str(q)) != Fraction(3, 10)
