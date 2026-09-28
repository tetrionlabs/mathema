# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness that is a record with no useful repr of its own (an ORM
row, whose default repr is its class and address) is shown by its
public fields, so the witness says which record broke the claim."""
from mathema.probing import _fmt_value


class Row:
    """A record whose repr is Python's default."""

    def __init__(self, sku, quantity):
        self._state = object()
        self.sku = sku
        self.quantity = quantity


class Labelled:
    """A record in the style of a Django model's default repr."""

    def __init__(self, rating):
        self._state = object()
        self.rating = rating

    def __repr__(self):
        return "<Labelled: Labelled object (None)>"


class Shown:
    """A record with a repr of its own, kept as it is."""

    def __init__(self, n):
        self.n = n

    def __repr__(self):
        return f"Shown<{self.n}>"


def test_a_record_with_the_default_repr_is_shown_by_its_fields():
    assert _fmt_value(Row("ABC", 4)) == "Row(sku='ABC', quantity=4)"
    assert _fmt_value(Labelled(1)) == "Labelled(rating=1)"
    assert _fmt_value(Shown(3)) == "Shown<3>"
    assert _fmt_value([Row("A", 1)]) == "[Row(sku='A', quantity=1)]"
