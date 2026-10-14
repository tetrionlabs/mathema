# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witnessed falsification is knowledge about the claim it refutes,
and only that: `f(x) == 2*x` shown wrong at a witness credits what the
function computes, but says nothing about its output's envelope, its
shape or what it accepts, which a proven identity would settle."""
from mathema.badges import _BITS, _clarity_profile, _reductions, clarity_score


def double(x: float) -> float:
    """Twice x."""
    return 2.0 * x


def _row(verdict):
    return {"name": "doubles", "statement": "f(x) == 2*x",
            "verdict": verdict, "route": "derive"}


def test_a_falsified_identity_credits_only_what_the_function_computes():
    profile = _clarity_profile(double, library_keys=frozenset())
    r = _reductions([_row("falsified")], profile.pure, profile)
    assert r["identity"] > 0
    assert r["extent"] == r["shape"] == 0.0
    assert r["domain_soft:x"] == _BITS["base_domain_soft"]


def test_a_falsified_identity_still_counts_as_knowledge():
    assert clarity_score(double, verified_claims=[_row("falsified")]) > \
        clarity_score(double, verified_claims=[])
