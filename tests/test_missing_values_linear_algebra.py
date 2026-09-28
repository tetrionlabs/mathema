# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Missing values in vectors, matrices and tables: every row of the
linear-algebra battery. A hole sits in a slot (an element, an entry, a
cell); `None` is the whole container being absent. Each row asserts
its verdict and, where one is named, the member its witness holds; a
row a later stage of the build owns carries a strict `xfail`."""
import pytest

from tests.test_missing_values_core import (FALSIFIED, PROVEN,
                                            PROVEN_OR_HOLDS, assert_row,
                                            stage, witness)

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pl = pytest.importorskip("polars")


def plain_sum(xs: list) -> float:
    return sum(xs)


def plain_sum_typed(xs: list[float]) -> float:
    return sum(xs)


def nan_sum(xs: list) -> float:
    return sum(x for x in xs if x is not None and x == x)


def strict_sum(xs: list) -> float:
    if any(x is None or x != x for x in xs):
        raise ValueError("missing element")
    return sum(xs)


def mean_np(xs: np.ndarray) -> float:
    return float(np.mean(xs))


def nanmean_np(xs: np.ndarray) -> float:
    return float(np.nanmean(xs))


def mean_pd(xs: pd.Series) -> float:
    return float(xs.mean())


def mean_pd_strict(xs: pd.Series) -> float:
    return float(xs.mean(skipna=False))


def mean_pl(xs: pl.Series) -> float:
    return float(xs.mean())


def gram_trace(A: np.ndarray) -> float:
    return float(np.trace(A @ A.T))


def weighted(df: pd.DataFrame) -> float:
    return float((df.w * df.r).sum())


def col_mean(df: pl.DataFrame) -> float:
    return float(df["r"].mean())


HOLDS = ("holds",)


@stage(2)
def test_q1_a_bare_list_slot_may_hold_null():
    assert_row(plain_sum, "for xs in [0, 1]^n, f(xs) >= 0", PROVEN,
               companion="falsified", companion_member="None")


@stage(2)
def test_q1b_the_written_element_clause_is_the_same_claim():
    assert_row(plain_sum, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", PROVEN,
               companion="falsified", companion_member="None")


def test_q2_dropping_holes_holds():
    assert_row(nan_sum, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", HOLDS)


@stage(2)
def test_q3_a_raise_on_an_admitted_hole_falsifies():
    probe, _ = assert_row(strict_sum, "for xs in [0, 1]^n | {missing}, f(xs) >= 0",
                          FALSIFIED)
    assert "None" in witness(probe) or "nan" in witness(probe)


@stage(3)
def test_q4_a_float_list_admits_nan_slots():
    assert_row(plain_sum_typed, "for xs in [0, 1]^n, f(xs) >= 0", PROVEN,
               companion="falsified", companion_member="nan")


@stage(4)
def test_q5_a_drop_policy_holds():
    assert_row(nan_sum, "for xs in [0, 1]^n | {missing}, f(xs) == f(non_missing(xs))",
               HOLDS)


@stage(4)
def test_q6_a_sum_that_raises_on_null_is_no_drop_policy():
    probe, _ = assert_row(plain_sum,
                          "for xs in [0, 1]^n | {missing}, f(xs) == f(non_missing(xs))",
                          FALSIFIED)
    assert "None" in witness(probe)


@stage(4)
def test_q7_a_raise_policy_holds():
    assert_row(strict_sum,
               "for xs in [0, 1]^n | {missing}, assuming any_missing(xs), "
               "raises(f(xs), ValueError)", HOLDS)


@stage(5)
def test_q8_a_list_sum_is_not_missing_safe():
    assert_row(plain_sum, "is_missing_safe(f)", FALSIFIED)


@stage(5)
def test_q9_a_dropping_sum_is_missing_safe():
    assert_row(nan_sum, "is_missing_safe(f)", PROVEN)


@stage(3)
def test_v1_numpy_propagation_leaves_a_falsified_companion():
    assert_row(mean_np, "for xs in [0, 1]^n, f(xs) >= 0", PROVEN,
               companion="falsified", companion_member="nan")


@stage(3)
def test_v2_a_nan_slot_falsifies_on_the_probe():
    probe, _ = assert_row(mean_np, "for xs in [0, 1]^n | {missing}, f(xs) >= 0",
                          FALSIFIED)
    assert "nan" in witness(probe)


def test_v3_nanmean_holds():
    assert_row(nanmean_np, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", HOLDS)


@stage(4)
def test_v4_the_numpy_propagate_policy_holds():
    assert_row(mean_np,
               "for xs in [0, 1]^n | {missing}, assuming any_missing(xs), "
               "f(xs) in {missing}", HOLDS)


@stage(4)
def test_v5_pandas_drops():
    assert_row(mean_pd, "for xs in [0, 1]^n | {missing}, f(xs) == f(non_missing(xs))",
               HOLDS)


@stage(4)
def test_v6_pandas_without_skipna_propagates():
    assert_row(mean_pd_strict,
               "for xs in [0, 1]^n | {missing}, f(xs) == f(non_missing(xs))",
               FALSIFIED)


@stage(4)
def test_v7_polars_carries_nan_as_a_value():
    probe, _ = assert_row(mean_pl,
                          "for xs in [0, 1]^n | {missing}, f(xs) == f(non_missing(xs))",
                          FALSIFIED)
    assert "nan" in witness(probe)


@pytest.mark.xfail(strict=True, reason="84 records holds; since the pandas "
                   "rows merged from develop, derive proves it through "
                   "pandas.Series.mean: the row's verdict awaits a decision")
def test_v8_pandas_mean_holds():
    assert_row(mean_pd, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", HOLDS)


@stage(3)
def test_v9_a_polars_nan_member_falsifies():
    probe, _ = assert_row(mean_pl, "for xs in [0, 1]^n | {missing}, f(xs) >= 0",
                          FALSIFIED)
    assert "nan" in witness(probe)


@stage(5)
def test_v10_a_bare_series_mean_is_missing_safe():
    assert_row(mean_pd, "is_missing_safe(f)", PROVEN)


@stage(3)
def test_matrix_m1_a_hole_entry_leaves_a_falsified_companion():
    assert_row(gram_trace, "for A in R^(n,n), f(A) >= 0", PROVEN,
               companion="falsified", companion_member="nan")


@stage(3)
def test_matrix_m2_a_hole_entry_falsifies_on_the_probe():
    assert_row(gram_trace, "for A in R^(n,n) | {missing}, f(A) >= 0", FALSIFIED)


def test_t1_a_complete_table_holds():
    assert_row(weighted, "for df in [0, 1]^n, f(df) ~= dot(df.w, df.r)",
               PROVEN_OR_HOLDS)


@stage(3)
def test_t2_a_column_hole_falsifies():
    assert_row(weighted, "for df in [0, 1]^n | {missing}, f(df) ~= dot(df.w, df.r)",
               FALSIFIED)


@stage(4)
def test_t3_a_polars_nan_member_falsifies_the_drop_policy():
    probe, _ = assert_row(col_mean,
                          "for df in [0, 1]^n | {missing}, "
                          "f(df) == mean(non_missing(df.r))", FALSIFIED)
    assert "nan" in witness(probe)
