# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A decorator runs when the function is defined, so clarity does not
charge it as a call the function makes: `@enforce_domain(...)` costs
nothing in *where it can go wrong*."""
from mathema import enforce_domain
from mathema.badges import _clarity_profile


@enforce_domain({"term": {"1m", "3m", "6m", "12m"}})
def term_months(term: str) -> int:
    """The number of months in a deposit term."""
    return int(term[:-1])


def test_enforce_domain_is_not_a_callee():
    assert _clarity_profile(term_months, library_keys=frozenset()).callees == ()
