# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A structured language (a row language whose members are mappings):
a parameter the body reads as a mapping is drawn from the language, not
from the generic mapping synthesiser; a mapping member is checked
against exclusions without hashing; an unhashable member never crashes
enumeration."""
import textwrap

import sys

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.domain import (Domain, Interval, InvalidDomain, domain_contains,
                            finite_members, parse_binding)
from mathema.languages import Problem, register_language, unregister_language


class _Orders:
    name = "orders"
    kind = "row"
    level = "finite"
    ROWS = ({"qty": 1, "price": 2.0}, {"qty": 3, "price": 0.5})

    def __init__(self):
        self.drawn = 0

    def contains(self, value):
        return value in self.ROWS

    def explain(self, value):
        return None if self.contains(value) else [Problem("", "orders", value)]

    def sample(self, rng):
        self.drawn += 1
        return dict(rng.choice(self.ROWS))

    def members(self, limit):
        return self.ROWS if len(self.ROWS) <= limit else None

    def hazards(self):
        return ()

    def outside(self, rng):
        return {"qty": 1}

    def shrink(self, value):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return "L[orders]"

    def to_json(self):
        return {"type": "object"}


def _load(tmp_path, body, name="schema_fns"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _RowsOf:
    """A row language over a dataclass, one-deep numeric field bounds."""
    kind = "row"
    level = "schema"

    def __init__(self, cls):
        self.cls = cls
        self.name = cls.__name__
        self.bounds = {"qty": Domain(base_type="Z", pieces=(Interval(1.0, 10.0),),
                                     explicit_type=True),
                       "price": Interval(0.0, 1e6)}

    def contains(self, value):
        return isinstance(value, self.cls) and 1 <= value.qty <= 10 \
            and 0.0 <= value.price <= 1e6

    def explain(self, value):
        return None if self.contains(value) else [Problem("", self.name, value)]

    def sample(self, rng):
        return self.cls(qty=rng.randint(1, 10), price=rng.uniform(0.0, 100.0))

    def members(self, limit):
        return None

    def hazards(self):
        return ()

    def outside(self, rng):
        return self.cls(qty=0, price=-1.0)

    def shrink(self, value):
        return ()

    def fields(self):
        return dict(self.bounds)

    def render(self, ascii_mode=True):
        return f"L[{self.name}]"

    def to_json(self):
        return {"type": "object", "properties": {"qty": {"type": "integer"},
                                                 "price": {"type": "number"}}}


class _Entry:
    def __init__(self, name, value, obj):
        self.name, self.value, self._obj = name, value, obj

    def load(self):
        return self._obj


@pytest.fixture
def dataclass_adaptor(monkeypatch):
    import dataclasses

    def adapt(obj):
        return _RowsOf(obj) if isinstance(obj, type) and dataclasses.is_dataclass(obj) else None

    monkeypatch.setattr(languages, "_discovered_adaptors",
                        lambda: (_Entry("rows", "pkg.mod:adapt", adapt),))
    languages._loaded_adaptors.cache_clear()
    yield
    languages._loaded_adaptors.cache_clear()


ORDER_MODULE = '''
    from dataclasses import dataclass


    @dataclass
    class Order:
        qty: int
        price: float


    def total(o: Order) -> float:
        """Quantity times price."""
        return o.qty * o.price
'''


@pytest.mark.needs_full_proof_budget
def test_a_schema_language_field_lift_proves_a_sign_fact(tmp_path, dataclass_adaptor):
    mod = _load(tmp_path, ORDER_MODULE, name="schema_orders")
    (p,) = check_conjectures(mod.total, [claim("for o in L[schema_orders.Order], f(o) >= 0",
                                               route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
    assert p.meta["mathema.language"]["o"][0]["source"] == "adaptor rows"


def test_a_schema_language_disproof_is_an_executed_instance(tmp_path, dataclass_adaptor):
    mod = _load(tmp_path, ORDER_MODULE, name="schema_orders2")
    (p,) = check_conjectures(mod.total, [claim("for o in L[schema_orders2.Order], f(o) <= 50")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "Order(" in str(p.counterexample) or "qty" in str(p.counterexample)


def test_a_claim_level_field_binding_narrows_the_language(tmp_path, dataclass_adaptor):
    mod = _load(tmp_path, ORDER_MODULE, name="schema_orders3")
    (p,) = check_conjectures(mod.total, [claim(
        "for o in L[schema_orders3.Order], o.price in [0, 1], f(o) <= 10")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note, p.counterexample)


def test_a_deeper_path_is_refused_by_name():
    from mathema.conjecture import InvalidConjecture
    with pytest.raises(InvalidConjecture, match="one level deep"):
        claim("for o in L[orders], o.qty.n in [0, 1], f(o) >= 0")
    with pytest.raises(InvalidDomain, match="o.qty.n"):
        from mathema.domain import split_quantifier
        split_quantifier("for o in L[orders], o.qty.n in [0, 1], f(o) >= 0")


def test_a_mapping_parameter_bound_to_a_language_is_sampled_from_the_language(tmp_path):
    orders = _Orders()
    register_language("orders", orders)
    try:
        mod = _load(tmp_path, '''
            def total(order: dict) -> float:
                """Quantity times price."""
                return order["qty"] * order["price"]
        ''')
        (p,) = check_conjectures(mod.total,
                                 [claim("for order in L[orders], f(order) >= 0",
                                        route="probe")])
        assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
        assert orders.drawn >= p.n > 0
    finally:
        unregister_language("orders")


def test_a_mapping_member_is_checked_against_exclusions_without_hashing():
    register_language("orders", _Orders())
    try:
        bound = parse_binding('order in L[orders] \\ {"x"}')[1]
        assert domain_contains({"qty": 1, "price": 2.0}, bound)
        assert not domain_contains({"qty": 9, "price": 9.0}, bound)
        assert not domain_contains([1, 2], bound)
    finally:
        unregister_language("orders")


def test_an_unhashable_member_never_crashes_enumeration():
    register_language("orders", _Orders())
    try:
        bound = parse_binding("order in L[orders]")[1]
        members = finite_members(bound, 10)
        assert members is not None and len(members) == 2
        assert all(isinstance(m, dict) for m in members)
    finally:
        unregister_language("orders")
