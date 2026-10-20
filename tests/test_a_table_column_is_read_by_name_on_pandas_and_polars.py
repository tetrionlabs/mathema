# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A reduction of a table answers one value per column, and a claim
reads the answer for a column by its name.

pandas answers `df.sum()` with a Series labelled by the column names;
polars answers with a one-row DataFrame. Either way `f(a)["x"]` is the
answer for column `x`, whatever other columns the table has and in
whatever order, so a row stated by name adjudicates on both libraries.
A row stated by position reads the position, as it always has: it
holds where column `x` is at that position and is falsified where it
is not.
"""
from __future__ import annotations

import math

import pytest

pytest.importorskip("pandas")
pytest.importorskip("polars")

import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.runtime_types import (AbstractVec, observe,  # noqa: E402
                                   observed_plain)

_OVER = "for a in [-1e6, 1e6]^n \\ {missing}, "


def pandas_sums(a: pd.DataFrame):
    return a.assign(y=a.x * 2)[["y", "x"]].sum()


def polars_sums(a: pl.DataFrame):
    return a.with_columns(y=a["x"] * 2).select(["y", "x"]).sum()


def _verdict(fn, text: str):
    (p,) = check_conjectures(fn, [claim(_OVER + text)])
    return p


@pytest.mark.parametrize("fn", [pandas_sums, polars_sums])
@pytest.mark.parametrize("text", ['f(a)["x"] ~= sum(a.x)',
                                  'f(a)["y"] ~= 2 * sum(a.x)'])
def test_a_reduction_read_by_column_name_holds(fn, text):
    p = _verdict(fn, text)
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)


@pytest.mark.parametrize("fn", [pandas_sums, polars_sums])
def test_a_wrong_reduction_read_by_column_name_is_falsified(fn):
    p = _verdict(fn, 'f(a)["x"] ~= 3 * sum(a.x)')
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "a = {'x': [" in str(p.counterexample), p.counterexample


def test_a_pandas_reduction_read_by_position_reads_the_position():
    first = _verdict(pandas_sums, "f(a)[0] ~= sum(a.x)")
    assert first.verdict == "falsified", (first.verdict, first.note)
    second = _verdict(pandas_sums, "f(a)[1] ~= sum(a.x)")
    assert second.verdict in ("holds", "proven"), (second.verdict,
                                                   second.note)


def test_the_compendium_form_of_issue_31_adjudicates():
    def summed_with_y_first(a: pd.DataFrame):
        frame = a.copy()
        frame.insert(0, "y", [100.0 + 7.0 * i for i in range(len(frame))])
        return pd.DataFrame.sum(frame)
    p = _verdict(summed_with_y_first, 'f(a)["x"] ~= sum(a.x)')
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)


def test_a_series_labelled_by_name_is_observed_with_its_labels():
    seen = observe(pd.Series([2.0, 1.0], index=["y", "x"]))
    assert isinstance(seen, AbstractVec)
    assert seen.labels == ("y", "x")
    assert seen.values == (2.0, 1.0)
    plain = observed_plain(pd.Series([2.0, math.nan], index=["y", "x"]))
    assert plain[0] == 2.0 and math.isnan(plain[1])
    assert plain.labels == ("y", "x")


def test_a_series_on_dates_or_positions_has_no_labels():
    dated = pd.Series([1.0, 2.0],
                      index=pd.bdate_range("2020-01-01", periods=2))
    assert observe(dated).labels == ()
    assert observe(pd.Series([1.0, 2.0])).labels == ()
    assert observed_plain(dated) == [1.0, 2.0]
    assert type(observed_plain(dated)) is list
    assert observe(pl.Series("x", [1.0, 2.0])).labels == ()
