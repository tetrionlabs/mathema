# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The derive route over a row language lifts the fields the body
reads: a numeric field is one symbol bounded by its constraints (one
side is enough, `price >= 0`), a text field read only as `len(o.sku)`
is one whole number bounded by its length, and a field the body reads
any other way (a categorical, text read as text) declines the lift
with the field named, leaving the claim to the probe."""
import sys
import textwrap

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.domain import Domain, Interval, LanguageRef
from mathema.languages import Problem

ROWS = '''
    from dataclasses import dataclass
    from typing import Annotated, Optional


    @dataclass
    class Order:
        qty: int
        price: float
        kind: str
        sku: str


    @dataclass
    class Annotated_Order:
        qty: int
        price: float
        kind: Optional[str]
        sku: Annotated[str, "at most eight"]


    def labelled_annotated(o: Annotated_Order) -> float:
        """Quantity times price, plus one per character of the sku."""
        return o.qty * o.price + len(o.sku)


    def total(o: Order) -> float:
        """Quantity times price."""
        return o.qty * o.price


    def labelled(o: Order) -> float:
        """Quantity times price, plus one per character of the sku."""
        return o.qty * o.price + len(o.sku)


    def short_label(o: Order) -> int:
        """The sku's length, at most eight."""
        return len(o.sku)


    def discounted(o: Order) -> float:
        """Ten percent off a promotional sku."""
        return o.qty * o.price * (0.9 if o.sku.startswith("PROMO") else 1.0)


    def by_kind(o: Order) -> float:
        """Web orders pay a flat two on top."""
        return o.qty * o.price + (2.0 if o.kind == "web" else 0.0)
'''


class _Orders:
    """A row language whose fields state one-deep bounds the way the
    package's adaptors do: numbers as intervals (one side open), a
    categorical as None, text as a length-bounded language."""
    kind = "row"
    level = "schema"

    def __init__(self, cls):
        self.cls = cls
        self.name = f"{cls.__module__}.{cls.__qualname__}"

    def contains(self, v):
        return (isinstance(v, self.cls) and 1 <= v.qty <= 10 and v.price >= 0
                and v.kind in ("web", "shop") and isinstance(v.sku, str) and len(v.sku) <= 8)

    def explain(self, v):
        return None if self.contains(v) else [Problem("", "Order", v)]

    def sample(self, rng):
        return self.cls(qty=rng.randint(1, 10), price=rng.uniform(0, 100),
                        kind=rng.choice(("web", "shop")),
                        sku="".join(rng.choice("ABC") for _ in range(rng.randint(0, 8))))

    def members(self, limit):
        return None

    def hazards(self):
        return ()

    def outside(self, rng):
        return self.cls(qty=0, price=-1.0, kind="web", sku="")

    def shrink(self, v):
        return ()

    def fields(self):
        return {"qty": Domain(base_type="Z", pieces=(Interval(1.0, 10.0),), explicit_type=True),
                "price": Interval(0.0, float("inf")),
                "kind": None,
                "sku": LanguageRef("unicode", (("len", Interval(0.0, 8.0)),))}

    def render(self, ascii_mode=True):
        return f"L[{self.name}]"

    def to_json(self):
        return {"type": "object"}


class _Entry:
    def __init__(self, name, value, obj):
        self.name, self.value, self._obj = name, value, obj

    def load(self):
        return self._obj


@pytest.fixture
def orders(monkeypatch, tmp_path):
    import dataclasses
    import importlib.util

    def adapt(obj):
        return _Orders(obj) if isinstance(obj, type) and dataclasses.is_dataclass(obj) else None

    monkeypatch.setattr(languages, "_discovered_adaptors",
                        lambda: (_Entry("rows", "pkg.mod:adapt", adapt),))
    languages._loaded_adaptors.cache_clear()
    path = tmp_path / "lift_rows.py"
    path.write_text(textwrap.dedent(ROWS))
    spec = importlib.util.spec_from_file_location("lift_rows", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lift_rows"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("lift_rows", None)
    languages._loaded_adaptors.cache_clear()


def _derive(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    return p


@pytest.mark.needs_full_proof_budget
def test_the_numeric_fields_the_body_reads_are_lifted(orders):
    p = _derive(orders.total, "for o in L[lift_rows.Order], f(o) >= 0")
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)


@pytest.mark.needs_full_proof_budget
def test_a_text_field_read_only_through_len_is_a_bounded_whole_number(orders):
    p = _derive(orders.labelled, "for o in L[lift_rows.Order], f(o) >= 0")
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
    q = _derive(orders.short_label, "for o in L[lift_rows.Order], f(o) <= 8")
    assert q.verdict == "proven", (q.verdict, q.note, q.sketch)


def test_a_text_field_read_as_text_declines_naming_the_field(orders):
    p = _derive(orders.discounted, "for o in L[lift_rows.Order], f(o) >= 0")
    assert p.verdict != "proven"
    assert "o.sku" in (p.note or "") + str(p.sketch or ""), (p.note, p.sketch)


def test_a_categorical_field_the_body_reads_declines_naming_the_field(orders):
    p = _derive(orders.by_kind, "for o in L[lift_rows.Order], f(o) >= 0")
    assert p.verdict != "proven"
    assert "o.kind" in (p.note or "") + str(p.sketch or ""), (p.note, p.sketch)


def test_the_best_route_still_samples_what_derive_declines(orders):
    (p,) = check_conjectures(orders.discounted, [claim("for o in L[lift_rows.Order], f(o) >= 0")])
    assert p.verdict == "holds", (p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
def test_len_lifts_when_every_field_annotation_is_a_typing_form(orders):
    # a typing form (Optional, Annotated) is accepted by the older
    # expansion rule, and len(o.sku) must still lift as a length
    p = _derive(orders.labelled_annotated,
                "for o in L[lift_rows.Annotated_Order], f(o) >= 0")
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
