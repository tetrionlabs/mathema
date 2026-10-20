# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A column whose draw is holes only keeps the type its binding states.

`for a.k in {"u", "v"}^n` makes `k` a string column. A draw where every
cell of `k` is a hole says nothing about the type in its values, so the
binding says it: pandas receives a string column, polars a `String`
column holding null, never a float column of NaN, which on polars is a
value that is neither a member of `{"u", "v"}` nor a hole.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pandas")
pytest.importorskip("polars")

import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402

_STRINGS = 'for a.k in {"u", "v"}^n, a.x in [0, 1]^n, '
_BOOLS = "for a.k in {True, False}^n, a.x in [0, 1]^n, "


def k_is_text_pandas(a: pd.DataFrame) -> int:
    return int(pd.api.types.is_string_dtype(a["k"])
               or a["k"].dtype == object)


def k_is_text_polars(a: pl.DataFrame) -> int:
    return int(a["k"].dtype == pl.String)


def k_members_polars(a: pl.DataFrame) -> int:
    return int(all(v in ("u", "v") for v in a["k"].drop_nulls().to_list()))


def k_is_bool_polars(a: pl.DataFrame) -> int:
    return int(a["k"].dtype == pl.Boolean)


@pytest.mark.parametrize("fn, over", [
    (k_is_text_pandas, _STRINGS), (k_is_text_polars, _STRINGS),
    (k_members_polars, _STRINGS), (k_is_bool_polars, _BOOLS)])
def test_the_column_keeps_its_type_on_every_draw(fn, over):
    (p,) = check_conjectures(fn, [claim(over + "f(a) == 1")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note,
                                              p.counterexample)
