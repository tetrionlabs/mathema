# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`check()` reads a result that is a big integer, a pandas Series, an
object array or a Decimal, and gives a verdict.

`2 ** n` for n up to 2000 is an integer far beyond float range; it
compares exactly, so `f(n) >= 1` holds on the computation line instead
of the check crashing on a conversion to float. A Series or object
array result compares element by element, as any array does, and a
Decimal compares exactly.
"""
from __future__ import annotations
import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

from decimal import Decimal  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import mathema  # noqa: E402


def pow2(n: int) -> int:
    return 2 ** n


def pair_series(x: float):
    return pd.Series([x, x])


def mixed_array(x: float):
    return np.array([x, "a"], dtype=object)


def as_decimal(x: float):
    return Decimal(x)


def _rows(fn, claims=None):
    record = mathema.check(fn, claims=claims) if claims else mathema.check(fn)
    return {p.name: p for p in record.probes}


@pytest.mark.needs_full_proof_budget
def test_a_power_of_two_far_beyond_float_range_is_judged_exactly():
    rows = _rows(pow2, ["for n in [0, 2000] subset Z, f(n) >= 1"])
    assert rows["f_n_ge_1"].verdict == "proven", rows["f_n_ge_1"].note
    companion = rows["f_n_ge_1[float]"]
    assert companion.verdict == "holds", (companion.verdict, companion.note)


@pytest.mark.needs_full_proof_budget
def test_an_equality_with_a_power_of_two_is_judged_exactly():
    rows = _rows(pow2, ["for n in [0, 2000] subset Z, f(n) == 2**n"])
    (main,) = [p for name, p in rows.items() if "[" not in name
               and name.startswith("f_n")]
    assert main.verdict == "proven", (main.verdict, main.note)
    companion = rows[f"{main.name}[float]"]
    assert companion.verdict in ("proven", "holds"), \
        (companion.verdict, companion.note)


@pytest.mark.needs_full_proof_budget
def test_a_wrong_bound_on_a_power_of_two_is_falsified_exactly():
    rows = _rows(pow2, ["for n in [0, 2000] subset Z, f(n) <= 2 ** 1999"])
    (main,) = [p for name, p in rows.items() if "[" not in name
               and name.startswith("f_n")]
    assert main.verdict == "falsified", (main.verdict, main.note)


@pytest.mark.parametrize("fn", [pair_series, mixed_array])
def test_an_array_result_is_compared_element_by_element(fn):
    rows = _rows(fn)
    row = next(p for name, p in rows.items()
               if name.startswith("is_representation_safe"))
    assert row.verdict in ("holds", "proven"), (row.verdict, row.note)


def test_a_decimal_result_is_compared_exactly():
    rows = _rows(as_decimal)
    increasing = [p for name, p in rows.items()
                  if name.startswith("monotone_increasing")]
    for row in increasing:
        assert row.verdict in ("holds", "proven"), (row.verdict, row.note)
    rows = _rows(as_decimal, ["for x in [-10, 10], f(x) >= -10"])
    assert rows["f_x_ge_10"].verdict in ("proven", "holds"), \
        rows["f_x_ge_10"].note
