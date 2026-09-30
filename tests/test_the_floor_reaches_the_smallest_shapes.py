# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`^n` holds n = 1, so every claim over vectors or matrices meets the
smallest shapes its binding admits before any random draw: vectors that
share a length all at length 1 together, and a 1 by 1 matrix."""
import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")


def second_plus(xs: np.ndarray, ys: np.ndarray) -> float:
    return float(xs[1] + ys[0])


def coupling(A: np.ndarray) -> float:
    return float(A[0, 1])


def _row(fn, text):
    (row,) = [r for r in check_conjectures(fn, [claim(text, name="c")]) if r.name == "c"]
    return row


def test_vectors_sharing_a_length_meet_length_one_together():
    row = _row(second_plus, "for xs in [0, 1]^n, ys in [0, 1]^n, f(xs, ys) >= 0")
    assert row.verdict == "falsified"
    xs, ys = row.meta["mathema.counterexample_args"]
    assert (len(xs), len(ys)) == (1, 1)
    assert "raised IndexError" in row.counterexample


def test_a_square_matrix_meets_one_by_one():
    row = _row(coupling, "for A in [0, 1]^(n,n), f(A) >= 0")
    assert row.verdict == "falsified"
    (A,) = row.meta["mathema.counterexample_args"]
    assert np.shape(A) == (1, 1)
    assert "raised IndexError" in row.counterexample


def test_a_container_holding_two_members_is_drawn_and_each_member_is_read(monkeypatch):
    pl = pytest.importorskip("polars")
    from mathema import _missing_policy
    from mathema.policy import batch

    def mean_pl(xs: pl.Series) -> "float | None":
        return xs.mean()
    seen = []
    real = _missing_policy.refill

    def spy(call_at, point, output, raised, fills):
        out = real(call_at, point, output, raised, fills)
        if {"null", "nan"} <= {m for _q, _k, m in _missing_policy.keys_of(point)}:
            seen.append(point)
        return out
    monkeypatch.setattr(_missing_policy, "refill", spy)
    with batch() as made:
        rows = check_conjectures(mean_pl, [
            claim("for xs in [0, 1]^n, f(xs) <= 1", name="c"),
            claim("assuming count(xs) >= 1, missing(f, xs, null) drops", name="nulls")])
    by_name = {r.name: r for r in rows}
    assert by_name["c"].verdict == "holds", by_name["c"].note
    # the null in [null, nan, v] drops, read with the nan filled
    assert by_name["nulls"].verdict == "holds", by_name["nulls"].note
    assert seen, "no draw held null and nan together"
    # a mixed call is filed one member at a time, never as one call
    assert not [c for c in made.calls if {"null", "nan"} <= {
        m for _q, _k, m in _missing_policy.keys_of(c.point)}]


def test_the_floor_draws_one_container_per_pair_of_members():
    from mathema import _floor
    items = _floor.vector_floor(["N", "M"], admits_zero=True, length_free=True)
    made = [item([0.25, 0.5, 0.75]) for item in items]
    assert ["N", "M", 0.25] in made
