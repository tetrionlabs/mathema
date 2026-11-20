# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The probe route draws a parameter only in a shape positive evidence
establishes: the claim's domain, a type marker, the annotation, the
default, or how the body uses it. A parameter with no evidence, or with
evidence that disagrees, is not drawn and the claim's probe outcome is
unknown with the reason. A body that only ever does arithmetic with a
parameter establishes a number, so the common unannotated numeric
function keeps drawing, and its record says which evidence it rests on.
A TypeError or AttributeError the drawn value causes at the operation
that applies to it, when the shape rests only on the code (a default or
a use), is a draw defect, never a falsification; a claim that binds the
value itself is still judged on it."""
import importlib.util
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

FNS = '''
    import math


    def same(x):
        return x


    def less(x):
        return x - 1


    def wave(x):
        return math.sin(x)


    def through(t):
        return wave(t)


    def shout(s):
        return s.upper()


    def greet(name):
        return "hi " + name


    def first(x: float):
        return x[0]


    def scale(v):
        return v * 2 + v.offset


    def head(xs=[1.0, 2.0]):
        return xs[0] * 0 + 1


    def plus(x: float):
        return x + 1
'''


@pytest.fixture
def mod(tmp_path):
    p = tmp_path / "shape_evidence_fns.py"
    p.write_text(textwrap.dedent(FNS))
    spec = importlib.util.spec_from_file_location("shape_evidence_fns", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules["shape_evidence_fns"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("shape_evidence_fns", None)


def _row(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    return p


def test_a_parameter_nothing_establishes_is_not_drawn(mod):
    p = _row(mod.same, "f(x) == x")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta.get("mathema.probe_gap") == "shape-not-established"
    assert "shape of parameter x is not established" in p.note
    assert "shape_evidence_fns.py:5" in p.note
    assert '"def same(x):"' in p.note
    assert "bind x in the claim" in p.note and "annotate it" in p.note
    assert p.n == 0 and p.counterexample is None


def test_binding_the_parameter_in_the_claim_draws_it(mod):
    p = _row(mod.same, "for x in [0, 1], f(x) == x")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "mathema.probe_gap" not in (p.meta or {})


def test_arithmetic_in_the_body_establishes_a_number_and_the_record_says_so(mod):
    p = _row(mod.less, "f(x) <= x")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    shapes = p.meta["mathema.drawn_shapes"]
    assert shapes["x"]["source"] == "body use"
    assert shapes["x"]["shape"] == "number"


@pytest.mark.parametrize("name, var", [("wave", "x"), ("through", "t")])
def test_a_numeric_function_or_a_callee_establishes_a_number(mod, name, var):
    p = _row(getattr(mod, name), f"f({var}) <= 1")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.drawn_shapes"][var]["shape"] == "number"


def test_a_stated_shape_is_not_restated_on_the_record(mod):
    p = _row(mod.plus, "f(x) >= x")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert "mathema.drawn_shapes" not in (p.meta or {})


@pytest.mark.usefixtures("without_language_package")
@pytest.mark.parametrize("name, var", [("shout", "s"), ("greet", "name")])
def test_a_body_that_uses_text_is_never_given_a_number(mod, name, var):
    p = _row(getattr(mod, name), f"f({var}) == f({var})")
    assert p.verdict == "skipped", (p.verdict, p.note, p.counterexample)
    assert p.meta.get("mathema.probe_gap") == "string-domain-missing"
    assert "raised" not in (p.counterexample or "")


def test_an_annotation_the_body_contradicts_is_not_drawn(mod):
    p = _row(mod.first, "f(x) == f(x)")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta.get("mathema.probe_gap") == "shape-not-established"
    assert "annotated float (a number)" in p.note
    assert "indexes" in p.note and "(a sequence)" in p.note


def test_a_default_establishes_its_own_shape(mod):
    p = _row(mod.head, "f(xs) == 1")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.drawn_shapes"]["xs"]["source"] == "default"


def test_a_wrong_shape_raise_on_a_guessed_number_is_a_draw_defect(mod):
    p = _row(mod.scale, "f(v) >= 0")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.counterexample is None
    defect = p.meta["mathema.draw_defect"]
    assert defect["param"] == "v" and defect["raised"] == "AttributeError"
    assert "the draw for v had the wrong shape" in p.note
    assert "shape_evidence_fns.py:34" in p.note
    assert '"return v * 2 + v.offset"' in p.note


def test_a_raises_claim_passing_only_on_a_wrong_shape_is_a_draw_defect(mod):
    p = _row(mod.scale, "raises(f(v), AttributeError)")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.draw_defect"]["param"] == "v"


def test_a_claim_that_binds_the_value_is_judged_on_it(mod):
    falsified = _row(mod.scale, "for v in [0, 1], f(v) >= 0")
    assert falsified.verdict == "falsified", (falsified.verdict, falsified.note)
    assert "raised AttributeError" in falsified.counterexample
    held = _row(mod.scale, "for v in [0, 1], raises(f(v), AttributeError)")
    assert held.verdict == "holds", (held.verdict, held.note)
