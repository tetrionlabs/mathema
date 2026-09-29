# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A missing value meets a relation by its kind: a hole agrees with a
hole under `==`/`~=` whatever member spells it, an absence agrees with
an absence, an absence and a hole disagree, and a missing value against
a number fails every relation, `!=` included; an ordering at a missing
value fails. A raise at an admitted missing value is a counterexample.
Membership in `{missing}`, `{nan}` or `{None}` is decided by the domain,
resolved against the value tested. The same rule holds on every route."""
import math

import pytest

from mathema.conjecture import claim, check_conjectures
from mathema.probing import (inputs_missing, missing_class, missing_relation,
                             relation_holds_elementwise, values_agree)
from tests.test_missing_values_core import (FALSIFIED, PROVEN, add, assert_row,
                                            double_or_missing, ident, sqrt_guarded,
                                            sqrt_plain, zero_if_missing)

NAN = float("nan")
pd = pytest.importorskip("pandas")


@pytest.mark.parametrize("value, kind", [
    (None, "absent"), (NAN, "hole"), (pd.NA, "hole"), (pd.NaT, "hole"),
    (0.0, None), ([NAN], None), ("", None),
])
def test_a_value_has_one_kind(value, kind):
    assert missing_class(value) == kind


@pytest.mark.parametrize("lv, rv, relation, expected", [
    (NAN, NAN, "==", True),
    (NAN, pd.NA, "==", True),       # a NaN in, a pd.NA out: one hole propagated
    (NAN, NAN, "~=", True),
    (NAN, NAN, "!=", False),
    (None, None, "==", True),
    (None, None, "!=", False),
    (None, NAN, "==", False),
    (None, NAN, "!=", True),
    (NAN, 1.0, "==", False),
    (NAN, 1.0, "!=", False),        # against a number every relation fails
    (None, 1.0, "!=", False),
    (NAN, 0.0, ">=", False),
    (NAN, NAN, "<=", False),        # an ordering at a missing value fails
])
def test_the_kind_rule(lv, rv, relation, expected):
    assert missing_relation(lv, rv, relation) is expected
    assert relation_holds_elementwise(lv, rv, relation, 1e-9,
                                      missing_inputs=True) is expected


def test_neither_side_missing_is_left_to_the_ordinary_comparison():
    assert missing_relation(1.0, 2.0, "<") is None


def test_vectors_agree_hole_for_hole_and_number_for_number():
    assert relation_holds_elementwise([1.0, NAN], [1.0, NAN], "==", 1e-9,
                                      missing_inputs=True) is True
    assert relation_holds_elementwise([1.0, NAN], [2.0, NAN], "==", 1e-9,
                                      missing_inputs=True) is False
    assert relation_holds_elementwise([1.0, NAN], [1.0, 3.0], "==", 1e-9,
                                      missing_inputs=True) is False
    assert relation_holds_elementwise([1.0, NAN], [1.0, 3.0], "!=", 1e-9,
                                      missing_inputs=True) is False
    assert values_agree([None, 2.0], [None, 2.0], missing_inputs=True) is True


def test_an_input_is_missing_when_it_is_or_holds_a_missing_value():
    assert inputs_missing([None, 1.0])
    assert inputs_missing([[1.0, NAN]])
    assert inputs_missing([pd.Series([1.0, None])])
    assert not inputs_missing([1.0, [2.0, 3.0]])


def test_without_a_missing_input_a_nan_agrees_with_nothing():
    assert relation_holds_elementwise(NAN, NAN, "==", 1e-9) is False


# --- the battery rows this rule settles (84 sections 2 and 3) -----------

def test_s3_absence_raising_falsifies_the_claim():
    assert_row(sqrt_plain, "for x in {0.25, None}, f(x) >= 0", FALSIFIED,
               member="None", raised="TypeError")


def test_s4_a_hole_against_an_ordering_falsifies():
    assert_row(sqrt_plain, "for x in {0.25, nan}, f(x) >= 0", FALSIFIED, member="nan")


def test_s8_absence_against_a_number_falsifies():
    assert_row(double_or_missing, "for x in {0.25, None}, f(x) >= 0", FALSIFIED,
               member="None")


@pytest.mark.parametrize("text, value", [
    ("for x in {0.25, None}, f(x) == x", "None"),
    ("for x in {0.25, nan}, f(x) == x", "nan"),
])
def test_s12_s13_the_same_kind_agrees_by_execution(text, value):
    assert_row(ident, text, PROVEN, executed={"x": [value]})


@pytest.mark.parametrize("route", ["best", "probe"])
def test_the_same_rows_hold_on_the_probe(route):
    (p,) = [p for p in check_conjectures(
        ident, [claim("for x in {0.25, None, nan}, f(x) == x", route=route)])]
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)
    (q,) = [p for p in check_conjectures(
        sqrt_plain, [claim("for x in {0.25, None}, f(x) >= 0", route=route)])
            if "[" not in p.name]
    assert q.verdict == "falsified" and "None" in q.counterexample


def test_s16_a_listed_absence_is_executed_against_the_other_parameter():
    assert_row(add, "for x in [0, 1], y in {0.5, None}, f(x, y) >= 0", FALSIFIED,
               member="None", raised="TypeError", executed={"y": ["None"]})


def test_p1_a_hole_that_returns_is_not_a_raise():
    assert_row(sqrt_plain, "for x in {missing}, raises(f(x))", FALSIFIED, member="nan")


def test_p2_the_hole_raises_the_stated_exception():
    assert_row(sqrt_guarded, "for x in {missing}, raises(f(x), ValueError)", PROVEN)


def test_p3_a_replaced_hole_equals_its_replacement():
    assert_row(zero_if_missing, "for x in {missing}, f(x) == 0", PROVEN)


def test_p4_membership_is_by_class_resolved_against_the_value():
    assert_row(double_or_missing, "for x in {missing}, f(x) in {missing}", PROVEN)
    assert_row(zero_if_missing, "for x in {missing}, f(x) in {missing}", FALSIFIED)


def test_a_membership_in_an_interval_admits_no_missing_value():
    assert_row(double_or_missing, "for x in {nan}, f(x) in [0, 10]", FALSIFIED)


def test_absence_is_in_none_and_not_in_missing():
    assert_row(double_or_missing, "for x in {None}, f(x) in {None}", PROVEN)
    assert_row(double_or_missing, "for x in {None}, f(x) in {missing}", FALSIFIED)


def test_the_executed_rung_of_equivalence_agrees_by_kind():
    def g(x):
        return x * 1.0 if x is not None else None
    (p,) = check_conjectures(ident, [claim("for x in {0.5, None, nan}, f =:= g",
                                           funcs={"g": g})])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)
    assert math.isnan(NAN)
