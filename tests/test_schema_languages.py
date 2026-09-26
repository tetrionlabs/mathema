# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A structured language (a row language whose members are mappings):
a parameter the body reads as a mapping is drawn from the language, not
from the generic mapping synthesiser; a mapping member is checked
against exclusions without hashing; an unhashable member never crashes
enumeration."""
import textwrap

from mathema.conjecture import check_conjectures, claim
from mathema.domain import domain_contains, finite_members, parse_binding
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
    spec.loader.exec_module(mod)
    return mod


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
