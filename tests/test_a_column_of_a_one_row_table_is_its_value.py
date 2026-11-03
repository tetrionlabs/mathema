# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A table with one row holds one value per column, so a number meets a
column of that table as the value it holds: polars answers a reduction
with a one-row DataFrame, and `f(a)["x"]` is the answer for column `x`.
This is a fact about the table, not about a list: a list of one element
and the column of a longer table are still a different shape from a
number other than 0."""
from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
pl = pytest.importorskip("polars")

from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.probing import scalar_spreads  # noqa: E402
from mathema.runtime_types import observed_plain  # noqa: E402

_OVER = "for a in [1, 100]^n \\ {missing}, "


def polars_sums(a: pl.DataFrame):
    return a.select("x").sum()


def pandas_one_row(a: pd.DataFrame):
    return pd.DataFrame({"x": [float(a["x"].sum())]})


def polars_whole_sums(a: pl.DataFrame):
    return a.sum()


def polars_five(a: pl.DataFrame):
    return pl.DataFrame({"x": [5.0]})


def pandas_five(a: pd.DataFrame):
    return pd.DataFrame({"x": [5.0]})


def polars_two_rows(a: pl.DataFrame):
    return pl.DataFrame({"x": [5.0, 5.0]})


def pandas_two_rows(a: pd.DataFrame):
    return pd.DataFrame({"x": [5.0, 5.0]})


def polars_no_rows(a: pl.DataFrame):
    return pl.DataFrame({"x": pl.Series([], dtype=pl.Float64)})


def one_element_list(x: float):
    return [5.0]


def dict_of_one_element_list(x: float):
    return {"x": [5.0]}


def _verdict(fn, law: str) -> str:
    (probe,) = check_conjectures(fn, [claim(law, name="c")])
    return probe.verdict


@pytest.mark.parametrize("fn", [polars_sums, pandas_one_row])
def test_a_one_row_reduction_meets_the_sum_it_holds(fn):
    assert _verdict(fn, _OVER + 'f(a)["x"] ~= sum(a.x)') in ("holds", "proven")


@pytest.mark.parametrize("fn", [polars_sums, pandas_one_row])
def test_a_one_row_reduction_misses_a_sum_it_does_not_hold(fn):
    assert _verdict(fn, _OVER + 'f(a)["x"] ~= 3 * sum(a.x)') == "falsified"


@pytest.mark.parametrize("fn", [polars_five, pandas_five])
@pytest.mark.parametrize("law,verdicts", [
    ('f(a)["x"] == 5', ("holds", "proven")),
    ('f(a)["x"] ~= 5', ("holds", "proven")),
    ('f(a)["x"] != 6', ("holds", "proven")),
    ('f(a)["x"] >= 5', ("holds", "proven")),
    ('f(a)["x"] == 6', ("falsified",)),
    ('f(a)["x"] != 5', ("falsified",)),
    ('f(a)["x"] > 5', ("falsified",)),
])
def test_a_number_reads_the_value_a_one_row_column_holds(fn, law, verdicts):
    assert _verdict(fn, _OVER + law) in verdicts


@pytest.mark.parametrize("fn", [polars_five, pandas_five])
def test_a_one_row_column_still_equals_a_list_of_its_value(fn):
    assert _verdict(fn, _OVER + 'f(a)["x"] == [5.0]') in ("holds", "proven")


@pytest.mark.parametrize("law,verdicts", [
    ('f(a)["n"] ~= sum(a.n)', ("holds", "proven")),
    ('2 * f(a)["n"] ~= 2 * sum(a.n)', ("holds", "proven")),
    ('f(a)["n"] ~= sum(a.n) + 1', ("falsified",)),
])
def test_a_one_row_column_of_whole_numbers_is_its_value(law, verdicts):
    assert _verdict(polars_whole_sums,
                    "for a.n in [0, 100]^n subset Z \\ {missing}, " + law) in verdicts


@pytest.mark.parametrize("fn", [polars_two_rows, pandas_two_rows])
@pytest.mark.parametrize("relation", ["==", "~="])
def test_a_column_of_a_longer_table_is_not_a_number(fn, relation):
    assert _verdict(fn, _OVER + f'f(a)["x"] {relation} 5') == "falsified"


@pytest.mark.parametrize("relation", ["==", "~="])
def test_a_column_of_no_rows_is_not_a_number(relation):
    assert _verdict(polars_no_rows,
                    _OVER + f'f(a)["x"] {relation} 5') == "falsified"


@pytest.mark.parametrize("relation", ["==", "~="])
def test_a_list_of_one_element_is_not_a_number(relation):
    assert _verdict(one_element_list,
                    f"for x in [0, 1], f(x) {relation} 5") == "falsified"


@pytest.mark.parametrize("relation", ["==", "~="])
def test_a_one_element_list_under_a_key_is_not_a_number(relation):
    assert _verdict(dict_of_one_element_list,
                    f'for x in [0, 1], f(x)["x"] {relation} 5') == "falsified"


@pytest.mark.parametrize("relation", ["==", "~=", "!=", ">="])
def test_the_shape_rule_spreads_a_scalar_over_a_one_row_column(relation):
    column = observed_plain(pl.DataFrame({"x": [5.0]}))["x"]
    assert column == [5.0]
    assert scalar_spreads(5.0, column, relation)


@pytest.mark.parametrize("relation", ["==", "~=", "!="])
def test_the_shape_rule_keeps_a_plain_list_of_one_apart(relation):
    assert not scalar_spreads(5.0, [5.0], relation)


def no_table_pandas(n: int) -> pd.DataFrame:
    return pd.DataFrame({"qty": [float(n)]})


def no_table_polars(n: int) -> pl.DataFrame:
    return pl.DataFrame({"qty": [float(n)]})


def series_pandas(n: int) -> pd.Series:
    return pd.Series([float(n)])


def series_polars(n: int) -> pl.Series:
    return pl.Series([float(n)])


def one_row_bools(a: pd.DataFrame):
    return pd.DataFrame({"x": [True]})


def one_row_sum(df: pd.DataFrame):
    return pd.DataFrame({"qty": [float(df["qty"].sum())]})


@pytest.mark.parametrize("fn", [no_table_pandas, no_table_polars])
def test_a_one_row_frame_from_a_function_with_no_table_parameter_reads_the_same(fn):
    assert _verdict(fn, 'for n in {1, 2, 3}, f(n)["qty"] == n') in ("holds", "proven")
    assert _verdict(fn, 'for n in {1, 2, 3}, f(n)["qty"] == [n]') in ("holds", "proven")
    assert _verdict(fn, 'for n in {1, 2, 3}, f(n)["qty"] == n + 1') == "falsified"


@pytest.mark.parametrize("fn", [series_pandas, series_polars])
def test_a_series_of_one_element_reads_the_same_on_both_libraries(fn):
    assert _verdict(fn, "for n in {1, 2, 3}, f(n) == n") in ("holds", "proven")
    assert _verdict(fn, "for n in {1, 2, 3}, f(n) == [n]") in ("holds", "proven")
    assert _verdict(fn, "for n in {1, 2, 3}, f(n) == n + 1") == "falsified"


@pytest.mark.parametrize("law,verdicts", [
    ('f(a)["x"] == True', ("holds", "proven")),
    ('f(a)["x"] == 1', ("holds", "proven")),
    ('f(a)["x"] == False', ("falsified",)),
])
def test_a_one_row_bool_column_is_its_value_read_exactly_too(law, verdicts):
    assert _verdict(one_row_bools, _OVER + law) in verdicts


def test_the_one_row_mark_never_shows_in_a_value():
    from mathema._linalg_eval import as_array
    from mathema.runtime_types._abstract import OneRowColumn
    column = as_array({"qty": OneRowColumn([2.0])})["qty"]
    assert repr(column) == "array([2.])"
    assert str(column) == "[2.]"
    assert repr(2 * column) == "array([4.])"


def test_the_one_row_mark_never_reaches_a_record():
    import json

    import mathema
    record = mathema.check(one_row_sum, claims=[mathema.claim(
        'for df.qty in [0, 10]^n, f(df)["qty"] ~= sum(df.qty)', name="c")])
    for probe in record.probes:
        shown = json.dumps({"counterexample": probe.counterexample,
                            "note": probe.note, "meta": probe.meta},
                           default=str)
        assert "OneRow" not in shown, (probe.name, shown[:300])
    (missing,) = [p for p in record.probes if p.name == "missing[df]"]
    assert "returns {'qty': array([" in str(missing.counterexample), \
        missing.counterexample
