# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`enforce_domain` over a language domain judges the argument as one
value: a member that happens to be iterable (a pydantic model yields its
fields, a list yields its items) is a member or not as a whole, never
item by item. A refusal names why, from the language's own
explanation, and shows a record by its fields."""
import pytest

from mathema import DomainError, claims_decorator, enforce_domain
from mathema.languages import Problem, register_language, unregister_language


class Line:
    """A record that iterates over its fields, as a pydantic model does."""

    def __init__(self, sku, qty):
        self.sku, self.qty = sku, qty

    def __iter__(self):
        return iter([("sku", self.sku), ("qty", self.qty)])


class _Lines:
    name = "lines"
    kind = "row"
    level = "schema"

    def members(self, limit):
        return None

    def contains(self, value):
        return isinstance(value, Line) and value.qty >= 1

    def explain(self, value):
        if self.contains(value):
            return None
        return [Problem(".qty", "qty >= 1", getattr(value, "qty", value))]

    def sample(self, rng):
        return Line("A", rng.randint(1, 5))

    def hazards(self):
        return ()

    def outside(self, rng):
        return Line("A", 0)

    def shrink(self, value):
        return iter(())

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return "L[lines]"

    def to_json(self):
        return {"type": "object"}


class _Pairs(_Lines):
    name = "pairs"
    kind = "sequence"

    def contains(self, value):
        return isinstance(value, list) and len(value) == 2 and value[0] <= value[1]

    def explain(self, value):
        return None if self.contains(value) else [Problem("", "an ordered pair", value)]

    def render(self, ascii_mode=True):
        return "L[pairs]"


@pytest.fixture
def languages():
    register_language("lines", _Lines())
    register_language("pairs", _Pairs())
    try:
        yield
    finally:
        unregister_language("lines")
        unregister_language("pairs")


def test_an_iterable_record_that_is_a_member_is_accepted(languages):
    @enforce_domain()
    @claims_decorator("for line in L[lines], f(line) >= 1")
    def quantity(line):
        return line.qty

    assert quantity(Line("A", 2)) == 2


def test_a_list_that_is_a_member_is_accepted_and_one_that_is_not_is_refused(languages):
    @enforce_domain()
    @claims_decorator("for pair in L[pairs], f(pair) >= 0")
    def width(pair):
        return pair[1] - pair[0]

    assert width([1, 3]) == 2
    with pytest.raises(DomainError, match=r"pair=\[3, 1\] outside its declared domain L\[pairs\]"):
        width([3, 1])


def test_a_refusal_says_why_and_shows_the_record_by_its_fields(languages):
    @enforce_domain()
    @claims_decorator("for line in L[lines], f(line) >= 1")
    def quantity(line):
        return line.qty

    with pytest.raises(DomainError) as refused:
        quantity(Line("A", 0))
    message = str(refused.value)
    assert "sku='A'" in message and "qty=0" in message
    assert "at .qty: qty >= 1" in message
    assert "object at 0x" not in message
