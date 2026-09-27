# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A field path in a binding and in the lift reaches any depth, through
fields and indices: `o.address.zip`, `o.lines[0].sku`, and
`o.lines[*].qty` for every element. A path binding narrows the members
the probe draws (every value at the path lies in the bound; a path
through a missing field reads the missing value); the lift reads a
numeric leaf at any depth with the bound the language's `fields()`
states, a nested mapping for a nested record and `"[*]"` for the
elements of a list, and a claim's path binding overrides it."""
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.domain import Domain, Interval, LanguageRef, split_quantifier
from mathema.languages import Problem, StringLanguage, register_language, unregister_language
from mathema.spec import render_claim_text

ROWS = '''
    from dataclasses import dataclass, field
    from typing import Optional


    @dataclass
    class Address:
        zip: str


    @dataclass
    class Line:
        sku: str
        qty: int


    @dataclass
    class Order:
        address: Optional[Address]
        lines: list = field(default_factory=list)


    def first_qty(o: Order) -> int:
        """The first line's quantity."""
        return o.lines[0].qty


    def zip_width(o: Order) -> int:
        """The columns the zip code takes."""
        return len(o.address.zip)


    def largest_qty(o: Order) -> int:
        """The largest quantity on the order."""
        return max((line.qty for line in o.lines), default=0)


    def has_zip(o: Order) -> bool:
        """Whether the order has an address."""
        return o.address is not None
'''

DIGITS = StringLanguage("digits", char_ok=str.isdigit, pool="0123456789")


class _Orders:
    kind = "row"
    level = "schema"

    def __init__(self, mod):
        self.mod = mod
        self.name = "deep_rows.Order"

    def _ok(self, o):
        m = self.mod
        return (isinstance(o, m.Order) and (o.address is None or (
            isinstance(o.address, m.Address) and o.address.zip.isdigit()
            and len(o.address.zip) <= 5))
            and len(o.lines) >= 1
            and all(isinstance(li, m.Line) and 1 <= li.qty <= 10 and len(li.sku) <= 8
                    for li in o.lines))

    def contains(self, v):
        return self._ok(v)

    def explain(self, v):
        return None if self._ok(v) else [Problem("", "Order", v)]

    def sample(self, rng):
        m = self.mod
        address = None if rng.random() < 0.2 else m.Address(
            "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 5))))
        lines = [m.Line("A" * rng.randint(0, 8), rng.randint(1, 10))
                 for _ in range(rng.randint(1, 4))]
        return m.Order(address, lines)

    def members(self, limit):
        return None

    def hazards(self):
        return ()

    def outside(self, rng):
        return self.mod.Order(None, [])

    def shrink(self, v):
        return ()

    def fields(self):
        qty = Domain(base_type="Z", pieces=(Interval(1.0, 10.0),), explicit_type=True)
        return {"address": {"zip": LanguageRef("digits", (("len", Interval(0.0, 5.0)),))},
                "lines": {"[*]": {"sku": LanguageRef("unicode", (("len", Interval(0.0, 8.0)),)),
                                  "qty": qty}}}

    def render(self, ascii_mode=True):
        return f"L[{self.name}]"

    def to_json(self):
        return {"type": "object"}


@pytest.fixture
def rows(tmp_path):
    import importlib.util
    path = tmp_path / "deep_rows.py"
    path.write_text(textwrap.dedent(ROWS))
    spec = importlib.util.spec_from_file_location("deep_rows", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["deep_rows"] = mod
    spec.loader.exec_module(mod)
    register_language("deep_rows.Order", _Orders(mod))
    register_language("digits", DIGITS)
    yield mod
    unregister_language("deep_rows.Order")
    unregister_language("digits")
    sys.modules.pop("deep_rows", None)


@pytest.mark.parametrize("path, bound", [
    ("o.address.zip", "L[digits, len <= 5]"),
    ("o.lines[0].sku", "L[digits]"),
    ("o.lines[*].qty", "[1, 3]"),
])
def test_a_path_binding_parses_and_renders_back(path, bound):
    text = f"for o in L[deep_rows.Order], {path} in {bound}, f(o) >= 0"
    cj = claim(text)
    assert path in cj.domain
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        assert path in shown, shown
        assert render_claim_text(claim(shown), unicode=unicode) == shown


def test_a_malformed_path_is_refused():
    from mathema.domain import InvalidDomain
    with pytest.raises(InvalidDomain):
        split_quantifier("for o in L[x], o.lines[].qty in [1, 3], f(o) >= 0")


def test_a_path_binding_narrows_the_probe(rows):
    (p,) = check_conjectures(rows.largest_qty, [claim(
        "for o in L[deep_rows.Order], o.lines[*].qty in [1, 3], f(o) <= 3", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    (q,) = check_conjectures(rows.largest_qty, [claim(
        "for o in L[deep_rows.Order], f(o) <= 3", route="probe")])
    assert q.verdict == "falsified"


def test_a_path_through_a_missing_field_reads_the_missing_value(rows):
    (p,) = check_conjectures(rows.has_zip, [claim(
        "for o in L[deep_rows.Order], o.address.zip in L[digits] \\ {missing}, f(o) == True",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    (q,) = check_conjectures(rows.has_zip, [claim(
        "for o in L[deep_rows.Order], f(o) == True", route="probe")])
    assert q.verdict == "falsified"


@pytest.mark.needs_full_proof_budget
def test_the_lift_reads_a_leaf_at_any_depth(rows):
    (p,) = check_conjectures(rows.first_qty, [claim(
        "for o in L[deep_rows.Order], f(o) >= 1", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
    (q,) = check_conjectures(rows.zip_width, [claim(
        "for o in L[deep_rows.Order], f(o) <= 5", route="derive")])
    assert q.verdict == "proven", (q.verdict, q.note, q.sketch)


@pytest.mark.needs_full_proof_budget
def test_a_path_binding_overrides_the_language_s_bound_in_the_lift(rows):
    (p,) = check_conjectures(rows.first_qty, [claim(
        "for o in L[deep_rows.Order], o.lines[*].qty in [1, 3], f(o) <= 3", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
