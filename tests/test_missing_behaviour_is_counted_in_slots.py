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


def _refilled(fn, xs):
    from mathema._missing_policy import refill

    def call_at(point):
        return fn(**point), None
    return [b for *_rest, b in refill(call_at, {"xs": xs}, fn(xs=xs), None,
                                      {"xs": (0.0, 1.0)})]


def test_a_moved_hole_propagates():
    def reversed_(xs):
        return [2.0 * v for v in reversed(xs)]
    assert _refilled(reversed_, [1.0, NAN]) == ["propagates"]


def test_holes_at_the_same_positions_in_two_arguments_are_one_union():
    assert classify_call({"xs": [NAN, 1.0], "ys": [NAN, 1.0]}, [NAN, 2.0]) == "propagates"
    assert classify_call({"xs": [NAN, 1.0], "ys": [1.0, NAN]}, [NAN, NAN]) == "propagates"


def test_the_union_is_a_control_on_position_and_count():
    assert classify_call({"xs": [NAN, 1.0], "ys": [NAN, 1.0]}, [NAN, NAN]) == "introduces"
    assert classify_call({"xs": [NAN, 1.0], "ys": [1.0, NAN]}, [NAN, 2.0]) == "introduces"


def test_a_reduction_carries_one_hole_into_its_one_slot():
    assert classify_call({"xs": [NAN, NAN, 1.0]}, NAN) == "propagates"
    assert classify_call({"xs": [NAN, 1.0]}, 1.0) == "drops"


def test_a_hole_spread_over_every_slot_propagates():
    def spread(xs):
        return [sum(xs)] * len(xs)
    assert _refilled(spread, [1.0, NAN, 2.0]) == ["propagates"]
    assert classify_call({"xs": [1.0, NAN, 2.0]}, [1.0, NAN, 2.0]) == "propagates"


def test_holes_from_complete_inputs_are_introduced():
    def shifted(xs):
        return [NAN] + list(xs[:-1])
    assert _refilled(shifted, [1.0, NAN, 2.0]) == ["introduces"]


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
    assert table.mixed() == {"xs": {"nan": {"propagates": "xs = [nan]",
                                            "drops": "xs = [nan, 1.0]"}}}


def test_a_call_with_no_missing_input_files_nothing():
    table = PolicyTable()
    table.add({"x": 1.0}, NAN)
    assert table.summary() == {}


# converts is a change of kind, never of member spelling --------------

def test_an_absent_argument_returned_as_a_hole_converts():
    def fill(x):
        return float("nan") if x is None else x
    assert classify_call({"x": None}, fill(None)) == "converts"


def test_a_hole_returned_as_an_absent_output_converts():
    pd = pytest.importorskip("pandas")

    def absent_if_missing(v):
        return None if pd.isna(v) else v
    assert classify_call({"v": NAN}, absent_if_missing(NAN)) == "converts"


def test_a_null_slot_returned_as_nan_propagates_and_says_so():
    pd = pytest.importorskip("pandas")
    from mathema.probing import ExecutedMissing

    values = [0.2, None]
    out = pd.Series(values, dtype=float)
    assert classify_call({"values": values}, out) == "propagates"
    record = ExecutedMissing()
    record.add_call({"values": values}, output=out)
    assert record.meta()["executed"] == {
        "values": {"null": "null slot in, nan out (propagates, member changed: "
                           "values[1]=None returned as nan)"}}
    assert record.meta()["behaviour"] == {"values": {"null": "propagates"}}


# the claim's words over an all-hole vector ---------------------------

@pytest.mark.parametrize("word, expected", [
    ("sum", 0.0), ("prod", 1.0), ("count", 0), ("norm", 0.0),
])
def test_a_reduction_with_an_identity_gives_it_over_no_value(word, expected):
    np = pytest.importorskip("numpy")
    from mathema._linalg_eval import FUNCTIONS
    assert FUNCTIONS[word](np.array([NAN, NAN])) == expected


def test_a_dot_over_no_shared_value_is_zero():
    np = pytest.importorskip("numpy")
    from mathema._linalg_eval import FUNCTIONS
    assert FUNCTIONS["dot"](np.array([NAN, NAN]), np.array([0.5, 0.5])) == 0.0


@pytest.mark.parametrize("word", ["mean", "std", "var", "min", "max", "median"])
def test_a_reduction_without_an_identity_is_a_hole_over_no_value(word):
    np = pytest.importorskip("numpy")
    from mathema._linalg_eval import FUNCTIONS
    assert math.isnan(FUNCTIONS[word](np.array([NAN, NAN])))


def test_a_quantile_over_no_value_is_a_hole():
    np = pytest.importorskip("numpy")
    from mathema._linalg_eval import FUNCTIONS
    assert math.isnan(FUNCTIONS["quantile"](np.array([NAN, NAN]), 0.5))


def test_two_vectors_added_elementwise_propagate_each_hole():
    np = pytest.importorskip("numpy")
    import mathema

    def added(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        return xs + ys
    rec = mathema.check(added, claims=[mathema.claim(
        "for xs in [0, 1]^n, ys in [0, 1]^n, f(xs, ys) >= 0", name="c")])
    rows = {p.name: p for p in rec.probes}
    assert (rows["missing[xs]"].verdict, rows["missing[ys]"].verdict) == ("holds", "holds")
