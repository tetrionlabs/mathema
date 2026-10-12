# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every claim earns something: a claim covering a share `s` of the
function's domain is credited `s + 0.1 * (1 - s)` of what the same
claim over the whole domain would earn, so a proof at three points of a
bare `str` earns a tenth, a claim over a stated domain earns nearly all
of it, and a claim over everything earns exactly all of it. The floor
counts once per source, so many tiny claims cannot farm it."""
import pytest

from mathema.badges import _CLAIM_FLOOR, _clarity_profile, _reductions


def side_key(side: str) -> str:
    """The order side as a lower-case word."""
    return side.strip().lower()


def fahrenheit(c: float) -> float:
    """A Celsius temperature in Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


def _identity(fn, statement):
    profile = _clarity_profile(fn, library_keys=frozenset())
    return _reductions([{"name": "law", "statement": statement,
                         "verdict": "proven", "route": "derive"}],
                       profile.pure, profile)["identity"]


def test_the_floor_is_a_tenth():
    assert _CLAIM_FLOOR == 0.1


def test_a_proof_at_three_points_of_a_bare_str_earns_the_floor():
    assert _identity(side_key, 'for side in {"BUY", "Buy", " buy "}, '
                     'f(side) == "buy"') == pytest.approx(0.1)


def test_a_range_earns_its_share_and_the_floor_on_the_rest():
    s = _identity(fahrenheit, "for c in [0, 100], f(c) == 1.8*c + 32")
    assert s == pytest.approx(0.2515 + 0.1 * (1 - 0.2515), abs=1e-4)


def test_a_claim_over_everything_earns_exactly_all():
    assert _identity(fahrenheit, "f(c) == 1.8*c + 32") == 1.0


def test_many_tiny_claims_earn_the_floor_once():
    profile = _clarity_profile(fahrenheit, library_keys=frozenset())
    rows = [{"name": f"at{i}", "statement": f"for c in {{{float(i)}}}, "
             "f(c) == 1.8*c + 32", "verdict": "proven",
             "route": "derive:brute_force"} for i in range(20)]
    assert _reductions(rows, profile.pure, profile)["identity"] == \
        pytest.approx(0.1, abs=1e-9)
