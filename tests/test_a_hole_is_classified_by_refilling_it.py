# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a call at a hole did is read by calling f again with the hole
filled by a value of its domain: a raise raises; a hole in the output
that stays when the input's hole is filled was introduced; a hole that
goes with it propagates, however far it spread; a value the fill leaves
the same leaves f indifferent to the slot; a value the fill changes
dropped the hole. A container holding two members is filled one member
at a time."""
import math

import pytest

from mathema._missing_policy import INCONCLUSIVE, INDIFFERENT, refill

NAN = math.nan
UNIT = {"x": 0.5, "y": 0.5, "xs": 0.5, "A": 0.5}


def _calls(fn):
    def call_at(point):
        try:
            return fn(**point), None
        except Exception as exc:
            return None, type(exc).__name__
    return call_at


def _behaviours(fn, **point):
    try:
        output, raised = fn(**point), None
    except Exception as exc:
        output, raised = None, type(exc).__name__
    return [b for _p, _o, _r, b in refill(_calls(fn), point, output, raised, UNIT)]


def clamp01(x):
    return max(0.0, min(1.0, x))


def root(x):
    return math.sqrt(x) if x == x else NAN


def second(x, y):
    return y


def strict(x):
    if x != x:
        raise ValueError("x is nan")
    return x


def zero_over_zero(xs):
    import numpy as np
    return float(np.float64(0.0) / np.float64(0.0)) + 0.0 * len(xs)


def test_a_raise_raises():
    assert _behaviours(strict, x=NAN) == ["raises"]


def test_a_filled_call_that_gives_no_value_is_inconclusive():
    assert _behaviours(zero_over_zero, xs=[NAN, 0.5]) == [INCONCLUSIVE]


def test_a_hole_that_stays_beside_values_after_the_fill_was_introduced():
    def shifted(xs):
        return [NAN] + list(xs[:-1])
    assert _behaviours(shifted, xs=[1.0, NAN, 0.5]) == ["introduces"]


def test_a_replacement_equal_to_the_fill_is_still_read():
    # clamp(nan) is 1.0, and so is clamp(1.0) and clamp(2.0); clamp(0.9) is not
    def call_at(point):
        return clamp01(**point), None
    out = refill(call_at, {"x": NAN}, 1.0, None, {"x": 1.0})
    assert [b for *_r, b in out] == ["drops"]


def test_a_hole_that_goes_with_the_fill_propagates():
    assert _behaviours(root, x=NAN) == ["propagates"]


def test_a_value_no_fill_changes_is_indifferent():
    assert _behaviours(second, x=NAN, y=0.5) == [INDIFFERENT]


def test_a_value_the_fill_changes_dropped_the_hole():
    assert _behaviours(clamp01, x=NAN) == ["drops"]


def test_a_spread_is_propagation():
    np = pytest.importorskip("numpy")

    def running_total(xs):
        return np.cumsum(np.array(xs, dtype=float)).tolist()

    def gram(A):
        a = np.array(A, dtype=float)
        return (a.T @ a).tolist()

    def trace_of(A):
        return float(np.trace(np.array(A, dtype=float)))
    assert _behaviours(running_total, xs=[1.0, NAN, 0.5]) == ["propagates"]
    assert _behaviours(gram, A=[[NAN, 0.5], [0.25, 1.0]]) == ["propagates"]
    assert _behaviours(trace_of, A=[[NAN, 0.5], [0.25, 1.0]]) == ["propagates"]


def test_a_trace_is_indifferent_to_a_hole_off_the_diagonal():
    np = pytest.importorskip("numpy")

    def trace_of(A):
        return float(np.trace(np.array(A, dtype=float)))
    assert _behaviours(trace_of, A=[[0.5, NAN], [0.25, 1.0]]) == [INDIFFERENT]


def test_an_entry_never_indexed_leaves_f_indifferent():
    def coupling(A):
        return A[0][1]
    assert _behaviours(coupling, A=[[NAN, 0.5], [0.25, 1.0]]) == [INDIFFERENT]
    assert _behaviours(coupling, A=[[0.5, NAN], [0.25, 1.0]]) == ["propagates"]


def test_a_function_reading_every_slot_is_classified_as_before():
    np = pytest.importorskip("numpy")

    def mean(xs):
        return float(np.mean(np.array(xs, dtype=float)))

    def nansum(xs):
        return float(np.nansum(np.array(xs, dtype=float)))
    assert _behaviours(mean, xs=[NAN, 0.5]) == ["propagates"]
    assert _behaviours(nansum, xs=[NAN, 0.5]) == ["drops"]


def test_two_members_are_filled_one_at_a_time():
    pl = pytest.importorskip("polars")

    def mean_pl(xs):
        return pl.Series(xs, dtype=pl.Float64, nan_to_null=False).mean()
    point = {"xs": [None, NAN, 0.5]}
    out = refill(_calls(mean_pl), point, mean_pl(**point), None, UNIT)
    # the member each call still holds, and what f did with it
    assert {("null" if None in p["xs"] else "nan"): b
            for p, _o, _r, b in out} == {"null": "drops", "nan": "propagates"}


def test_an_absence_is_not_refilled():
    assert refill(_calls(root), {"x": None}, None, "TypeError", UNIT) is None



# --- end to end -----------------------------------------------------------

def _rows(fn, text):
    import mathema
    rec = mathema.check(fn, claims=[mathema.claim(text, name="c")])
    return {p.name: p for p in rec.probes}


def test_a_running_total_propagates_its_holes():
    np = pytest.importorskip("numpy")

    def running_total(xs: np.ndarray) -> np.ndarray:
        return np.cumsum(xs)
    rows = _rows(running_total, "for xs in [0, 1]^n, len(f(xs)) >= 1")
    assert rows["missing[xs]"].verdict == "holds", rows["missing[xs]"].note


def test_a_gram_matrix_propagates_its_holes():
    np = pytest.importorskip("numpy")

    def gram(A: np.ndarray) -> np.ndarray:
        return A.T @ A
    rows = _rows(gram, "for A in [0, 1]^(n,n), f(A) >= 0")
    assert rows["missing[A]"].verdict == "holds", rows["missing[A]"].note


def test_a_trace_is_mixed_where_a_hole_off_the_diagonal_leaves_it_indifferent():
    np = pytest.importorskip("numpy")

    def trace_of(A: np.ndarray) -> float:
        return float(np.trace(A))
    rows = _rows(trace_of, "for A in [0, 1]^(n,n), f(A) >= 0")
    # a finite trace beside a hole breaks "the hole comes back"
    assert rows["missing[A]"].verdict == "falsified", rows["missing[A]"].note
    assert "no fill of the nan slot changes" in rows["missing[A]"].note
    assert rows["c"].meta["mathema.missing"]["indifferent"]["A"] >= 1


def test_an_overflow_under_complete_inputs_is_inconclusive_not_introduced():
    def ema(x: list[float], alpha: float) -> float:
        y = x[0]
        for v in x[1:]:
            y = alpha * v + (1 - alpha) * y
        return y
    import mathema
    rec = mathema.check(ema, claims=[mathema.claim(
        "for alpha in [0, 1], f(x, alpha) <= max(x)")])
    rows = {p.name: p for p in rec.probes}
    assert rows["missing[x]"].verdict != "falsified", rows["missing[x]"].note
    alpha = rows["missing[alpha]"]
    # a written claim's draws carry the policy rows (no rows on a bare check)
    assert alpha.verdict != "falsified", alpha.note
    assert alpha.meta["mathema.policy"]["behaviour"] != "introduces", alpha.meta


def test_a_policy_row_decided_by_refilling_says_so_on_its_route():
    import mathema

    def clamp(x: float) -> float:
        return max(0.0, min(1.0, x))
    rec = mathema.check(clamp, claims=[
        mathema.claim("for x in [0, 1], f(x) >= 0", name="c"),
        mathema.claim("missing(f, x) drops", name="p")])
    routes = {p.route for p in rec.probes if (p.meta or {}).get("mathema.policy")
              and p.route and p.route.startswith("probe")}
    assert routes == {"probe:counterfactual"}, routes


# --- a function that does not repeat itself -------------------------------

def test_an_unseeded_draw_is_never_read_as_reading_its_hole():
    import random
    from mathema._missing_policy import NOT_REPEATABLE

    def noisy(x):
        return random.random()
    for _ in range(20):
        assert _behaviours(noisy, x=NAN) == [NOT_REPEATABLE]


def test_a_deterministic_function_is_unaffected_by_the_repeat():
    assert _behaviours(clamp01, x=NAN) == ["drops"]
    assert _behaviours(root, x=NAN) == ["propagates"]


def test_a_repeat_compares_by_kind():
    from mathema._missing_policy import repeats
    assert repeats((NAN, None), (float("nan"), None))
    assert repeats((None, "ValueError"), (None, "ValueError"))
    assert not repeats((None, "ValueError"), (None, "TypeError"))
    # two answers within floating-point accuracy are one answer
    assert repeats((0.0, None), (-0.0, None))
    assert repeats((1.0, None), (1.0 + 1e-12, None))
    assert not repeats((1.0, None), (1.001, None))
    assert repeats(([1.0, NAN], None), ([1.0, NAN], None))
    assert not repeats(([1.0, 2.0], None), ([1.0, 2.5], None))
