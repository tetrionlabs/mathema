# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim is judged wherever the function returns a value, a
missing input it drops included, and never where it returns a missing
value or raises at a missing input: that point is classified, its
behaviour recorded in `meta["mathema.missing"]`, and not compared. A
value claim with no judged point is `unknown`. Membership in
`{missing}`, `{nan}` or `{absent}` asks about the missing output itself
and is judged everywhere. The same rule holds on every route."""
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.probing import classified, inputs_missing, relation_holds_elementwise
from tests.test_missing_values_core import (PROVEN, add, assert_row,
                                            double_or_missing, ident, sqrt_guarded,
                                            sqrt_plain, zero_if_missing)

NAN = float("nan")
pd = pytest.importorskip("pandas")
FALSIFIED = ("falsified",)


def behaviour(probe) -> dict:
    return ((probe.meta or {}).get("mathema.missing") or {}).get("behaviour") or {}


def test_a_point_is_classified_at_a_missing_input_with_no_value_out():
    assert classified([NAN], [NAN])
    assert classified([None], [], raised=True)
    assert classified([[1.0, NAN]], [[2.0, NAN]])
    assert not classified([NAN], [0.0])            # the function dropped it
    assert not classified([0.5], [NAN])            # a NaN from present inputs


def test_an_input_is_missing_when_it_is_or_holds_a_missing_value():
    assert inputs_missing([None, 1.0])
    assert inputs_missing([[1.0, NAN]])
    assert inputs_missing([pd.Series([1.0, None])])
    assert not inputs_missing([1.0, [2.0, 3.0]])


def test_a_nan_agrees_with_nothing_in_an_ordinary_comparison():
    assert relation_holds_elementwise(NAN, NAN, "==", 1e-9) is False
    assert relation_holds_elementwise(0.0, NAN, ">=", 1e-9) is False


# --- the battery rows this rule settles (84 sections 2 and 3, FM3) -----

def test_s3_a_raise_at_a_listed_absence_is_classified():
    probe, _ = assert_row(sqrt_plain, "for x in {0.25, None}, f(x) >= 0", PROVEN)
    assert behaviour(probe) == {"x": {"None": "raises"}}


def test_s4_a_propagated_hole_is_classified():
    probe, _ = assert_row(sqrt_plain, "for x in {0.25, nan}, f(x) >= 0", PROVEN)
    assert behaviour(probe) == {"x": {"nan": "propagates"}}


def test_s8_a_propagated_absence_is_classified():
    probe, _ = assert_row(double_or_missing, "for x in {0.25, None}, f(x) >= 0", PROVEN)
    assert behaviour(probe) == {"x": {"None": "propagates"}}


@pytest.mark.parametrize("text, member", [
    ("for x in {0.25, None}, f(x) == x", "None"),
    ("for x in {0.25, nan}, f(x) == x", "nan"),
])
def test_s12_s13_propagation_is_classified_by_execution(text, member):
    probe, _ = assert_row(ident, text, PROVEN, executed={"x": [member]})
    assert behaviour(probe) == {"x": {member: "propagates"}}


@pytest.mark.parametrize("route, verdict", [("best", "proven"), ("probe", "holds")])
def test_the_same_rows_hold_on_the_probe(route, verdict):
    (p,) = [p for p in check_conjectures(
        ident, [claim("for x in {0.25, None, nan}, f(x) == x", route=route)])]
    assert p.verdict == verdict, (p.verdict, p.note)
    (q,) = [p for p in check_conjectures(
        sqrt_plain, [claim("for x in {0.25, None}, f(x) >= 0", route=route)])
            if "[" not in p.name]
    assert q.verdict == verdict, (q.verdict, q.note)


def test_s16_a_listed_absence_at_the_second_parameter_is_classified():
    probe, _ = assert_row(add, "for x in [0, 1], y in {0.5, None}, f(x, y) >= 0",
                          PROVEN, executed={"y": ["None"]})
    assert behaviour(probe) == {"y": {"None": "raises"}}


def test_a_value_claim_with_no_judged_point_is_unknown():
    (p,) = check_conjectures(sqrt_plain, [claim("for x in {missing}, f(x) >= 0")])
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert p.note.startswith("the only listed point, x = nan, gives nan back, so "
                             "there is no value to compare with >= 0.")
    assert "`missing(f, x) propagates`" in p.note


def test_a_dropped_hole_is_judged_on_the_value_returned():
    assert_row(zero_if_missing, "for x in {missing}, f(x) == 0", PROVEN)
    probe, _ = assert_row(zero_if_missing, "for x in {0.5, nan}, f(x) == x", FALSIFIED)
    assert "nan" in probe.counterexample


def test_a_none_from_present_inputs_is_no_value():
    def lookup(x: float):
        return None if x > 0.5 else x
    (p,) = check_conjectures(lookup, [claim("for x in {0.25, 0.75}, f(x) >= 0")])
    assert p.verdict == "falsified" and "0.75" in p.counterexample


def test_p1_a_hole_that_returns_is_not_a_raise():
    assert_row(sqrt_plain, "for x in {missing}, raises(f(x))", FALSIFIED, member="nan")


def test_p2_the_hole_raises_the_stated_exception():
    assert_row(sqrt_guarded, "for x in {missing}, raises(f(x), ValueError)", PROVEN)


def test_p4_membership_is_by_class_resolved_against_the_value():
    assert_row(double_or_missing, "for x in {missing}, f(x) in {missing}", PROVEN)
    assert_row(zero_if_missing, "for x in {missing}, f(x) in {missing}", FALSIFIED)


def test_a_membership_in_an_interval_is_a_value_claim():
    probe, _ = assert_row(double_or_missing, "for x in {nan}, f(x) in [0, 10]",
                          ("unknown",))
    assert behaviour(probe) == {"x": {"nan": "propagates"}}


def test_absence_is_in_absent_and_not_in_missing():
    assert_row(double_or_missing, "for x in {None}, f(x) in {None}", PROVEN)
    assert_row(double_or_missing, "for x in {None}, f(x) in {missing}", FALSIFIED)


def test_the_executed_rung_of_equivalence_judges_value_points_only():
    def g(x):
        return x * 1.0 if x is not None else None
    (p,) = check_conjectures(ident, [claim("for x in {0.5, None, nan}, f =:= g",
                                           funcs={"g": g})])
    assert p.verdict == "holds", (p.verdict, p.note)
