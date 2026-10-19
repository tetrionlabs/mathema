# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A ground claim names no variable: every call to f in it passes
literal arguments (`f(nan) == 0`, `f([]) == 0`). It states one fact
about one input, so it is decided by evaluating it once at its own
calls: proven when it holds there, falsified when it does not, with
that call as the witness. Nothing is drawn, and a parameter the claim
never reads never appears in the witness."""
import sys

import pytest

from mathema.conjecture import check_conjectures, claim

pd = pytest.importorskip("pandas")


def refuses_nan(x):
    if x != x:
        raise ValueError("nan")
    return x


def exits_on_nan(x):
    if x != x:
        sys.exit(1)
    return x


def total(xs: list) -> float:
    return sum(xs)


def scaled_total(xs: list, k: float) -> float:
    return sum(xs) * k


def series_total(xs: pd.Series) -> float:
    return float(xs.sum())


ROUTES = ("derive", "best", "probe")


def _one(fn, law, route):
    (p,) = [p for p in check_conjectures(fn, [claim(law, route=route)])
            if not p.name.startswith(("is_empty_safe", "is_missing_safe"))]
    return p


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("fn,name", [(refuses_nan, "ValueError"),
                                     (exits_on_nan, "SystemExit")])
def test_a_raise_at_the_literal_call_is_the_witness(fn, name, route):
    p = _one(fn, "f(nan) == 0", route)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample is not None, p.note
    assert p.counterexample.startswith("x = nan: raised " + name), \
        p.counterexample


@pytest.mark.parametrize("route", ROUTES)
def test_a_value_miss_at_the_literal_call_is_the_witness(route):
    p = _one(refuses_nan, "f(2) == 3", route)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample == "x = 2: 2 vs 3", p.counterexample


@pytest.mark.parametrize("route", ("derive", "best"))
@pytest.mark.parametrize("fn,suffix", [(total, ""),
                                       (series_total, ":within_float64")])
def test_a_fixed_input_that_holds_is_proven(fn, suffix, route):
    # float(xs.sum()) is a float pandas computed, with no exact reading:
    # its call is proven within float64, the record saying so
    p = _one(fn, "f([]) == 0", route)
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.route == "derive:brute_force" + suffix, p.route
    assert "mathema.sampling" not in (p.meta or {}), p.meta


@pytest.mark.parametrize("fn", [total, series_total])
def test_the_probe_route_runs_the_call_once(fn):
    p = _one(fn, "f([]) == 0", "probe")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "mathema.sampling" not in (p.meta or {}), p.meta


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("fn,got", [(total, "0"), (series_total, "0.0")])
def test_a_fixed_input_that_fails_names_only_its_call(fn, got, route):
    p = _one(fn, "f([]) == 1", route)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample == f"xs = []: {got} vs 1", p.counterexample


@pytest.mark.parametrize("route", ROUTES)
def test_every_literal_argument_is_in_the_witness(route):
    p = _one(scaled_total, "f([], 2) == 1", route)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample == "xs = [], k = 2: 0 vs 1", p.counterexample


@pytest.mark.parametrize("route", ROUTES)
def test_several_calls_are_named_as_written(route):
    p = _one(refuses_nan, "f(1) + f(2) == 4", route)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample == "f(1), f(2): 3 vs 4", p.counterexample


def test_a_symbolic_proof_of_a_ground_claim_keeps_its_route():
    p = _one(refuses_nan, "f(2) == 2", "derive")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.route)
