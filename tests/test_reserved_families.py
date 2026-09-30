# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Four computation-safety families are named now and adjudicated in a
later release: a claim naming one (`is_concurrency_safe(f)`, say) is a
known claim, `skipped` with a note saying it is reserved, and none is
ever suggested. Platforms (a GPU, a JIT, a distributed runtime) are
named in the bracketed computation descriptor, never in a family
name."""
import pytest

RESERVED = ("is_precision_safe", "is_order_invariant",
            "is_concurrency_safe", "is_representation_consistent")


def half(x: float) -> float:
    """Half."""
    return x / 2


@pytest.mark.parametrize("name", RESERVED)
def test_a_reserved_family_is_skipped_with_the_reason(name):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(half, [claim(f"{name}(f)", route="best")])
    assert p.verdict == "skipped", (p.verdict, p.note)
    assert "reserved for a later release" in (p.note or ""), p.note


@pytest.mark.parametrize("name", RESERVED)
def test_a_reserved_family_is_registered(name):
    from mathema.families import families
    assert name in families()


def test_no_reserved_family_is_suggested():
    from mathema.suggest import suggest_claims
    names = {c.name.split("[", 1)[0] for c in suggest_claims(half)}
    assert not names & set(RESERVED)


def test_no_reserved_family_credits_a_clarity_source():
    from mathema.badges import _SAFETY_SOURCE
    assert not set(_SAFETY_SOURCE) & set(RESERVED)
