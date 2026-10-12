# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A missing-value policy row (`missing[x]`, `missing(f, x) propagates`)
says what the function does with a missing value. It credits the
missing-values source and nothing else: it is not a claim about the
function's shape."""
from mathema.badges import _clarity_profile, _reductions


def double(x: float) -> float:
    """Twice x."""
    return 2.0 * x


def total(xs: list) -> float:
    """The sum of xs."""
    return float(sum(xs))


def _row(param):
    return {"name": f"missing[{param}]",
            "statement": f"missing(f, {param}) propagates",
            "verdict": "holds", "route": "probe:counterfactual",
            "meta": {"mathema.policy": {"kind": "missing", "parameter": param}}}


def test_a_missing_value_policy_is_not_a_shape_claim():
    profile = _clarity_profile(double, library_keys=frozenset())
    assert _reductions([_row("x")], profile.pure, profile)["shape"] == 0.0


def test_a_missing_value_policy_credits_the_missing_values_source():
    profile = _clarity_profile(total, library_keys=frozenset())
    before = _reductions([], profile.pure, profile)["safety:is_missing_safe"]
    after = _reductions([_row("xs")], profile.pure, profile)["safety:is_missing_safe"]
    assert after > before
