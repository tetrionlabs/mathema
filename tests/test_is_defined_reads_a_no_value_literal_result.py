# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function that returns a nan or an infinity has no value there, the
same as a call that raises. A literal nan or infinity reaching the
returned value (math.nan, math.inf, numpy.nan, float("nan"), a module
constant holding one) marks a no-value region, so `is_defined` is never
proven over a body that hands one back, and the executed witness says
where. A literal that only takes part in a comparison, or that a clamp
absorbs, leaves every result a value."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.symbolic._partiality import NO_VALUE, partiality_walk
from mathema.analysis import effective_facts

NAN = float("nan")


def nan_above_zero(x: float) -> float:
    return x if x <= 0 else math.nan


def inf_at_zero(x: float) -> float:
    return 1.0 / x if x != 0 else math.inf


def negative_inf_below(x: float) -> float:
    if x < -1:
        return -math.inf
    return x


def numpy_nan_above(x: float) -> float:
    import numpy
    return x if x <= 2 else numpy.nan


def float_text_nan_above(x: float) -> float:
    return x if x <= 2 else float("nan")


def module_nan_above(x: float) -> float:
    return x if x <= 2 else NAN


def nan_through_a_name(x: float) -> float:
    y = math.nan if x > 3 else x
    return 2 * y


def nan_inside_a_loop(x: float) -> float:
    total = 0.0
    for _ in range(2):
        total += x if x <= 0 else math.nan
    return total / 2


def overflowing_product(x: float) -> float:
    if x > 0:
        return 0.0 * (1e308 * 10.0)
    return x


def infinity_minus_infinity(x: float) -> float:
    return x if x <= 1 else 1e308 * 10 - 1e308 * 10


def overflow_through_a_name(x: float) -> float:
    big = 1e308 * x * 10.0
    return x if x <= 1 else big - big


def zero_times_infinity(x: float) -> float:
    return x if x <= 1 else 0.0 * math.inf


def infinity_minus_itself(x: float) -> float:
    return x if x <= 1 else math.inf - math.inf


def compares_with_infinity(x: float) -> float:
    return x if x < math.inf else 0.0


def clamps_with_infinity(x: float) -> float:
    return min(x, math.inf)


def zero_where_nan(x: float) -> float:
    return 0.0 if math.isnan(x) else x


def _verdict(fn, text="for x in [-10, 10], is_defined(f)"):
    (p,) = check_conjectures(fn, [claim(text)])
    return p


def test_a_nan_branch_falsifies_is_defined_with_its_witness():
    p = _verdict(nan_above_zero)
    assert p.verdict == "falsified", (p.route, p.note, p.sketch)
    assert p.counterexample, p


def test_the_bare_predicate_is_not_proven_over_a_nan_branch():
    p = _verdict(nan_above_zero, "is_defined(f)")
    assert p.verdict == "falsified", (p.route, p.note, p.sketch)


def test_an_infinity_at_one_point_is_found_exactly():
    p = _verdict(inf_at_zero)
    assert p.verdict == "falsified", (p.route, p.note, p.sketch)
    assert "x = 0" in p.counterexample, p.counterexample


def test_a_negative_infinity_branch_falsifies():
    p = _verdict(negative_inf_below)
    assert p.verdict == "falsified", (p.route, p.note, p.sketch)


def test_every_spelling_of_nan_is_a_no_value_region():
    for fn in (float_text_nan_above, module_nan_above,
               nan_through_a_name):
        guards, _unread = partiality_walk(fn, effective_facts(fn))
        assert any(exc == NO_VALUE for _cond, exc in guards), fn.__name__
        p = _verdict(fn)
        assert p.verdict == "falsified", (fn.__name__, p.route, p.note)


def test_a_nan_inside_a_loop_is_not_proven_defined():
    _guards, unread = partiality_walk(nan_inside_a_loop,
                                      effective_facts(nan_inside_a_loop))
    assert unread is not None
    p = _verdict(nan_inside_a_loop)
    assert p.verdict == "falsified", (p.route, p.note, p.sketch)


def test_a_literal_that_never_reaches_the_result_keeps_the_proof():
    for fn in (compares_with_infinity, clamps_with_infinity, zero_where_nan):
        guards, unread = partiality_walk(fn, effective_facts(fn))
        assert guards == [] and unread is None, (fn.__name__, guards, unread)
        p = _verdict(fn)
        assert p.verdict == "proven", (fn.__name__, p.route, p.note)


def test_an_arithmetic_of_finite_literals_is_read_as_written():
    # 1e308 * 10.0 is 10**309, a finite number; 0 * 10**309 and
    # 10**309 - 10**309 are 0: only the float64 run overflows
    for fn in (overflowing_product, infinity_minus_infinity,
               overflow_through_a_name):
        guards, _unread = partiality_walk(fn, effective_facts(fn))
        assert not any(exc == NO_VALUE for _c, exc in guards), fn.__name__
        p = _verdict(fn)
        assert p.verdict == "proven", (fn.__name__, p.route, p.sketch)


def test_an_infinity_literal_times_zero_has_no_value():
    for fn in (zero_times_infinity, infinity_minus_itself):
        guards, _unread = partiality_walk(fn, effective_facts(fn))
        assert any(exc == NO_VALUE for _cond, exc in guards), fn.__name__
        p = _verdict(fn)
        assert p.verdict == "falsified", (fn.__name__, p.route, p.sketch)


def test_numpy_nan_is_a_no_value_region():
    pytest.importorskip("numpy")
    guards, _unread = partiality_walk(numpy_nan_above,
                                      effective_facts(numpy_nan_above))
    assert any(exc == NO_VALUE for _cond, exc in guards)
    p = _verdict(numpy_nan_above)
    assert p.verdict == "falsified", (p.route, p.note)
