# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive reads a categorical record field by splitting on its levels.

A field holding one of a few strings (`o.kind`, a command name, a
`Literal` field) is no number, so it is never a symbol. Where its levels
are stated, by the claim (`o.kind in {"restock", "discount"}`) or by the
record's language, derive proves the claim once per level with the
field bound to that level, so every branch that reads it settles: the
claim is proven when every case is, and otherwise left to running the
code. With no level stated the field still has no reading. Identity (`is`,
`is not`) against anything but a singleton (None, True, False,
Ellipsis) depends on how the runtime interns its objects, so derive
never decides such a branch: the code is run instead.
"""
import sys
import textwrap

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.domain import Domain, Interval

ORDERS = '''
    from dataclasses import dataclass


    @dataclass
    class Order:
        kind: str
        qty: int


    @dataclass
    class Untyped:
        kind: str
        qty: int


    @dataclass
    class Wide:
        kind: str
        qty: int


    def units(o: Order) -> int:
        if o.kind == "restock":
            return o.qty * 12
        return 0


    def untyped_units(o: Untyped) -> int:
        if o.kind == "restock":
            return o.qty * 12
        return 0


    def wide_units(o: Wide) -> int:
        if o.kind == "a":
            return o.qty * 12
        return 0


    def is_not_export(o: Order) -> int:
        if o.kind is not "export":
            return o.qty * 12
        return 1000


    def identity_of_text(s: str, x: float) -> float:
        if s is not "export":
            return x
        return 1000.0


    def none_checked(o: Order) -> int:
        if o.kind is None:
            return 1000
        return o.qty * 12


    def initial_units(o: Order) -> float:
        return 12.0 if o.kind.startswith("r") else 0.0
'''

_QTY = Domain(base_type="Z", pieces=(Interval(1.0, 10.0),), explicit_type=True)


class _Orders:
    kind = "row"
    level = "schema"

    def __init__(self, cls, levels):
        self.cls, self.levels = cls, levels
        self.name = f"{cls.__module__}.{cls.__qualname__}"

    def contains(self, v):
        return isinstance(v, self.cls) and isinstance(v.kind, str) \
            and isinstance(v.qty, int) and 1 <= v.qty <= 10

    def explain(self, v):
        return None

    def sample(self, rng):
        return self.cls(kind=rng.choice(["restock", "discount", "export"]),
                        qty=rng.randint(1, 10))

    def members(self, limit):
        return None

    def hazards(self):
        return ()

    def outside(self, rng):
        return self.cls(kind="restock", qty=0)

    def shrink(self, v):
        return ()

    def fields(self):
        return {"kind": self.levels, "qty": _QTY}

    def render(self, ascii_mode=True):
        return f"L[{self.name}]"

    def to_json(self):
        return {"type": "object"}


class _Entry:
    def __init__(self, name, obj):
        self.name, self.value, self._obj = name, f"pkg.mod:{name}", obj

    def load(self):
        return self._obj


@pytest.fixture
def orders(monkeypatch, tmp_path):
    import importlib.util
    path = tmp_path / "categorical_orders.py"
    path.write_text(textwrap.dedent(ORDERS))
    spec = importlib.util.spec_from_file_location("categorical_orders", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["categorical_orders"] = mod
    spec.loader.exec_module(mod)

    def adapt(obj):
        if obj is mod.Order:
            return _Orders(obj, frozenset({"restock", "discount", "export"}))
        if obj is mod.Untyped:
            return _Orders(obj, None)
        if obj is mod.Wide:
            return _Orders(obj, frozenset(f"k{i}" for i in range(20)) | {"a"})
        return None

    monkeypatch.setattr(languages, "_discovered_adaptors", lambda: (_Entry("orders", adapt),))
    languages._loaded_adaptors.cache_clear()
    yield mod
    sys.modules.pop("categorical_orders", None)
    languages._loaded_adaptors.cache_clear()


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.needs_full_proof_budget
def test_levels_the_language_states_split_the_proof(orders):
    p = _one(orders.units, "for o in L[categorical_orders.Order], f(o) <= 120")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.route, p.note)
    assert "split on o.kind" in (p.sketch or ""), p.sketch


@pytest.mark.needs_full_proof_budget
def test_levels_the_claim_states_split_the_proof(orders):
    law = ('for o in L[categorical_orders.Untyped], '
           'o.kind in {"restock", "discount"}, f(o) <= 120')
    p = _one(orders.untyped_units, law)
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.route, p.note)


def test_a_case_that_fails_is_not_proven(orders):
    p = _one(orders.units, "for o in L[categorical_orders.Order], f(o) <= 100")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)


def test_a_field_with_no_stated_levels_has_no_reading(orders):
    p = _one(orders.untyped_units, "for o in L[categorical_orders.Untyped], f(o) <= 120")
    assert p.route != "derive", (p.verdict, p.route)
    assert "o.kind, which is not a number" in (p.note or ""), p.note


def test_a_categorical_read_as_text_is_not_proven_by_derive(orders):
    p = _one(orders.initial_units, "for o in L[categorical_orders.Order], f(o) <= 12")
    assert p.route != "derive", (p.verdict, p.route, p.sketch)


def test_too_many_levels_are_not_split(orders):
    p = _one(orders.wide_units, "for o in L[categorical_orders.Wide], f(o) <= 120")
    assert p.route != "derive", (p.verdict, p.route)
    assert "more than the 16" in (p.note or ""), p.note


def test_identity_against_text_is_never_decided_by_derive(orders):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = _one(orders.is_not_export, "for o in L[categorical_orders.Order], f(o) <= 120")
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch)
    assert p.route != "derive"


def test_identity_of_a_plain_text_parameter_is_never_decided_by_derive(orders):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = _one(orders.identity_of_text,
                 'for s in {"export", "a"}, x in [0, 1], f(s, x) <= 1')
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch)
    assert "identity" in (p.note or "") + (p.sketch or ""), (p.note, p.sketch)


@pytest.mark.needs_full_proof_budget
def test_identity_against_none_is_still_decided(orders):
    p = _one(orders.none_checked, "for o in L[categorical_orders.Order], f(o) <= 120")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.route, p.sketch)
