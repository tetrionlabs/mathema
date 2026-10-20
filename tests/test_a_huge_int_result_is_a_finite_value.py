# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A Python int is exact and finite at any size, so an int result too
large for a float is a value: `is_defined`, `is_finite` and `is_real`
read it as one, a value claim compares it exactly, and a vector of
such ints is held exactly. None of these ends the check or reads the
size as a raise of f. A Fraction and a finite Decimal are exact too."""
import math
from decimal import Decimal
from fractions import Fraction

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.f import _is_nonfinite

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


def factorial_ish(n: int) -> int:
    r = 1
    for k in range(1, abs(n) % 300 + 200):
        r *= k
    return r


def guarded(n: int) -> int:
    try:
        return factorial_ish(n)
    except ValueError:
        return 0


def pair(n: int) -> list:
    r = factorial_ish(n)
    return [r, r]


@pytest.mark.parametrize("fn", [factorial_ish, guarded, pair],
                         ids=lambda fn: fn.__name__)
@pytest.mark.parametrize("law", ["is_defined(f)", "is_finite(f(n))",
                                 "is_real(f(n))", "f(n) >= 0"])
def test_a_huge_int_result_holds_as_a_value(fn, law):
    (p, *_rest) = check_conjectures(fn, [claim(law)])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample,
                                              p.note)
    assert "OverflowError" not in (p.counterexample or ""), p.counterexample


def test_a_false_claim_on_huge_ints_is_falsified_with_a_witness():
    (p, *_rest) = check_conjectures(pair, [claim("f(n) <= 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample and "OverflowError" not in p.counterexample, \
        p.counterexample


def test_an_exact_number_beyond_a_float_is_finite():
    huge = 10 ** 400
    assert not _is_nonfinite(huge)
    assert not _is_nonfinite(-huge)
    assert not _is_nonfinite(Fraction(huge, 3))
    assert not _is_nonfinite(Decimal("1e400"))
    assert _is_nonfinite(Decimal("Infinity"))
    assert _is_nonfinite(Decimal("NaN"))


def test_a_vector_with_a_huge_int_is_read_entry_by_entry():
    pytest.importorskip("numpy")
    huge = 10 ** 400
    assert not _is_nonfinite([huge, 1])
    assert _is_nonfinite([huge, math.inf])
    assert _is_nonfinite([huge, math.nan])
