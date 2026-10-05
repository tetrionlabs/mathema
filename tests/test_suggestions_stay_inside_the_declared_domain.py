# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema never suggests a claim that calls the function outside its
declared domain. A suggested claim that transforms an argument
(`f(c * x)`, `f(g(xs, c))`, `f(-x)`, `f(y, x)`) binds its variables, in
the grammar's own `for` and `let` forms, so every transformed argument
stays inside the domain the signature or a guard declares; when no such
binding exists the suggestion is not made. Idempotence and
associativity feed the function's own output back in, so they are
stated over the whole declared domain: an output that leaves it is a
call outside it, and the row falsifies with that call as the witness.
A function with no declared domain gets the suggestions it always
got."""
import math

import pytest

from mathema import check, claims_decorator, enforce_dimensions, enforce_domain
from mathema.conjecture import claim
from mathema.suggest import suggest_claims
from mathema.types import Vec


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
        if p.name in ("idempotent", "associative"):
            continue
        assert "DomainError" not in str(p.counterexample), (
            fn.__name__, p.name, p.statement, p.counterexample)
        assert "DomainError" not in (p.note or ""), (fn.__name__, p.name,
                                                     p.note)


def test_a_sequence_scaling_restricts_the_factor_to_keep_entries_inside():
    s = _suggested(mean_weight)["scale_equivariant"]
    assert s.domain["c"].pieces == ((0.0, 1.0),), s.domain
    rows = {p.name: p for p in check(mean_weight).probes}
    row = rows["scale_equivariant"]
    # every scaled call stays inside the domain; only the empty list,
    # which has no mean, falls, on the empty-input line
    assert row.verdict == "falsified", (row.verdict, row.counterexample)
    assert row.counterexample.startswith("weights = []"), row.counterexample


def test_a_sequence_shift_binds_the_entries_and_the_shift_together():
    s = _suggested(mean_weight)["translation_equivariant"]
    assert s.domain["weights"].pieces == ((0.25, 0.75),), s.domain
    assert s.domain["c"].pieces == ((-0.25, 0.25),), s.domain


def test_symmetry_is_not_suggested_where_minus_x_leaves_the_guard():
    names = set(_suggested(unit_root))
    assert "even" not in names and "odd" not in names


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


def test_idempotence_is_stated_over_the_whole_declared_domain():
    s = _suggested(doubled_share)["idempotent"]
    assert tuple(s.domain["x"]) == (0.0, 1.0), s.domain
    rows = {p.name: p for p in check(doubled_share).probes}
    # f(1) = 2 leaves [0, 1], so f(f(1)) is a call the guard refuses
    assert rows["idempotent"].verdict == "falsified"
    assert "DomainError" in rows["idempotent"].counterexample


def test_associativity_binds_both_arguments_and_c_to_their_domains():
    s = _suggested(total_weight)["associative"]
    assert tuple(s.domain["a"]) == (0.0, 1.0), s.domain
    assert tuple(s.domain["b"]) == (0.0, 2.0), s.domain
    assert tuple(s.domain["c"].pieces[0]) == (0.0, 2.0), s.domain
    rows = {p.name: p for p in check(total_weight).probes}
    assert rows["associative"].verdict == "falsified"
    assert "DomainError" in rows["associative"].counterexample


def test_a_function_with_no_declared_domain_keeps_its_suggestions():
    s = _suggested(plain_mean)
    assert s["scale_equivariant"].domain["c"].pieces == ((-5.0, 5.0),)
    assert "weights" not in s["translation_equivariant"].domain


SEEN: list = []


@enforce_domain()
@claims_decorator("for xs in [0, 1]^n, f(xs) >= 0")
def share_total(xs: Vec("n")) -> float:
    """Sum of shares, each guarded to [0, 1] by the space the claim binds."""
    return sum(xs)


@enforce_dimensions()
@claims_decorator("for xs in [0, 1]^30, f(xs) >= 0")
def share_total_30(xs: Vec("n")) -> float:
    """Sum of thirty shares, the space the claim binds fixing the size
    and the entries."""
    SEEN.extend(v for v in xs if isinstance(v, (int, float))
                and math.isfinite(v))
    return sum(xs)


def test_a_space_in_a_guard_bounds_the_suggested_transforms_entrywise():
    s = _suggested(share_total)
    assert s["scale_equivariant"].domain["c"].pieces == ((0.0, 1.0),), \
        s["scale_equivariant"].domain
    assert s["translation_equivariant"].domain["xs"].pieces == \
        ((0.25, 0.75),), s["translation_equivariant"].domain
    for p in check(share_total).probes:
        assert "DomainError" not in str(p.counterexample), (
            p.name, p.statement, p.counterexample)


def test_every_entry_drawn_lies_in_the_space_enforce_dimensions_guards():
    SEEN.clear()
    check(share_total_30)
    assert SEEN
    # the round-off estimate of a value comparison recomputes a draw
    # with its entries moved by a few units in the last place, and
    # never moves one out of the space
    outside = sorted({v for v in SEEN if not 0 <= v <= 1})
    assert not outside, outside[:10]


def log_guarded(x: float) -> float:
    if x <= 0:
        raise ValueError("log of a nonpositive number")
    return math.log(x)


def cut_at_zero(x: float) -> float:
    if x == 0:
        raise ValueError("zero")
    if x < -1 or x > 1:
        raise ValueError("outside")
    return 1 / x


def cut_inside(x: float) -> float:
    if x < 0 or x > 1:
        raise ValueError("outside")
    if 0.4 < x < 0.6:
        raise ValueError("hole")
    return 2 * x


_SPLIT = claim("for w in [-1, -0.5] ∪ [0.5, 3], f(w) >= -1").domain["w"]


@enforce_domain(domain={"w": _SPLIT})
def split_mean(w: list) -> float:
    return sum(w) / len(w)


def test_a_conditional_raise_cuts_the_domain_a_suggestion_binds():
    s = _suggested(log_guarded)
    assert tuple(s["monotonic_increasing[x]"].domain["x"]) == (0.0, math.inf)
    rows = {p.name: p for p in check(log_guarded).probes}
    assert rows["monotonic_increasing[x]"].verdict == "proven", (
        rows["monotonic_increasing[x]"].counterexample)


@pytest.mark.parametrize("fn", [log_guarded, cut_at_zero, cut_inside],
                         ids=lambda f: f.__name__)
def test_no_suggestion_calls_into_a_region_a_guard_raises_in(fn):
    for p in check(fn).probes:
        if p.name.startswith(("raises[", "idempotent")):
            continue
        assert "ValueError" not in str(p.counterexample), (
            fn.__name__, p.name, p.statement, p.counterexample)


def test_a_hole_cut_by_a_guard_stays_out_of_the_binding():
    s = _suggested(cut_inside)
    pieces = s["monotonic_increasing[x]"].domain["x"].pieces
    assert [tuple(p) for p in pieces] == [(0.0, 0.4), (0.6, 1.0)], pieces
    # no symmetric part survives the cut, so neither symmetry is asked
    assert "even" not in s and "odd" not in s


def test_a_shift_over_a_union_stays_in_the_widest_piece():
    s = _suggested(split_mean)["translation_equivariant"]
    assert tuple(s.domain["w"].pieces[0]) == (1.125, 2.375), s.domain
    assert tuple(s.domain["c"].pieces[0]) == (-0.625, 0.625), s.domain
    for p in check(split_mean).probes:
        assert "DomainError" not in str(p.counterexample), (
            p.name, p.statement, p.counterexample)
