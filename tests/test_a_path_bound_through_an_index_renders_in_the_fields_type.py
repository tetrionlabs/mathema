# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A path bound reached through a list index renders in the field's
own type.

`o.lines[0].qty in [7, 7]` over an int field reads `[7, 7] : int`,
however the language's `fields()` spells the elements of the list:
nested under `"[*]"`, as a one-item list, as the element record itself,
or under a `lines[*]` key. The `[*]` form of the path reads the same.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from mathema.claims import check_conjectures, claim
from mathema.languages import register_language, unregister_language


@dataclass
class Line:
    qty: int = 1


@dataclass
class Order:
    lines: list = field(default_factory=list)
    total: int = 0


MEMBERS = (Order([Line(7)], 7), Order([Line(7), Line(2)], 9), Order([Line(3)], 3))

SHAPES = {
    "nested": {"lines": {"[*]": {"qty": "Z"}}, "total": "Z"},
    "list": {"lines": [{"qty": "Z"}], "total": "Z"},
    "record": {"lines": {"qty": "Z"}, "total": "Z"},
    "starred key": {"lines[*]": {"qty": "Z"}, "total": "Z"},
}


class _Orders:
    name, kind, level = "orders", "object", "finite"

    def __init__(self, fields):
        self._fields = fields

    def contains(self, value):
        return isinstance(value, Order)

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
        return self._fields

    def render(self, ascii_mode=True):
        return "L[orders]"

    def to_json(self):
        return {"type": "object"}


def first_qty(o: Order) -> int:
    return o.lines[0].qty


@pytest.fixture(params=sorted(SHAPES))
def orders(request):
    register_language("orders", _Orders(SHAPES[request.param]))
    yield request.param
    unregister_language("orders")


@pytest.mark.parametrize("path", ["o.lines[0].qty", "o.lines[*].qty"])
def test_the_bound_takes_the_int_type_of_the_element_field(orders, path):
    (p,) = check_conjectures(first_qty, [claim(
        f"for o in L[orders], {path} in [7, 7], f(o) == 7", route="probe")])
    assert f"{path} in [7, 7] : int" in p.statement, (orders, p.statement)
    assert "7.0" not in p.statement, p.statement


def test_a_direct_int_field_still_reads_int(orders):
    (p,) = check_conjectures(first_qty, [claim(
        "for o in L[orders], o.total in [7, 7], f(o) == 7", route="probe")])
    assert "o.total in [7, 7] : int" in p.statement, p.statement
