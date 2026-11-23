# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Verdicts one step beside false proofs already fixed. A literal nan
passed to f is a missing value, as None is, and the call is run. The
empty tuple is an empty input of every annotation that admits a tuple.
A wrapper that enforces a wider domain than the claim's does not refuse
everything outside the claim's. A side of the claim that has no float
value only because an intermediate rounded is not a counterexample to
the mathematics. A missing value the domain lists is run for
`is_defined`. A witness shows the arguments the call passed."""
import math
from typing import Optional, Sequence, Union

import pytest

from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


# --- a literal nan argument ---------------------------------------------------

def one_at_nan(x, y=0.0):
    if x != x:
        return 1.0
    return 0.0


def one_at_none(x, y=0.0):
    if x is None:
        return 1.0
    return 0.0


@pytest.mark.parametrize("text", [
    "for x in {1}, f(nan, 0.5) == 0",
    "for x in {1}, f(inf - inf, 0.5) == 0",
    "for x in {1}, f(x=nan, y=0.5) == 0",
])
def test_a_call_passing_nan_is_run_not_read_as_a_real_number(text):
    p = _row(one_at_nan, text)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)
    assert "x = nan" in (p.counterexample or ""), p.counterexample


def test_a_call_passing_a_nan_the_claim_cannot_run_is_not_proven():
    # the claim's own words do not include `float`, so the call is not run
    p = _row(one_at_nan, "for x in {1}, f(float('nan'), 0.5) == 0")
    assert p.verdict in ("falsified", "unknown"), (p.verdict, p.sketch, p.note)


def test_a_true_claim_about_a_call_passing_nan_is_not_falsified():
    p = _row(one_at_nan, "for x in {1}, f(nan, 0.5) == 1")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.sketch, p.note)
    p = _row(one_at_nan, "for x in [0, 1], f(x, nan) == 0")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.sketch, p.note)


def test_the_witness_shows_the_arguments_a_keyword_call_passed():
    p = _row(one_at_none, "for x in {1}, f(x=None, y=0.5) == 0")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    assert "x = None" in (p.counterexample or ""), p.counterexample
    assert "x = 1" not in (p.counterexample or ""), p.counterexample


# --- the empty tuple ----------------------------------------------------------

def mean_union(xs: Union[list, tuple]) -> float:
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)


def mean_bar(xs: "list[float] | tuple[float, ...]") -> float:
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)


def mean_optional(xs: Optional[Sequence[float]]) -> float:
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)


def mean_union_guarded(xs: Union[list, tuple]) -> float:
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def mean_list(xs: Optional[list]) -> float:
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)


@pytest.mark.parametrize("fn", [mean_union, mean_bar, mean_optional])
def test_the_empty_tuple_is_tried_where_the_annotation_admits_a_tuple(fn):
    p = _row(fn, "is_empty_safe(xs)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    assert "()" in (p.counterexample or ""), p.counterexample


@pytest.mark.parametrize("fn", [mean_union_guarded, mean_list])
def test_a_function_safe_at_every_empty_input_it_admits_stays_proven(fn):
    p = _row(fn, "is_empty_safe(xs)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)


# --- a wrapper enforcing another domain ---------------------------------------

@enforce_domain({"x": "[0, 100]"})
def wide(x):
    return x * 2.0


@enforce_domain({"x": "[0, 1]"})
def exact(x):
    return x * 2.0


def test_a_wider_enforced_domain_does_not_exclude_outside_the_claims():
    p = _row(wide, "for x in [0, 1], excluded_outside_domain(x)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)


@pytest.mark.parametrize("fn, text", [
    (wide, "for x in [0, 100], excluded_outside_domain(x)"),
    (wide, "for x in [0, 200], excluded_outside_domain(x)"),
    (wide, "excluded_outside_domain(x)"),
    (exact, "for x in [0, 1], excluded_outside_domain(x)"),
])
def test_an_enforced_domain_inside_the_claims_excludes_by_construction(
        fn, text):
    p = _row(fn, text)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)


# --- a float-only failure of the claim's own side -----------------------------

def summed(x):
    return math.fsum([x])


def test_a_log_of_an_underflow_does_not_falsify_the_mathematics():
    p = _row(summed, "for x in R, log(exp(f(x))) == f(x)")
    assert p.verdict == "unknown", (p.verdict, p.counterexample, p.note)
    assert "read exactly it has a value" in (p.note or ""), p.note


def test_a_side_with_no_real_value_read_exactly_still_falsifies():
    p = _row(summed, "for x in [-2, -1], log(f(x)) == log(f(x))")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    p = _row(summed, "for x in [-2, -1], sqrt(f(x)) * sqrt(f(x)) == f(x)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)


def test_a_false_claim_is_still_falsified_where_its_side_has_a_value():
    p = _row(summed, "for x in R, log(exp(f(x))) == f(x) + 1")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)


# --- a listed missing value under is_defined ----------------------------------

def raises_in_a_gap(x, y):
    if x is None and 0.6 < y < 0.7:
        raise ValueError("gap")
    return 0.0


def floors(x):
    return float(math.floor(x))


def guarded(x, y):
    if x is None:
        return 0.0
    return x * 2.0 + y


def test_a_listed_missing_value_that_raises_falsifies_is_defined():
    p = _row(raises_in_a_gap, "for x in {1, None}, y in {0.65}, is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    assert "x = None" in (p.counterexample or ""), p.counterexample
    assert "0.65" in (p.counterexample or ""), p.counterexample
    p = _row(floors, "for x in {1, nan}, is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    assert "nan" in (p.counterexample or ""), p.counterexample


def test_a_listed_missing_value_the_function_handles_does_not_falsify():
    p = _row(guarded, "for x in {1, None}, y in {0.65}, is_defined(f)")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.sketch, p.note)
