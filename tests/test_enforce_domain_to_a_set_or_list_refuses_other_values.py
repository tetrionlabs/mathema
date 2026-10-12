# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`@enforce_domain` given a set or a list of values guards the same
finite set a frozenset does: a member passes, anything else is refused
before the body runs, and clarity reads the parameter as that finite
set. A tuple or list of two numbers stays an interval."""
import pytest

import mathema
from mathema.authoring import DomainError
from mathema.badges import _clarity_profile


def _key(name: str) -> str:
    """The lookup key for a username."""
    return name.strip().lower()


@pytest.mark.parametrize("values", [
    {"buy", "sell"}, ["buy", "sell"], ("buy", "sell"), frozenset({"buy", "sell"})],
    ids=["set", "list", "tuple", "frozenset"])
def test_a_collection_of_strings_is_enforced_as_a_finite_set(values):
    guarded = mathema.enforce_domain({"name": values})(_key)
    assert guarded("buy") == "buy"
    with pytest.raises(DomainError):
        guarded("hold")


@pytest.mark.parametrize("values", [{1, 2, 5}, [1, 2, 5]], ids=["set", "list"])
def test_a_collection_of_numbers_is_enforced_as_a_finite_set(values):
    def twice(n: int) -> int:
        """Twice n."""
        return 2 * n
    guarded = mathema.enforce_domain({"n": values})(twice)
    assert guarded(5) == 10
    with pytest.raises(DomainError):
        guarded(3)


@pytest.mark.parametrize("values", [{"buy", "sell"}, ["buy", "sell"]],
                         ids=["set", "list"])
def test_clarity_reads_an_enforced_set_or_list_as_a_finite_set(values):
    guarded = mathema.enforce_domain({"name": values})(_key)
    (d,) = _clarity_profile(guarded).domains
    assert (d.finite, d.points) == (True, 2)


@pytest.mark.parametrize("bounds", [(0.0, 1.0), [0.0, 1.0]], ids=["tuple", "list"])
def test_two_numbers_stay_an_interval(bounds):
    def half(x: float) -> float:
        """Half of x."""
        return x / 2.0
    guarded = mathema.enforce_domain({"x": bounds})(half)
    assert guarded(0.25) == 0.125
    with pytest.raises(DomainError):
        guarded(1.5)
