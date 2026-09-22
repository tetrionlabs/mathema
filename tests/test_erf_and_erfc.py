# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""math.erf/math.erfc in the derive-route vocabulary (_math_vocab.py's
_SYMPY_FUNCS): the standard normal CDF is a direct affine transform of
erf, so this unblocks any normal-CDF/quantile-shaped claim across
statistics, finance, and engineering-reliability code, not a
domain-specific addition. Covers both what actually proves and an
honest, verified gap in what doesn't (sympy itself doesn't know erf's
own boundedness), rather than only the cases that work."""
import pytest
import math

import sympy

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.symbolic import lift


def erf_fn(x: float) -> float:
    return math.erf(x)


def erfc_fn(x: float) -> float:
    return math.erfc(x)


def erf_plus_erfc(x: float) -> float:
    return math.erf(x) + math.erfc(x)


def normal_cdf(x: float) -> float:
    return (1 + math.erf(x / math.sqrt(2))) / 2


def test_erf_lifts_to_a_real_sympy_erf_expression():
    facts = analyze_source(erf_fn)
    lifted = lift(erf_fn, facts)
    assert lifted is not None
    assert lifted.expr.has(sympy.erf)


def test_erfc_lifts_to_a_real_sympy_erfc_expression():
    facts = analyze_source(erfc_fn)
    lifted = lift(erfc_fn, facts)
    assert lifted is not None
    assert lifted.expr.has(sympy.erfc)


def test_erf_is_odd():
    results = check_conjectures(erf_fn, [claim("f(-x) == -f(x)", route="derive")])
    assert results[0].verdict == "proven"


def test_erfc_reflection_identity():
    # erfc(-x) == 2 - erfc(x), the complement's own point-symmetry
    results = check_conjectures(erfc_fn, [claim("f(-x) == 2 - f(x)", route="derive")])
    assert results[0].verdict == "proven"


@pytest.mark.needs_full_proof_budget
def test_erf_plus_erfc_is_the_constant_one():
    # the defining relation, erfc(x) = 1 - erf(x), plain simplify()/
    # .equals() alone don't apply this rewrite (confirmed directly against
    # sympy), which is exactly why _proof_support.py's equality path
    # gained a targeted diff.rewrite(sympy.erf) retry, scoped to
    # expressions that actually contain erf/erfc.
    results = check_conjectures(erf_plus_erfc, [claim("f(x) == 1", route="derive")])
    assert results[0].verdict == "proven"


def test_normal_cdf_derivative_is_the_normal_pdf_and_nonnegative():
    # monotonicity via derivative sign, erf'(x) = 2/sqrt(pi)*exp(-x^2)
    # is always positive, no boundedness fact needed for this one
    results = check_conjectures(normal_cdf, [claim("d(f(x), x) >= 0", route="derive")])
    assert results[0].verdict == "proven"


def test_normal_cdf_at_zero_is_one_half():
    results = check_conjectures(normal_cdf, [claim("f(0) == 0.5", route="derive")])
    assert results[0].verdict == "proven"


def test_normal_cdf_bounds_prove_by_interval_evaluation():
    # This used to be a documented, honest gap: sympy's erf(x) carries
    # no is_extended_nonnegative fact even for a real symbol, so
    # ask(Q.nonnegative(1 - erf(x))) couldn't close a bounds claim.
    # The interval-evaluation pass closed it, erf's global range
    # [-1, 1] is a known bounded-function fact, so both CDF bounds now
    # prove rigorously, with the interval stated in the sketch.
    results = check_conjectures(normal_cdf, [claim("f(x) >= 0", route="derive")])
    assert results[0].verdict == "proven"
    assert "interval evaluation" in results[0].sketch
    results = check_conjectures(normal_cdf, [claim("f(x) <= 1", route="derive")])
    assert results[0].verdict == "proven"
