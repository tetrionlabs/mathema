# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The row lift reads any row language's fields, not only a
dataclass's: a literal-key subscript (`line["qty"]`, a TypedDict or a
JSON Schema row) and an attribute read on a row of any class (a
pydantic, SQLAlchemy or Django model) each lift as one symbol bounded
by the language's `fields()`, and a text field read only through
`len(...)` as a bounded whole number, exactly as the dataclass path
does. Before, a subscript read reached the lift with no bound, so
derive "disproved" a true sign claim at a record no valid member is,
and reported it as an uncorroborated disproof; an attribute read on a
non-dataclass row did not lift at all. A row parameter the body reads
no field of is not lifted, and an object parameter outside a language
claim is not widened."""
import sys
import textwrap

import pytest

import mathema.languages as languages
from mathema.conjecture import check_conjectures, claim
from mathema.domain import Domain, Interval, LanguageRef
from mathema.languages import Problem

ROWS = '''
    from typing import TypedDict


    class LineDict(TypedDict):
        sku: str
        qty: int
        price: float


    class LineModel:
        """A row class that is not a dataclass."""

        def __init__(self, sku, qty, price):
            self.sku, self.qty, self.price = sku, qty, price

        def __repr__(self):
            return f"LineModel({self.sku!r}, {self.qty!r}, {self.price!r})"


    class Plain:
        def __init__(self, x):
            self.x = x


    def dict_total(line: LineDict) -> float:
        """Quantity times price."""
        return line["qty"] * line["price"]


    def dict_width(line: LineDict) -> int:
        """The columns the sku takes, with a space either side."""
        return len(line["sku"]) + 2


    def dict_shout(line: LineDict) -> float:
        """The price, doubled for an upper-case sku."""
        return line["price"] * (2.0 if line["sku"].isupper() else 1.0)


    def model_total(line: LineModel) -> float:
        """Quantity times price."""
        return line.qty * line.price


    def model_width(line: LineModel) -> int:
        """The columns the sku takes, with a space either side."""
        return len(line.sku) + 2


    def described(line: LineModel) -> float:
        """The length of the row's text form, as a number."""
        return float(len(str(line)))


    def square(o: Plain) -> float:
        """The square of the field."""
        return o.x * o.x
'''

_FIELDS = {"sku": LanguageRef("unicode", (("len", Interval(0.0, 8.0)),)),
           "qty": Domain(base_type="Z", pieces=(Interval(1.0, 10.0),), explicit_type=True),
           "price": Interval(0.0, float("inf"))}


class _Rows:
    """A row language over dicts or instances, with the one-deep field
    bounds the package's adaptors state."""
    kind = "row"
    level = "schema"

    def __init__(self, cls, make):
        self.cls, self.make = cls, make
        self.name = f"{cls.__module__}.{cls.__qualname__}"

    def _values(self, v):
        return v if isinstance(v, dict) else getattr(v, "__dict__", {})

    def contains(self, v):
        d = self._values(v)
        return (set(d) == {"sku", "qty", "price"} and isinstance(d["qty"], int)
                and 1 <= d["qty"] <= 10 and isinstance(d["price"], float) and d["price"] >= 0
                and isinstance(d["sku"], str) and len(d["sku"]) <= 8)

    def explain(self, v):
        return None if self.contains(v) else [Problem("", "Line", v)]

    def sample(self, rng):
        return self.make(sku="".join(rng.choice("abAB") for _ in range(rng.randint(0, 8))),
                         qty=rng.randint(1, 10), price=rng.uniform(0.0, 100.0))

    def members(self, limit):
        return None

    def hazards(self):
        return ()

    def outside(self, rng):
        return self.make(sku="", qty=0, price=-1.0)

    def shrink(self, v):
        return ()

    def fields(self):
        return dict(_FIELDS)

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
def rows(monkeypatch, tmp_path):
    import importlib.util
    path = tmp_path / "lift_more_rows.py"
    path.write_text(textwrap.dedent(ROWS))
    spec = importlib.util.spec_from_file_location("lift_more_rows", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lift_more_rows"] = mod
    spec.loader.exec_module(mod)

    def adapt(obj):
        if obj is mod.LineDict:
            return _Rows(obj, lambda **kw: dict(kw))
        if obj is mod.LineModel:
            return _Rows(obj, lambda **kw: mod.LineModel(**kw))
        return None

    monkeypatch.setattr(languages, "_discovered_adaptors", lambda: (_Entry("rows", adapt),))
    languages._loaded_adaptors.cache_clear()
    yield mod
    sys.modules.pop("lift_more_rows", None)
    languages._loaded_adaptors.cache_clear()


def _one(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, shape", [("dict_total", "LineDict"), ("model_total", "LineModel")])
def test_a_field_read_lifts_through_the_language_bounds(rows, fn, shape):
    p = _one(getattr(rows, fn), f"for line in L[lift_more_rows.{shape}], f(line) >= 0", "derive")
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, shape", [("dict_width", "LineDict"), ("model_width", "LineModel")])
def test_a_text_field_read_through_len_is_a_bounded_whole_number(rows, fn, shape):
    law = f"for line in L[lift_more_rows.{shape}], f(line) <= 10"
    assert _one(getattr(rows, fn), law, "derive").verdict == "proven"


@pytest.mark.needs_full_proof_budget
def test_no_uncorroborated_disproof_over_dict_rows(rows):
    p = _one(rows.dict_total, "for line in L[lift_more_rows.LineDict], f(line) >= 0")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "UNCORROBORATED" not in (p.note or "")
    q = _one(rows.dict_width, "for line in L[lift_more_rows.LineDict], f(line) <= 9")
    assert q.verdict == "falsified", (q.verdict, q.note)
    assert "UNCORROBORATED" not in (q.note or "")


def test_a_text_field_read_as_text_declines_naming_the_field(rows):
    p = _one(rows.dict_shout, "for line in L[lift_more_rows.LineDict], f(line) >= 0", "derive")
    assert p.verdict != "proven"
    assert "line.sku" in f"{p.note} {p.sketch}"


def test_a_row_the_body_reads_no_field_of_is_not_lifted(rows):
    p = _one(rows.described, "for line in L[lift_more_rows.LineModel], f(line) >= 0", "derive")
    assert p.verdict not in ("proven", "falsified"), (p.verdict, p.note)


def test_an_object_parameter_outside_a_language_claim_is_not_widened(rows):
    p = _one(rows.square, "f(o) >= 0", "derive")
    assert p.verdict != "proven", (p.verdict, p.note)
