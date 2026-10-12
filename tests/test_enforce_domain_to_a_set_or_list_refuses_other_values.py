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


@pytest.mark.parametrize("values, member, outsider", [
    ([0, "a"], "a", 1), ({1, "x", None}, None, "y"), ((1, 2, 3), 3, 4),
    (["a"], "a", "b")], ids=["mixed list", "mixed set", "three numbers",
                             "one string"])
def test_any_other_collection_is_the_finite_set_of_its_members(values, member,
                                                               outsider):
    def echo(v):
        """The value itself."""
        return v
    guarded = mathema.enforce_domain({"v": values})(echo)
    assert guarded(member) == member
    with pytest.raises(DomainError):
        guarded(outsider)


@pytest.mark.parametrize("text, inside, outside", [
    ("(0, 1]", [1.0, 0.5], [0.0, 1.5]),
    ("[-1, -0.5] ∪ [0.5, 3]", [-0.75, 2.0], [0.0, 3.5]),
    ("[0, 1)", [0.0], [1.0])])
def test_a_string_is_read_in_the_domain_grammar(text, inside, outside):
    def half(x: float) -> float:
        """Half of x."""
        return x / 2.0
    guarded = mathema.enforce_domain({"x": text})(half)
    for x in inside:
        assert guarded(x) == x / 2.0
    for x in outside:
        with pytest.raises(DomainError):
            guarded(x)


def test_a_string_the_grammar_cannot_read_is_refused_when_decorating():
    def half(x: float) -> float:
        """Half of x."""
        return x / 2.0
    with pytest.raises(DomainError, match="interval"):
        mathema.enforce_domain({"x": "from zero to one"})(half)
