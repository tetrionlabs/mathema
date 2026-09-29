# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_empty_safe(xs)`: the function meets the empty container, realised
through the parameter's runtime type (`np.array([])`, an empty float
Series, a zero-row frame with the columns it reads), never a plain list
for a typed parameter. A raise behind an emptiness guard passes, an
unguarded raise fails, a finite value passes (the identity reductions
among them), a hole fails, and a None fails unless the return type
declares it. A scalar has no slots: the claim is misspecified there."""
import statistics
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pl = pytest.importorskip("polars")


def mean_np(xs: np.ndarray) -> float:
    return float(np.mean(xs))


def sum_pd(xs: pd.Series) -> float:
    return float(xs.sum())


def mean_pl(xs: pl.Series) -> float:
    return xs.mean()


def mean_pl_declared(xs: pl.Series) -> Optional[float]:
    return xs.mean()


def mean_list(xs: list) -> float:
    return statistics.mean(xs)


def mean_counted(xs: pd.Series) -> float:
    if xs.count() == 0:
        raise ValueError("no values")
    return float(xs.mean())


def mean_guarded(xs: list) -> float:
    if len(xs) == 0:
        raise ValueError("empty")
    return statistics.mean(xs)


def col_mean(df: pd.DataFrame) -> float:
    return float(df["r"].mean())


def typed(xs: pd.Series) -> float:
    return 0.0 if xs.dtype == float else float("nan")


def scalar(x: float) -> float:
    return x


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


def test_a_hole_for_the_empty_input_fails():
    row = _row(mean_np, "is_empty_safe(xs)")
    assert row.verdict == "falsified"
    assert row.counterexample == ("xs = []: f returned nan for the empty input; raise, "
                                  "or return a value")


def test_an_identity_reduction_passes():
    assert _row(sum_pd, "is_empty_safe(xs)").verdict in ("proven", "holds")


def test_an_undeclared_none_fails_and_a_declared_one_passes():
    row = _row(mean_pl, "is_empty_safe(xs)")
    assert row.verdict == "falsified"
    assert row.counterexample == (
        "xs = []: f returned None for the empty input; declare the return type "
        "Optional[float], raise, or return a value")
    assert _row(mean_pl_declared, "is_empty_safe(xs)").verdict in ("proven", "holds")


def test_an_unguarded_raise_fails_and_a_guarded_one_passes():
    assert _row(mean_list, "is_empty_safe(xs)").verdict == "falsified"
    assert _row(mean_guarded, "is_empty_safe(xs)").verdict == "proven"


def test_a_table_is_realised_with_zero_rows_and_its_columns():
    row = _row(col_mean, "is_empty_safe(df)")
    assert row.verdict == "falsified"
    assert "f returned nan for the empty input" in row.counterexample


def test_the_empty_container_has_the_runtime_type():
    assert _row(typed, "is_empty_safe(xs)").verdict in ("proven", "holds")


def test_a_scalar_parameter_is_misspecified():
    row = _row(scalar, "is_empty_safe(x)")
    assert row.verdict == "skipped:misspecified"
    assert row.note == "x is a scalar; empty applies to a container"


def test_a_count_guard_is_an_emptiness_guard():
    assert _row(mean_counted, "is_empty_safe(xs)").verdict == "proven"
