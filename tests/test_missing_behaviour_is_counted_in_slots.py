# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a function does at a missing input is one of five behaviours,
`raises`, `drops`, `propagates`, `converts` or `introduces`, read by
counting no-value slots in the inputs and the output, the same five for
an absence and for a hole, on scalars, lists, arrays, Series, tables
and a record's optional field. Each behaviour has a case that is it and
a control that is not."""
import math

import pytest

from mathema._missing_policy import (PolicyTable, classify_call, keys_of,
                                     no_value_slots)

NAN = math.nan


# scalars ------------------------------------------------------------

@pytest.mark.parametrize("inputs, output, raised, behaviour", [
    ({"x": NAN}, None, "ValueError", "raises"),
    ({"x": NAN}, 0.0, None, "drops"),
    ({"x": NAN}, NAN, None, "propagates"),
    ({"x": None}, None, None, "propagates"),
    ({"x": None}, NAN, None, "converts"),
    ({"x": NAN}, None, None, "converts"),
    ({"x": None}, 1.0, None, "drops"),
    ({"x": NAN, "y": 1.0}, NAN, None, "propagates"),
])
def test_a_scalar_call_is_one_behaviour(inputs, output, raised, behaviour):
    assert classify_call(inputs, output, raised) == behaviour


@pytest.mark.parametrize("inputs, output, not_this", [
    ({"x": NAN}, 1.0, "propagates"),     # a value out is no propagation
    ({"x": NAN}, NAN, "drops"),          # a hole out is no drop
    ({"x": None}, None, "converts"),     # the kind kept is no conversion
    ({"x": NAN}, NAN, "raises"),         # a return is no raise
])
def test_a_scalar_control_is_not_the_behaviour(inputs, output, not_this):
    assert classify_call(inputs, output) != not_this


def test_a_no_value_from_present_inputs_introduces():
    assert classify_call({"x": 0.0}, NAN) == "introduces"
    assert classify_call({"x": 0.0}, 1.0) == "drops"


# lists --------------------------------------------------------------

def test_a_list_hole_propagates_at_its_position():
    assert classify_call({"xs": [1.0, NAN]}, [2.0, NAN]) == "propagates"


def test_a_moved_hole_is_not_propagation():
    assert classify_call({"xs": [1.0, NAN]}, [NAN, 2.0]) == "introduces"


def test_a_reduction_carries_one_hole_into_its_one_slot():
    assert classify_call({"xs": [NAN, NAN, 1.0]}, NAN) == "propagates"
    assert classify_call({"xs": [NAN, 1.0]}, 1.0) == "drops"


def test_extra_holes_are_introduced():
    assert classify_call({"xs": [1.0, NAN, 2.0]}, [NAN, NAN, NAN]) == "introduces"
    assert classify_call({"xs": [1.0, NAN, 2.0]}, [1.0, NAN, 2.0]) == "propagates"


def test_a_none_element_is_the_null_hole():
    slots = no_value_slots([1.0, None])
    assert [(s.kind, s.member) for s in slots.slots] == [("missing", "null")]
    assert classify_call({"xs": [1.0, None]}, None, "TypeError") == "raises"
    assert classify_call({"xs": [1.0, None]}, [1.0, NAN]) == "propagates"


def test_the_keys_name_every_member_a_list_holds():
    assert keys_of({"xs": [None, NAN, 1.0]}) == [("xs", "missing", "null"),
                                                 ("xs", "missing", "nan")]
    assert keys_of({"xs": [1.0]}) == []
    assert keys_of({"xs": None}) == [("xs", "absent", "None")]


# numpy --------------------------------------------------------------

def test_numpy_holes_are_counted_by_position():
    np = pytest.importorskip("numpy")
    xs = np.array([1.0, np.nan, 3.0])
    assert classify_call({"xs": xs}, xs * 2) == "propagates"
    assert classify_call({"xs": xs}, np.nan_to_num(xs)) == "drops"
    assert classify_call({"xs": xs}, float(np.mean(xs))) == "propagates"
    assert classify_call({"xs": xs}, float(np.nanmean(xs))) == "drops"


def test_a_numpy_matrix_hole_is_an_entry():
    np = pytest.importorskip("numpy")
    A = np.array([[1.0, np.nan], [0.0, 1.0]])
    assert [s.position for s in no_value_slots(A).slots] == [(0, 1)]
    assert classify_call({"A": A}, A @ A.T) == "introduces"
    assert classify_call({"A": A}, A.copy()) == "propagates"


# pandas -------------------------------------------------------------

def test_pandas_members_are_named():
    pd = pytest.importorskip("pandas")
    s = pd.Series([1.0, None, 3.0], dtype="Float64")
    assert [sl.member for sl in no_value_slots(s).slots] == ["NA"]
    assert classify_call({"xs": s}, float(s.mean())) == "drops"
    assert classify_call({"xs": s}, s.shift(1)) == "introduces"
    assert classify_call({"xs": s}, s * 2) == "propagates"


def test_a_pandas_table_names_its_column():
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"w": [1.0, float("nan")], "r": [0.5, 0.5]})
    assert [s.position for s in no_value_slots(df).slots] == [("w", 1)]
    assert classify_call({"df": df}, float((df.w * df.r).sum())) == "drops"
    assert classify_call({"df": df}, df.fillna(0.0)) == "drops"
    assert classify_call({"df": df}, df * 1.0) == "propagates"


# polars -------------------------------------------------------------

def test_polars_null_and_nan_are_two_members():
    pl = pytest.importorskip("polars")
    s = pl.Series([1.0, None, float("nan")])
    assert [sl.member for sl in no_value_slots(s).slots] == ["null", "nan"]
    table = PolicyTable()
    table.add({"xs": pl.Series([1.0, None])}, pl.Series([1.0, None]).mean())
    table.add({"xs": pl.Series([1.0, float("nan")])},
              pl.Series([1.0, float("nan")]).mean())
    assert table.summary() == {"xs": {"null": "drops", "nan": "propagates"}}


# a record's optional field ------------------------------------------

def test_a_none_field_is_the_fields_absence():
    pydantic = pytest.importorskip("pydantic")

    class Order(pydantic.BaseModel):
        qty: int
        note: "str | None" = None

    slots = no_value_slots(Order(qty=1))
    assert [(s.position, s.kind, s.member) for s in slots.slots] == \
        [(("note",), "absent", "None")]
    assert classify_call({"o": Order(qty=1)}, 1) == "drops"
    assert classify_call({"o": Order(qty=1)}, None, "AttributeError") == "raises"
    assert no_value_slots(Order(qty=1, note="x")).slots == ()


# aggregation --------------------------------------------------------

def test_one_behaviour_over_many_calls_is_the_policy():
    table = PolicyTable()
    table.add({"x": NAN}, NAN)
    table.add({"x": NAN, "y": 2.0}, NAN)
    assert table.behaviour(("x", "missing", "nan")) == "propagates"


def test_two_behaviours_are_mixed_with_a_witness_each():
    table = PolicyTable()
    table.add({"xs": [NAN]}, NAN)
    table.add({"xs": [NAN, 1.0]}, 1.0)
    assert table.behaviour(("xs", "missing", "nan")) == "mixed"
    assert table.mixed() == {"xs": {"nan": {"propagates": "xs=[nan]",
                                            "drops": "xs=[nan, 1.0]"}}}


def test_a_call_with_no_missing_input_files_nothing():
    table = PolicyTable()
    table.add({"x": 1.0}, NAN)
    assert table.summary() == {}
