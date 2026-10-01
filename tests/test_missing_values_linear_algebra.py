# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Missing values in vectors, matrices and tables: every row of the
linear-algebra battery. A hole sits in a slot (an element, an entry, a
cell); `None` is the whole container being absent. Each row asserts
its verdict and, where one is named, the member its witness holds; a
row a later stage of the build owns carries a strict `xfail`."""
import pytest

from tests.test_missing_values_core import (FALSIFIED, PROVEN,
                                            assert_row,
                                            witness)

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
#: a hole in a list slot is `null` or `nan`, whichever resolved member
#: fails first (R37): the witness names the kind
HOLE = ("None", "nan")


def assert_companion(fn, text, verdict, behaves, members=None):
    """The main claim is proven over the reals; a companion comes to
    `verdict` (its witness naming one of `members` when given), and the
    behaviour at each missing input executed is `behaves`."""
    _, companions = assert_row(fn, text, PROVEN, behaves=behaves)
    assert any(c.verdict == verdict and (members is None or any(
        m in witness(c) for m in members)) for c in companions), \
        [(c.name, c.verdict, witness(c)) for c in companions]


LIST_SUM = {"xs": {"null": "raises", "nan": "propagates"}}


@pytest.mark.needs_full_proof_budget
def test_q1_a_bare_list_sum_is_proven_over_the_reals():
    assert_row(plain_sum, "for xs in [0, 1]^n, f(xs) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_q1_the_list_companion_holds_and_records_both_members():
    assert_companion(plain_sum, "for xs in [0, 1]^n, f(xs) >= 0", "holds", LIST_SUM)


@pytest.mark.needs_full_proof_budget
def test_q1b_the_written_element_clause_is_the_same_claim():
    assert_row(plain_sum, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_q1b_the_list_companion_holds_and_records_both_members():
    assert_companion(plain_sum, "for xs in [0, 1]^n | {missing}, f(xs) >= 0",
                     "holds", LIST_SUM)


def test_q2_dropping_holes_holds():
    assert_row(nan_sum, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", HOLDS,
               behaves={"xs": {"null": "drops", "nan": "drops"}})


def test_q3_a_raise_on_an_admitted_hole_is_classified_on_the_probe():
    assert_row(strict_sum, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", HOLDS,
               behaves={"xs": {"null": "raises", "nan": "raises"}})


@pytest.mark.needs_full_proof_budget
def test_q4_a_float_list_sum_is_proven_over_the_reals():
    assert_row(plain_sum_typed, "for xs in [0, 1]^n, f(xs) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_q4_a_float_list_companion_holds_and_nan_propagates():
    assert_companion(plain_sum_typed, "for xs in [0, 1]^n, f(xs) >= 0", "holds",
                     {"xs": {"nan": "propagates"}})


@pytest.mark.needs_full_proof_budget
def test_v1_numpy_mean_is_proven_through_its_definition_row():
    assert_row(mean_np, "for xs in [0, 1]^n, f(xs) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_v1_numpy_propagation_is_recorded_and_the_companion_holds():
    assert_companion(mean_np, "for xs in [0, 1]^n, f(xs) >= 0", "holds",
                     {"xs": {"nan": "propagates"}})


@pytest.mark.needs_full_proof_budget
def test_v2_the_written_element_clause_is_proven_over_the_reals():
    assert_row(mean_np, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_v2_a_nan_slot_propagates_and_the_companion_holds():
    assert_companion(mean_np, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", "holds",
                     {"xs": {"nan": "propagates"}})


@pytest.mark.needs_full_proof_budget
def test_v3_nanmean_drops_some_holes_and_propagates_an_all_hole_vector():
    _, companions = assert_row(nanmean_np, "for xs in [0, 1]^n | {missing}, f(xs) >= 0",
                               PROVEN, behaves={"xs": {"nan": "mixed"}})
    (companion,) = companions
    assert companion.verdict == "holds"
    mixed = companion.meta["mathema.missing"]["mixed"]["xs"]["nan"]
    assert set(mixed) == {"drops", "propagates"}
    assert mixed["propagates"] in ("xs = [nan]", "xs = [nan, nan]"), mixed


@pytest.mark.needs_full_proof_budget
def test_v8_pandas_mean_is_proven_through_its_definition_row():
    assert_row(mean_pd, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_v8_the_series_companion_holds_and_each_member_is_mixed():
    assert_companion(mean_pd, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", "holds",
                     {"xs": {"nan": "mixed", "null": "mixed", "NA": "mixed"}})


@pytest.mark.needs_full_proof_budget
def test_v9_polars_mean_is_proven_through_its_definition_row():
    assert_row(mean_pl, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_v9_the_polars_companion_holds_null_is_mixed_and_nan_propagates():
    assert_companion(mean_pl, "for xs in [0, 1]^n | {missing}, f(xs) >= 0", "holds",
                     {"xs": {"null": "mixed", "nan": "propagates"}})


@pytest.mark.needs_full_proof_budget
def test_matrix_m1_a_gram_trace_is_proven():
    assert_row(gram_trace, "for A in R^(n,n), f(A) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_matrix_m1_the_companion_is_falsified_at_the_overflow_corner():
    assert_companion(gram_trace, "for A in R^(n,n), f(A) >= 0", "falsified",
                     {"A": {"nan": "propagates"}}, members=("e+308",))


@pytest.mark.needs_full_proof_budget
def test_matrix_m2_the_written_element_clause_is_the_same_claim():
    assert_row(gram_trace, "for A in R^(n,n) | {missing}, f(A) >= 0", PROVEN)


@pytest.mark.needs_full_proof_budget
def test_matrix_m2_the_companion_is_falsified_at_the_overflow_corner():
    assert_companion(gram_trace, "for A in R^(n,n) | {missing}, f(A) >= 0",
                     "falsified", {"A": {"nan": "propagates"}}, members=("e+308",))


@pytest.mark.needs_full_proof_budget
def test_t1_a_table_dot_is_proven():
    assert_row(weighted, "for df in [0, 1]^n, f(df) ~= dot(df.w, df.r)", PROVEN)


TABLE_DROPS = {"df": {"nan": "drops", "null": "drops", "NA": "drops"}}


@pytest.mark.needs_full_proof_budget
def test_t1_the_table_companion_holds_and_every_member_drops():
    # pandas' sum skips a hole, and `dot` over no shared value is 0
    assert_companion(weighted, "for df in [0, 1]^n, f(df) ~= dot(df.w, df.r)",
                     "holds", TABLE_DROPS)


@pytest.mark.needs_full_proof_budget
def test_t2_the_written_element_clause_is_the_same_claim():
    assert_row(weighted, "for df in [0, 1]^n | {missing}, f(df) ~= dot(df.w, df.r)",
               PROVEN)


@pytest.mark.needs_full_proof_budget
def test_t2_the_table_companion_holds_and_every_member_drops():
    assert_companion(weighted,
                     "for df in [0, 1]^n | {missing}, f(df) ~= dot(df.w, df.r)",
                     "holds", TABLE_DROPS)


# the policy claims each behaviour above states

@pytest.mark.parametrize("fn, text, verdicts", [
    (nan_sum, "missing(f, xs) drops", HOLDS),                       # Q5
    (plain_sum, "missing(f, xs) drops", FALSIFIED),                 # Q6
    (strict_sum, "missing(f, xs) raises(ValueError)", HOLDS),       # Q7
    (plain_sum, "missing(f, xs, null) raises(TypeError)", HOLDS),
    (plain_sum, "missing(f, xs, nan) propagates", HOLDS),
    (mean_np, "missing(f, xs) propagates", HOLDS),                  # V4
    (mean_pd, "missing(f, xs) drops", FALSIFIED),                   # V5
    (mean_pd_strict, "missing(f, xs, nan) propagates", HOLDS),      # V6
    (mean_pl, "missing(f, xs, nan) propagates", HOLDS),             # V7
    (mean_pl, "missing(f, xs, null) drops", FALSIFIED),             # V7
    (col_mean, "missing(f, df, nan) propagates", HOLDS),            # T3
])
def test_the_behaviour_is_a_policy_claim(fn, text, verdicts):
    assert_row(fn, text, verdicts)


def test_q8_a_list_sum_is_not_missing_safe():
    probe, _ = assert_row(plain_sum, "is_missing_safe(f)", FALSIFIED)
    # a None in a list slot is the member null
    assert any(m in witness(probe) for m in ("null", "nan"))


def test_q9_a_dropping_sum_is_missing_safe_on_evidence():
    assert_row(nan_sum, "is_missing_safe(f)", HOLDS)


def test_v10_a_series_mean_is_not_missing_safe_at_an_all_na_series():
    assert_row(mean_pd, "is_missing_safe(f)", FALSIFIED)
