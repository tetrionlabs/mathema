# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A guard that refuses every value outside a set states the
parameter's domain, exactly as `@enforce_domain` to that set does. It
is charged as that domain, not also as a branch and a raise site, so
the two spellings score the same."""
from mathema import enforce_domain
from mathema.badges import _clarity_profile, clarity_score


@enforce_domain({"term": {"1m", "3m", "6m", "12m"}})
def enforced(term: str) -> int:
    """The number of months in a deposit term."""
    return int(term[:-1])


def guarded(term: str) -> int:
    """The number of months in a deposit term."""
    if term not in {"1m", "3m", "6m", "12m"}:
        raise ValueError(term)
    return int(term[:-1])


def guarded_and_branchy(term: str) -> int:
    """The number of months in a deposit term, a year for "1y"."""
    if term not in {"1m", "3m", "6m", "12m", "1y"}:
        raise ValueError(term)
    if term == "1y":
        return 12
    return int(term[:-1])


def test_a_domain_stating_guard_is_not_a_branch_or_a_raise():
    profile = _clarity_profile(guarded, library_keys=frozenset())
    assert (profile.cx, profile.n_raises) == (0, 0)


def test_a_guard_and_enforce_domain_score_the_same():
    rows = [{"name": "months", "statement": "f(term) >= 1",
             "verdict": "proven", "route": "derive:brute_force"}]
    for claims in ([], rows):
        assert clarity_score(guarded, verified_claims=claims,
                             library_keys=frozenset()) == \
            clarity_score(enforced, verified_claims=claims,
                          library_keys=frozenset())


def test_the_function_s_other_branches_still_count():
    profile = _clarity_profile(guarded_and_branchy, library_keys=frozenset())
    assert (profile.cx, profile.n_raises) == (1, 0)
