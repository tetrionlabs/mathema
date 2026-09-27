# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's space binding (`for a in R^(n,n)`, `for data in R^n`)
drives the draws for a parameter whose kind the signature does not
state, as for a library function: the claim loop draws matrices and
sequences of the bound shape, and the built-in battery's `callable`
row builds its call from the same binding rather than from a scalar."""
import statistics

import pytest

import mathema

np = pytest.importorskip("numpy")


def _check(fn, statement):
    return mathema.check(fn, claims=[statement]).probes


def _declared(probes):
    (p,) = [p for p in probes if p.meta.get("mathema.surface") == "declared"]
    return p


def _callable_row(probes):
    return [p for p in probes if p.name == "callable"]


def test_inv_is_finite_on_nonsingular_matrices():
    p = _declared(_check(np.linalg.inv, "for a in R^(n,n), assuming "
                                        "det(a) != 0, is_finite(f(a))"))
    assert p.verdict == "holds", (p.verdict, p.note)


def test_inv_is_finite_without_a_premise_is_decided_by_executed_draws():
    p = _declared(_check(np.linalg.inv, "for a in R^(n,n), is_finite(f(a))"))
    assert p.verdict in ("holds", "falsified"), (p.verdict, p.note)


def test_the_battery_calls_inv_with_a_matrix_from_the_claims_binding():
    probes = _check(np.linalg.inv, "for a in R^(n,n), assuming det(a) != 0, "
                                   "is_finite(f(a))")
    assert not [p for p in _callable_row(probes) if p.verdict == "skipped"], \
        [p.note for p in _callable_row(probes)]


def test_statistics_mean_lies_between_the_extremes_of_a_sequence():
    probes = _check(statistics.mean,
                    "for data in R^n, min(data) <= f(data) <= max(data)")
    p = _declared(probes)
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert not [p for p in _callable_row(probes) if p.verdict == "skipped"]
