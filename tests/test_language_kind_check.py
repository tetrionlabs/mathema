# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a language's member kind is compared against: a row language
on a parameter the body reads as a mapping is not flagged, a string
language on an `int` parameter is, and an unknown real kind is
compatible with anything."""
import textwrap

from mathema.conjecture import _kind_compatible, check_conjectures, claim
from mathema.languages import Problem, register_language, unregister_language


class _Orders:
    name = "orders"
    kind = "row"
    level = "schema"

    def contains(self, value):
        return isinstance(value, dict) and set(value) == {"qty", "price"}

    def explain(self, value):
        return None if self.contains(value) else [Problem("", "orders", value)]

    def sample(self, rng):
        return {"qty": rng.randint(1, 5), "price": rng.uniform(0.0, 10.0)}

    def members(self, limit):
        return None

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


def _load(tmp_path, body, name="kind_fns"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_table():
    assert _kind_compatible("row", "dict")
    assert _kind_compatible("frame", "sequence")
    assert _kind_compatible("object", "unknown")
    assert _kind_compatible("string", None)
    assert not _kind_compatible("string", "int")
    assert not _kind_compatible("row", "string")


def test_a_row_language_on_a_mapping_parameter_is_not_flagged(tmp_path):
    register_language("orders", _Orders())
    try:
        mod = _load(tmp_path, '''
            def total(order: dict) -> float:
                """Quantity times price."""
                return order["qty"] * order["price"]
        ''')
        (p,) = check_conjectures(mod.total, [claim("for order in L[orders], f(order) >= 0")])
        assert p.verdict == "holds", (p.verdict, p.note)
        assert "whose members" not in p.note
    finally:
        unregister_language("orders")


def test_a_row_language_on_an_int_parameter_is_flagged(tmp_path):
    register_language("orders", _Orders())
    try:
        mod = _load(tmp_path, '''
            def double(n: int) -> int:
                """Twice n."""
                return n + n
        ''')
        (p,) = check_conjectures(mod.double, [claim("for n in L[orders], f(n) == f(n)")])
        assert "whose members are row values" in p.note
    finally:
        unregister_language("orders")
