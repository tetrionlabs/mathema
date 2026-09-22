# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim floor: the least a function's shape gives you to state.

A floor, not a ceiling. Nothing divides by it, and carrying more claims
than it asks for is not an overrun.
"""
import math
import re

import pytest

from mathema import suggest_claims
from mathema.families import CLAIM_ASPECTS, aspect_label, claim_aspect
from mathema.inventory import claim_floor, is_pure_enough


# --- fixtures: liftable ----------------------------------------------

def add(a: float, b: float) -> float:
    return a + b


def scale(x: float) -> float:
    return x * 2.0


def bs_d1(s: float, k: float, r: float, sig: float, t: float) -> float:
    if sig <= 0 or t <= 0:
        raise ValueError("sig and t must be positive")
    return (math.log(s / k) + (r + sig * sig / 2) * t) / (sig * math.sqrt(t))


def mean(xs) -> float:
    total = 0.0
    for x in xs:
        total += x
    return total / len(xs)


# --- fixtures: genuinely unliftable ----------------------------------

def parse_tag(s: str, k: int) -> int:
    hits = re.findall(r"\d+", s)
    total = 0
    for h in hits:
        total += int(h) * k
    return total


def stateful_io(path: str, x: float) -> float:
    with open(path) as fh:
        first = fh.readline()
    return float(first) * x


ALL = (add, scale, bs_d1, mean, parse_tag, stateful_io)


# add and scale are homogeneous of degree one, so the gated
# scale_equivariant suggestion (proven by construction) joins their
# floor
@pytest.mark.parametrize("fn,expected", [
    (add, 12), (scale, 9), (bs_d1, 26), (mean, 11),
])
def test_floor_for_liftable_shapes(fn, expected):
    assert claim_floor(fn)["floor"] == expected


@pytest.mark.parametrize("fn,expected", [
    (parse_tag, 6), (stateful_io, 8),
])
def test_an_unliftable_function_still_has_a_floor(fn, expected):
    """Most families offer a probe route, so nothing about the floor
    depends on lifting. It shrinks, the derive-only families gate
    themselves out, but it never collapses."""
    assert is_pure_enough(fn) is False
    assert claim_floor(fn)["floor"] == expected


def test_floor_never_exceeds_what_was_suggested():
    """Aspects collapse alternatives; they never invent a claim."""
    for fn in ALL:
        assert claim_floor(fn)["floor"] <= len(suggest_claims(fn))


def test_floor_is_at_least_three_for_any_readable_function():
    """is_deterministic, is_state_safe and is_numerically_stable are
    emitted unconditionally, so a function with zero claims is always
    below its floor, no model needed to say so."""
    for fn in ALL:
        assert claim_floor(fn)["floor"] >= 3


def test_floor_is_none_without_source():
    assert claim_floor(len) is None


def test_aspects_are_reported_with_the_count():
    report = claim_floor(add)
    assert len(report["aspects"]) == report["floor"]
    assert ["is_deterministic", ""] in report["aspects"]


# --- the aspect table ------------------------------------------------

def test_alternatives_about_one_target_collapse():
    """Stating any of convex/concave/affine answers the same question
    about x, so the floor asks for one, not three."""
    assert claim_aspect("convex[x]") == claim_aspect("concave[x]")
    assert claim_aspect("affine[x]") == claim_aspect("convex[x]")
    assert claim_aspect("monotonic_increasing[a]") == claim_aspect("monotonic_decreasing[a]")


def test_the_same_family_on_different_targets_does_not_collapse():
    assert claim_aspect("is_representation_safe[a]") != claim_aspect("is_representation_safe[b]")
    assert claim_aspect("convex[a]") != claim_aspect("convex[b]")


def test_aspect_label_groups_the_suggestion_cross_product():
    # the suggestion column: shape members over one target share a
    # label, so a caller reads one bending question, not three claims.
    assert aspect_label("affine[x]") == "shape[x]"
    assert aspect_label("convex[x]") == "shape[x]"
    assert aspect_label("concave[x]") == "shape[x]"
    assert aspect_label("monotonic_increasing[x]") == "monotonicity[x]"
    assert aspect_label("monotonic_decreasing[x]") == "monotonicity[x]"
    assert aspect_label("even") == aspect_label("odd") == "symmetry"
    # a different target is a different question
    assert aspect_label("convex[y]") == "shape[y]"
    assert aspect_label("convex[x]") != aspect_label("convex[y]")
    # a suggestion that competes with nothing carries no label
    assert aspect_label("idempotent") == ""
    assert aspect_label("is_representation_safe[a]") == ""


def test_every_keyword_group_member_counts_separately():
    """`stateless` expanding to three claims is three separate things
    to say, so a group contributes its full membership, not one."""
    from mathema.families import GROUPS

    for members in GROUPS.values():
        aspects = {claim_aspect(m)[0] for m in members}
        assert len(aspects) == len(set(members))


def test_an_ungrouped_claim_is_its_own_aspect():
    assert claim_aspect("commutative") == ("commutative", "")


def test_every_suggested_claim_maps_to_exactly_one_aspect():
    for fn in ALL:
        for cj in suggest_claims(fn):
            aspect, _ = claim_aspect(cj.name)
            owners = [name for name, members in CLAIM_ASPECTS.items()
                      if aspect == name]
            assert len(owners) <= 1


def test_the_aspect_table_names_only_claims_that_can_be_suggested():
    """A member that no longer appears in any suggestion is a stale
    table entry, so the grouping cannot rot as claim names change."""
    emitted = {cj.name.partition("[")[0] for fn in ALL
               for cj in suggest_claims(fn)}
    listed = {m for members in CLAIM_ASPECTS.values() for m in members}
    assert listed <= emitted, f"unemittable aspect members: {sorted(listed - emitted)}"


# --- what counts toward `actual` -------------------------------------

def guarded(x: float) -> float:
    """Absolute value.

    Claims:
        pos: f(x) >= 0
        small: f(x) <= 100
    """
    return abs(x)


def _verified_with(verdict: str) -> dict:
    return {"k": {"entry": {"claims": [{"name": "pos", "verdict": verdict}]}}}


def test_a_claim_with_no_record_yet_counts():
    from mathema.audit import claimed_count
    assert claimed_count("k", guarded, {}, None) == 2


@pytest.mark.parametrize("verdict", [
    "skipped", "skipped:misspecified", "unliftable",
])
def test_a_blocked_claim_does_not_count(verdict):
    """Adjudication never engaged with it, so it evidences nothing."""
    from mathema.audit import claimed_count
    assert claimed_count("k", guarded, {}, _verified_with(verdict)) == 1


@pytest.mark.parametrize("verdict", [
    "proven", "holds", "unknown", "falsified", "invalidated",
])
def test_an_adjudicated_claim_counts_whatever_the_answer(verdict):
    """A falsified claim is evidence, and an unknown was really tried."""
    from mathema.audit import claimed_count
    assert claimed_count("k", guarded, {}, _verified_with(verdict)) == 2
