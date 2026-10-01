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


# --- a guard's return is read by what it returns ---------------------------

nan_fill = 0.0


def hole_back(x: float) -> float:
    if x != x:
        return x
    return x + 1.0


def named_fill(x: float) -> float:
    import math
    if math.isnan(x):
        return nan_fill
    return x + 1.0


def none_back(x: Optional[float]) -> Optional[float]:
    if x is None:
        return x
    return x + 1.0


def nan_literal(x: Optional[float]) -> float:
    if x is None:
        return float("nan")
    return x


def test_a_guard_returning_the_parameter_passes_it_on():
    assert guard_policies(analyze(hole_back))[("x", "missing", "nan")][0] == "propagates"
    assert guard_policies(analyze(none_back))[("x", "absent", "None")][0] == "propagates"


def test_a_guard_returning_a_name_that_holds_a_value_drops():
    assert guard_policies(analyze(named_fill))[("x", "missing", "nan")][0] == "drops"


def test_a_guard_returning_nan_for_none_converts():
    assert guard_policies(analyze(nan_literal))[("x", "absent", "None")][0] == "converts"


# --- a subclass of the stated exception satisfies the row ------------------

class MissingInput(ValueError):
    pass


def refuses_none(x: Optional[float]) -> float:
    if x is None:
        raise MissingInput("x is None")
    return x


def test_a_subclass_of_the_stated_exception_satisfies_a_policy_row():
    rows = _rows(refuses_none, "absent(f, x) raises(ValueError)", "is_absent_safe(f)")
    assert rows["absent_f_x_raises_ValueError"].verdict == "proven"
    assert rows["is_absent_safe[f]"].verdict == "proven"


# --- the running extremes in a claim read the value slots ------------------

def test_cummax_and_cummin_in_claim_words_skip_holes_and_keep_them_in_place():
    from mathema._linalg_eval import FUNCTIONS, as_array, shown
    nan = float("nan")
    xs = as_array([nan, 0.2, 0.1, nan, 0.5])
    assert repr(shown(FUNCTIONS["cummax"](xs))) == repr([nan, 0.2, 0.2, nan, 0.5])
    assert repr(shown(FUNCTIONS["cummin"](xs))) == repr([nan, 0.2, 0.1, nan, 0.1])


def series_top(xs: pd.Series) -> float:
    return float(xs.max())


def test_a_claim_through_cummax_holds_where_the_series_skips_holes():
    (row,) = check_conjectures(series_top, [claim(
        "for xs in [0, 1]^n, f(xs) == max(cummax(xs))")])
    assert row.verdict != "falsified", row.counterexample


# --- a library's row speaks for its own runtime type -----------------------

def numpy_mean_of_series(xs: pd.Series) -> float:
    return float(np.mean(xs))


def test_a_numpy_row_is_not_composed_onto_a_pandas_argument():
    from mathema.policy import composed_policies
    assert composed_policies(numpy_mean_of_series, analyze(numpy_mean_of_series)) == {}


# --- a behaviour sentence says only what the calls showed ------------------

def test_the_mixed_sentence_states_only_what_its_witnesses_show():
    from mathema._missing_words import mixed_sentence
    text = mixed_sentence("xs", {"nan": {"raises": "xs = [nan]",
                                         "drops": "xs = [nan, nan, nan]"}},
                          {"nan": "ValueError"}, "array")
    assert text == ("f drops the hole at xs = [nan, nan, nan]; at xs = [nan] it raises "
                    "ValueError instead")


# --- an indifferent call breaks raises and propagates only ---------------

def capped_total(xs: np.ndarray) -> float:
    a = np.asarray(xs, dtype=float)
    if len(a) < 3 and np.isnan(a).any():
        raise ValueError("too short to skip a hole")
    return float(np.minimum(1.0, (np.nansum(a) + 1.0) * 1000.0))


def second(x: float, y: float) -> float:
    return y


def test_a_value_returned_at_the_hole_contradicts_a_stated_raise():
    rows = _rows(capped_total, "for xs in [0, 1]^n, f(xs) >= 0",
                 "missing(f, xs) raises(ValueError)", "is_missing_safe(f)")
    assert rows["missing_f_xs_raises_ValueError"].verdict == "falsified"
    assert rows["is_missing_safe[f]"].verdict == "falsified"


def test_an_indifferent_call_neither_confirms_nor_contradicts_a_drop():
    row = _rows(second, "for x in [0, 1], y in [0, 1], f(x, y) >= 0",
                "missing(f, x) drops")["missing_f_x_drops"]
    assert row.verdict == "unknown", (row.verdict, row.note)


def test_the_indifferent_calls_are_counted():
    (row,) = check_conjectures(second, [claim(
        "for x in [0, 1], y in [0, 1], f(x, y) >= 0", route="probe")])
    counted = row.meta["mathema.missing"]
    assert counted["indifferent"]["x"] >= 1 and "not_read" not in counted


def test_the_gate_is_not_proven_on_indifferent_calls_alone():
    gate = _rows(second, "for x in [0, 1], y in [0, 1], f(x, y) >= 0",
                 "missing(f, x) drops", "missing(f, y) propagates",
                 "is_missing_safe(f)")["is_missing_safe[f]"]
    assert gate.verdict == "unknown", (gate.verdict, gate.note)


def test_an_indifferent_call_does_not_break_converts():
    row = _rows(second, "for x in [0, 1], y in [0, 1], f(x, y) >= 0",
                "missing(f, x) converts")["missing_f_x_converts"]
    assert row.verdict == "unknown", (row.verdict, row.note)


# --- a call that does not repeat is a witness against determinism ----------

def jitter_at_a_hole(x: float, y: float) -> float:
    import random
    return y + (random.random() if x != x else 0.0)


def test_a_refill_that_does_not_repeat_falsifies_is_deterministic():
    rows = {r.name: r for r in check_conjectures(jitter_at_a_hole, [
        claim("for x in [0, 1], y in [0, 1], f(x, y) >= 0", name="c", route="probe"),
        claim("for x in [0, 1] \\ {missing}, y in [0, 1], f(x, y) == f(x, y)",
              name="is_deterministic")])}
    det = rows["is_deterministic"]
    assert det.verdict == "falsified", (det.verdict, det.note)
    assert det.counterexample.startswith("x = nan")


# --- a reading that leaves a premise's region is inconclusive for it -------

def test_a_member_reading_outside_the_premise_is_no_evidence_for_the_row():
    from mathema.policy import Call, _in_region
    nan = float("nan")
    made = {"a": [None, nan]}
    read = Call({"a": [None, 0.5]}, 0.5, None, None, None, "drops", False, made)
    assert not _in_region("count(a) == 0", read)
    assert _in_region("count(a) == 0",
                      Call({"a": [None, None]}, None, None, None, None, "converts"))



# --- a container holding two members reaches f holding both ---------------

def test_a_drawn_container_holding_two_members_is_realised_with_both():
    from mathema.runtime_types import Detection, realise
    nan = float("nan")
    pl = pytest.importorskip("polars")
    series = realise([None, nan, 0.5], Detection("polars.Series", "vec", ""))
    assert series.to_list()[0] is None and series.to_list()[1] != series.to_list()[1]
    frame = realise([None, nan, 0.5], Detection("pandas.Series", "vec", ""))
    assert frame.iloc[0] is None and frame.iloc[1] != frame.iloc[1]
    listed = realise([None, nan, 0.5], Detection("list", "vec", ""))
    assert listed[0] is None and listed[1] != listed[1]
    assert pl.Series([None, nan]).mean() != pl.Series([None, nan]).mean()


# --- the floor draws other parameters inside the function's own guards ----

def guarded_sum(x: float, y: float) -> float:
    if not (0 <= y <= 1):
        raise ValueError("y")
    return x + y


def test_a_rows_floor_draws_the_other_parameters_past_the_guards():
    from mathema.policy import _floor_points
    points = _floor_points(guarded_sum, analyze(guarded_sum), "x", "missing",
                           ["nan"], {})
    assert points and all(0 <= pt["y"] <= 1 for pt in points), points
    row = _rows(guarded_sum, "missing(f, x) propagates")["missing_f_x_propagates"]
    assert row.verdict == "holds", (row.verdict, row.note)


# --- a hole f puts in its output from present inputs fails a reduction ----

def nan_above_half(xs: np.ndarray) -> np.ndarray:
    return np.where(xs > 0.5, np.nan, xs)


def test_a_hole_in_fs_output_fails_a_claim_that_reduces_it():
    (row,) = check_conjectures(nan_above_half, [claim(
        "for xs in [0, 1]^n \\ {missing}, sum(f(xs)) <= sum(xs)")])
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.counterexample.endswith("f returned nan"), row.counterexample


# --- None from present inputs under a non-Optional return -----------------

def none_above_half(x: float) -> float:
    return None if x > 0.5 else x


def test_an_undeclared_none_falsifies_the_value_claim_and_has_no_row_of_its_own():
    import mathema
    rec = mathema.check(none_above_half, claims=[mathema.claim(
        "for x in [0, 1], f(x) <= 1", name="c")])
    rows = {p.name: p for p in rec.probes}
    assert "absent[f]" not in rows
    value = rows["c"]
    assert value.verdict == "falsified" or rows.get("c[float]").verdict == "falsified"


def test_an_undeclared_none_falsifies_is_defined():
    (row,) = check_conjectures(none_above_half, [claim("is_defined(f)")])
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.counterexample.startswith("x = ")
    assert "returned None" in row.counterexample


def none_declared(x: float) -> Optional[float]:
    return None if x > 0.5 else x


def test_a_declared_none_leaves_is_defined_standing():
    (row,) = check_conjectures(none_declared, [claim("is_defined(f)")])
    assert row.verdict == "proven", (row.verdict, row.note)
