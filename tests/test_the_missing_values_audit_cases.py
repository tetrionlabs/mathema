# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Cases where a policy row, a gate or a value claim once claimed more
than the calls showed: each pins the verdict the calls support."""
from typing import Optional

import pytest

from mathema import analyze
from mathema.conjecture import check_conjectures, claim
from mathema.policy import guard_policies


def _rows(fn, *texts):
    return {r.name: r for r in check_conjectures(fn, [claim(t) for t in texts])}


# --- a guard covers x only when the raise depends on x alone -------------

def raise_unless_y(x: Optional[float], y: float) -> float:
    if x is None and y != 0.125:
        raise TypeError("x is None")
    if x is None:
        return 0.0
    return x + y


def either_missing(x: Optional[float]) -> float:
    if x is None or x != x:
        raise ValueError("x is missing")
    return x


def test_a_guard_that_also_reads_another_parameter_covers_nothing():
    assert ("x", "absent", "None") not in guard_policies(analyze(raise_unless_y))
    gate = _rows(raise_unless_y, "for x in [0, 1], y in [0, 1], f(x, y) >= 0",
                 "is_absent_safe(f)")["is_absent_safe[f]"]
    assert gate.verdict != "proven", gate.note


def test_a_guard_joined_by_or_covers_each_of_its_tests():
    guards = guard_policies(analyze(either_missing))
    assert guards[("x", "absent", "None")][0] == "raises"
    assert guards[("x", "missing", "nan")][0] == "raises"


# --- a library row speaks for a parameter only while the body leaves it be

np = pytest.importorskip("numpy")


def mean_after_fill(xs: np.ndarray) -> float:
    if len(xs) > 20:
        xs = np.nan_to_num(xs)
    return float(np.mean(xs))


def test_no_library_row_is_composed_when_the_body_rebinds_the_parameter():
    from mathema.policy import composed_policies
    assert composed_policies(mean_after_fill, analyze(mean_after_fill)) == {}


# --- a call holding two members keeps its own raise -----------------------

def refuses_two_kinds(xs: list) -> float:
    has_null = any(x is None for x in xs)
    has_nan = any(x is not None and x != x for x in xs)
    if has_null and has_nan:
        raise ValueError("both kinds of hole")
    return sum(x for x in xs if x is not None and x == x)


def test_a_raise_at_two_members_together_is_recorded():
    rows = _rows(refuses_two_kinds, "for xs in [0, 1]^n, f(xs) >= 0",
                 "missing(f, xs) drops", "is_missing_safe(f)")
    assert rows["missing_f_xs_drops"].verdict == "falsified"
    assert rows["missing_f_xs_drops"].counterexample.endswith("f raised ValueError")
    assert rows["is_missing_safe[f]"].verdict == "falsified"


# --- the floor meets every other parameter at its corners -----------------

def zero_at_the_top(x: float, y: float) -> float:
    z = x * y
    return 0.0 if (z != z and y >= 0.99) else z


def test_a_stated_row_is_tried_with_the_other_parameter_at_its_corners():
    # the function's domain bounds y; the row's own floor meets y at 0 and 1
    space = claim("for x in [0, 1], y in [0, 1], f(x, y) >= 0").domain
    rows = {r.name: r for r in check_conjectures(zero_at_the_top, [
        claim("missing(f, x) propagates"), claim("is_missing_safe(f)")], domain=space)}
    assert rows["missing_f_x_propagates"].verdict == "falsified"
    assert rows["missing_f_x_propagates"].counterexample == \
        "x = nan, y = 1.0: f returned 0.0"
    assert rows["is_missing_safe[f]"].verdict != "proven"


# --- the empty input -------------------------------------------------------

def empty_unless_half(xs: np.ndarray, y: float) -> float:
    if len(xs) == 0 and y != 0.5:
        raise ValueError("empty")
    return float(np.mean(xs))


def mean_in_an_array(xs: np.ndarray):
    return np.array([np.mean(xs)])


def standardised(xs: np.ndarray):
    return (xs - xs.mean()) / xs.std()


def test_an_emptiness_check_that_also_reads_another_parameter_is_no_guard():
    from mathema.hazards import _emptiness_guard_params
    assert "xs" not in _emptiness_guard_params(analyze(empty_unless_half))


def test_an_array_holding_a_hole_for_the_empty_input_fails():
    (row,) = check_conjectures(mean_in_an_array, [claim("is_empty_safe(xs)")])
    assert row.verdict == "falsified", row.note
    assert "for the empty input" in row.counterexample


def test_an_empty_array_for_the_empty_input_passes():
    (row,) = check_conjectures(standardised, [claim("is_empty_safe(xs)")])
    assert row.verdict == "proven", (row.verdict, row.counterexample)


# --- a hole of any member from present inputs is no value ------------------

pd = pytest.importorskip("pandas")


def na_at_the_top(x: float) -> float:
    return pd.NA if x > 0.9 else x


def nat_at_the_top(x: float):
    return pd.NaT if x > 0.9 else x


def decimal_nan_at_the_top(x: float):
    import decimal
    return decimal.Decimal("NaN") if x > 0.9 else decimal.Decimal(str(x))


def test_na_nat_and_a_decimal_nan_from_present_inputs_fail_a_value_claim():
    for fn, word in ((na_at_the_top, "NA"), (nat_at_the_top, "NaT"),
                     (decimal_nan_at_the_top, "nan")):
        for text in ("for x in [0, 1] \\ {missing}, f(x) != 5",
                     "for x in [0, 1] \\ {missing}, f(x) <= 1"):
            (row,) = check_conjectures(fn, [claim(text)])
            assert row.verdict == "falsified", (fn.__name__, text, row.note)
            assert row.counterexample.endswith(f"f returned {word}"), row.counterexample


# --- a raise the hole did not cause says nothing about the hole ------------

def root_plus(x: float, y: float) -> float:
    import math
    return math.sqrt(x) + y


def distinct_total(xs: list) -> float:
    vals = [x for x in xs if x is not None and x == x]
    if len(set(vals)) != len(vals):
        raise ValueError("duplicate values")
    return sum(vals)


def test_a_raise_from_another_parameter_is_not_the_holes():
    from mathema._missing_policy import INCONCLUSIVE, refill

    def call_at(point):
        try:
            return root_plus(**point), None
        except Exception as exc:
            return None, type(exc).__name__
    out = refill(call_at, {"x": -8.77, "y": float("nan")}, None, "ValueError",
                 {"x": 0.5, "y": 0.5})
    assert [b for *_r, b in out] == [INCONCLUSIVE]


def test_a_raise_the_filled_call_repeats_is_not_the_holes():
    row = _rows(distinct_total, "missing(f, xs) drops")["missing_f_xs_drops"]
    assert row.verdict != "falsified", (row.verdict, row.counterexample)
