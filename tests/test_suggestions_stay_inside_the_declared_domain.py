# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema never suggests a claim that calls the function outside its
declared domain. A suggested claim that transforms an argument
(`f(c * x)`, `f(g(xs, c))`, `f(-x)`, `f(y, x)`) binds its variables, in
the grammar's own `for` and `let` forms, so every transformed argument
stays inside the domain the signature or a guard declares; when no such
binding exists the suggestion is not made. A function with no declared
domain gets the suggestions it always got."""
import math

import pytest

from mathema import check, enforce_domain
from mathema.suggest import suggest_claims


@enforce_domain(domain={"weights": (0, 1)})
def mean_weight(weights: list) -> float:
    """The mean of portfolio weights, each guarded to [0, 1]."""
    return sum(weights) / len(weights)


@enforce_domain(domain={"x": (0, 1)})
def unit_root(x: float) -> float:
    return math.sqrt(x)


@enforce_domain(domain={"x": (0, 1)})
def doubled_share(x: float) -> float:
    return 2 * x


@enforce_domain(domain={"x": (-1, 1)})
def cubed_signal(x: float) -> float:
    return x ** 3


@enforce_domain(domain={"a": (0, 1), "b": (0, 2)})
def total_weight(a: float, b: float) -> float:
    return a + b


def plain_mean(weights: list) -> float:
    return sum(weights) / len(weights)


def _suggested(fn):
    return {c.name: c for c in suggest_claims(fn)}


@pytest.mark.parametrize("fn", [mean_weight, unit_root, doubled_share,
                                cubed_signal, total_weight])
def test_no_suggested_row_is_refused_by_the_guard(fn):
    for p in check(fn).probes:
        assert "DomainError" not in str(p.counterexample), (
            fn.__name__, p.name, p.statement, p.counterexample)
        assert "DomainError" not in (p.note or ""), (fn.__name__, p.name,
                                                     p.note)


def test_a_sequence_scaling_restricts_the_factor_to_keep_entries_inside():
    s = _suggested(mean_weight)["scale_equivariant"]
    assert s.domain["c"].pieces == ((0.0, 1.0),), s.domain
    rows = {p.name: p for p in check(mean_weight).probes}
    assert rows["scale_equivariant"].verdict in ("proven", "holds")


def test_a_sequence_shift_binds_the_entries_and_the_shift_together():
    s = _suggested(mean_weight)["translation_equivariant"]
    assert s.domain["weights"].pieces == ((0.25, 0.75),), s.domain
    assert s.domain["c"].pieces == ((-0.25, 0.25),), s.domain


def test_symmetry_is_not_suggested_where_minus_x_leaves_the_guard():
    names = set(_suggested(unit_root))
    assert "even" not in names and "odd" not in names
    assert "idempotent" not in names


def test_symmetry_over_a_symmetric_guard_is_suggested_bound_to_it():
    s = _suggested(cubed_signal)
    assert s["odd"].domain["x"] in ((-1.0, 1.0), [-1.0, 1.0]) or \
        tuple(s["odd"].domain["x"]) == (-1.0, 1.0), s["odd"].domain
    rows = {p.name: p for p in check(cubed_signal).probes}
    assert rows["odd"].verdict == "proven", rows["odd"].note


def test_a_scalar_scaling_restricts_the_factor():
    s = _suggested(doubled_share)["scale_equivariant"]
    assert tuple(s.domain["c"].pieces[0]) == (0.1, 1.0), s.domain


def test_commutativity_binds_both_arguments_to_where_either_slot_admits():
    s = _suggested(total_weight)["commutative"]
    assert tuple(s.domain["a"]) == (0.0, 1.0) and \
        tuple(s.domain["b"]) == (0.0, 1.0), s.domain
    assert "associative" not in _suggested(total_weight)


def test_a_function_with_no_declared_domain_keeps_its_suggestions():
    s = _suggested(plain_mean)
    assert s["scale_equivariant"].domain["c"].pieces == ((-5.0, 5.0),)
    assert "weights" not in s["translation_equivariant"].domain
