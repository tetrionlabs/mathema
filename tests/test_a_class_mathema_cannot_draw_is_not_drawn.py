# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter annotated with a class mathema has no way to draw (not a
dataclass, not a runtime type, not bound to a language in the claim) is
never drawn as something outside its declared type: a claim that would
draw it is skipped with "no evaluable inputs" and a reason naming the
class and how to supply one, whether or not the module imports numpy.
A dataclass, a runtime type and a language binding keep drawing as
they did."""
import importlib
import sys
import textwrap
from dataclasses import dataclass

import pytest

import mathema
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")


class Box:
    def __init__(self, shape):
        self.shape = shape


def area(b: Box) -> float:
    return b.shape[0] * b.shape[1]


def scaled(b: Box, k: float) -> float:
    return k * b.shape[0]


@dataclass
class Rect:
    w: float
    h: float


def rect_area(r: Rect) -> float:
    return r.w * r.h


PLAIN = '''
    class Crate:
        def __init__(self, shape):
            self.shape = shape


    def volume(c: Crate) -> float:
        return c.shape[0] * c.shape[1]
'''


@pytest.fixture
def plain_module(tmp_path, monkeypatch):
    (tmp_path / "undrawable_plain.py").write_text(
        "# SPDX-License-Identifier: BUSL-1.1\n# Copyright 2026 Tetrion Ltd\n"
        + textwrap.dedent(PLAIN))
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("undrawable_plain", None)
    return importlib.import_module("undrawable_plain")


def _assert_skipped_for(p, param: str, cls: str):
    assert p.verdict == "skipped", (p.verdict, p.counterexample, p.note)
    assert "no evaluable inputs" in p.note, p.note
    assert cls in p.note and param in p.note, p.note
    assert "runtime type" in p.note and "bind" in p.note, p.note
    assert "AttributeError" not in (p.counterexample or "") + p.note, p


def test_the_annotation_decides_the_class_is_not_a_sequence():
    facts = analyze_source(area)
    assert facts.param_kinds["b"] != "sequence", facts.param_kinds
    assert facts.undrawable == {"b": "Box"}, facts.undrawable


def test_a_claim_over_the_class_is_skipped_with_the_reason():
    (p,) = check_conjectures(area, [claim("f(b) >= 0")])
    _assert_skipped_for(p, "b", "Box")


def test_a_probe_claim_over_the_class_is_skipped_too():
    (p,) = check_conjectures(scaled, [claim(
        "for k in [0, 1], f(b, k) == k * f(b, 1)", route="probe")])
    _assert_skipped_for(p, "b", "Box")


def test_a_chained_claim_over_the_class_is_skipped():
    (p,) = check_conjectures(area, [claim("0 <= f(b) <= 10")])
    _assert_skipped_for(p, "b", "Box")


def test_a_module_without_numpy_skips_alike(plain_module):
    (p,) = check_conjectures(plain_module.volume, [claim("f(c) >= 0")])
    _assert_skipped_for(p, "c", "Crate")


def test_check_draws_no_list_for_the_class():
    record = mathema.check(area, claims=["f(b) >= 0"])
    for p in record.probes:
        assert "b = [" not in (p.counterexample or ""), (p.name, p.counterexample)
        assert p.verdict != "falsified", (p.name, p.counterexample, p.note)
    (row,) = [p for p in record.probes if p.name == "f_b_ge_0"]
    _assert_skipped_for(row, "b", "Box")


def test_a_bare_check_suggests_no_sequence_claims_for_the_class():
    record = mathema.check(area)
    for p in record.probes:
        assert "b = [" not in (p.counterexample or ""), (p.name, p.counterexample)
        assert p.verdict != "falsified", (p.name, p.counterexample, p.note)


def test_a_literal_instance_in_the_claim_is_not_skipped():
    (p,) = check_conjectures(area, [claim("f(Box((2, 3))) == 6",
                                          funcs={"Box": Box})])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note)


def test_a_dataclass_is_still_drawn():
    assert analyze_source(rect_area).undrawable == {}
    (p,) = check_conjectures(rect_area, [claim(
        "f(r) == r.w * r.h", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
