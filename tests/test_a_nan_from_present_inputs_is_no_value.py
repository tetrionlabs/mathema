# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The no-value rule: a NaN the code computes from inputs that are not
missing is no value, and fails every relation, `!=` included, another
NaN included. Only an input that was missing makes a missing output a
propagation, compared by kind."""
import pytest

from mathema.conjecture import check_conjectures, claim


def nan_at_half(x: float) -> float:
    return float("nan") if x == 0.5 else x


def always_nan(x: float) -> float:
    return float("nan")


def ident(x):
    return x


def run(fn, text: str, route: str = "probe"):
    return next(p for p in check_conjectures(fn, [claim(text, route=route)])
                if "[" not in p.name)


@pytest.mark.parametrize("relation", ["==", "!=", ">=", "<="])
def test_a_nan_from_a_present_input_fails_every_relation(relation):
    p = run(always_nan, f"for x in [0, 1], f(x) {relation} f(x)")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_nan_at_one_present_point_is_found():
    p = run(nan_at_half, "for x in {0.25, 0.5}, f(x) == x", route="best")
    assert p.verdict == "falsified" and "0.5" in p.counterexample


def test_a_nan_that_propagates_a_listed_hole_agrees_with_itself():
    p = run(ident, "for x in {0.25, nan}, f(x) == x", route="best")
    assert p.verdict == "proven", (p.verdict, p.note)


def lag(a: list[float]) -> list[float]:
    return [float("nan")] + list(a[:-1])


def test_a_nan_slot_the_claim_never_reads_is_no_witness():
    # the claim reads f(a) from its second slot on, past the leading nan
    p = run(lag, "for a in R^n, assuming dim(a) >= 2, f(a)[1:] == a[:-1]")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_a_nan_slot_a_reduction_reads_past_still_fails():
    # sum reads the value slots, so the nan changes nothing it shows, yet
    # the reduction did read the slot f gave no value in
    p = run(lag, "for a in R^n, assuming dim(a) >= 2, sum(f(a)) == sum(a[:-1])")
    assert p.verdict == "falsified", (p.verdict, p.note)
