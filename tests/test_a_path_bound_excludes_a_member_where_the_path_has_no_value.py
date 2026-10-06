# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A path binding is a filter on a language's members: a member where
the path has no value is outside the bound.

`for checkout in L[shop], checkout.cart.items[0].quantity in [7, 7]`
admits no absence, so a checkout with an empty cart (the index is past
the end) is outside the binding and never reaches the claim; the record
counts it. Written `| {absent}`, the author admits the empty cart, and
a function returning 0 there is a genuine falsification. `\\ {missing}`
changes nothing: a hole is not a position past the end. A field holding
None is outside the same way. The bound renders in the field's own
type, `[7, 7] : int` for an int field.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from mathema.claims import check_conjectures, claim
from mathema.languages import register_language, unregister_language


@dataclass
class Line:
    quantity: int = 1


@dataclass
class Cart:
    items: list = field(default_factory=list)


@dataclass
class Checkout:
    cart: Cart = field(default_factory=Cart)
    postcode: Optional[str] = ""


MEMBERS = (Checkout(Cart([Line(7)]), "AB1"), Checkout(Cart([]), "EF3"),
           Checkout(Cart([Line(7), Line(2)]), None),
           Checkout(Cart([Line(3)]), "CD2"))


class _Shop:
    """The four checkouts: one with an empty cart, one with no postcode."""
    name, kind, level = "shop_checkout", "object", "finite"

    def contains(self, value):
        return isinstance(value, Checkout)

    def explain(self, value):
        return None

    def sample(self, rng):
        return rng.choice(MEMBERS)

    def members(self, limit):
        return MEMBERS

    def hazards(self):
        return ()

    def outside(self, rng):
        return 3

    def shrink(self, value):
        return ()

    def fields(self):
        return {"cart": {"items": {"[*]": {"quantity": "Z"}}}, "postcode": None}

    def render(self, ascii_mode=True):
        return "L[shop_checkout]"

    def to_json(self):
        return {"type": "object"}


class _Postcodes:
    """Non-empty alphanumeric postcodes."""
    name, kind, level = "postcode", "string", "predicate"

    def contains(self, value):
        return isinstance(value, str) and value.isalnum()

    def explain(self, value):
        return None

    def sample(self, rng):
        return rng.choice(["AB1", "CD2", "EF3"])

    def members(self, limit):
        return None

    def hazards(self):
        return ()

    def outside(self, rng):
        return ""

    def shrink(self, value):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return "L[postcode]"

    def to_json(self):
        return {"type": "string"}


def first_quantity(checkout: Checkout) -> int:
    """The quantity of the first line, 0 for an empty cart."""
    return checkout.cart.items[0].quantity if checkout.cart.items else 0


@pytest.fixture(autouse=True)
def shop():
    register_language("shop_checkout", _Shop())
    register_language("postcode", _Postcodes())
    yield
    unregister_language("shop_checkout")
    unregister_language("postcode")


_FIRST = "for checkout in L[shop_checkout], checkout.cart.items[0].quantity in [7, 7]{}, f(checkout) == 7"


def _one(text, **kw):
    (p,) = check_conjectures(first_quantity, [claim(text, **kw)])
    return p


def _no_value_count(p) -> int:
    return int((p.meta or {}).get("mathema.path_no_value") or 0)


@pytest.mark.parametrize("clause", ["", " \\ {missing}"])
@pytest.mark.parametrize("route", ["best", "probe"])
def test_an_empty_cart_is_outside_the_binding_and_counted(clause, route):
    p = _one(_FIRST.format(clause), route=route)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample, p.note)
    assert _no_value_count(p) >= 1, (p.note, p.meta)
    assert "outside the binding: the path has no value" in (p.note or "") \
        + (p.sketch or ""), (p.note, p.sketch)


@pytest.mark.parametrize("route", ["best", "probe"])
def test_admitting_the_absence_keeps_the_empty_cart_and_falsifies(route):
    p = _one(_FIRST.format(" | {absent}"), route=route)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "items=[]" in (p.counterexample or ""), p.counterexample


def test_a_field_holding_none_is_outside_the_binding_and_counted():
    p = _one("for checkout in L[shop_checkout], checkout.postcode in L[postcode], "
             "f(checkout) >= 0")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample, p.note)
    assert _no_value_count(p) >= 1, (p.note, p.meta)


@pytest.mark.parametrize("clause", ["", " | {absent}", " \\ {missing}"])
def test_the_bound_renders_in_the_fields_own_type(clause):
    p = _one(_FIRST.format(clause))
    assert "[7, 7] : int" in p.statement, p.statement
    assert "7.0" not in p.statement, p.statement
