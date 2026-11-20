# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The probe route draws a parameter only in a shape positive evidence
establishes: the claim's domain, a type marker, the annotation, the
default, or how the body uses it. A parameter with no evidence, or with
evidence that disagrees and nothing settles, is not drawn and the
claim's probe outcome is unknown with the reason; an annotation or a
number use the body contradicts is drawn, and the raise stands. A body that only ever does arithmetic with a
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
    import dataclasses
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


    def running(xs, y0):
        total = y0
        for v in xs:
            if v > 0:
                total = total + v
        return total


    def replaced(y0):
        t = y0
        t = [1.0]
        return t[0] + 1


    def unused(x, y):
        return x - 1


    @dataclasses.dataclass(order=True)
    class Pair:
        a: float
        b: float


    class Bigger(Pair):
        def __lt__(self, other):
            return self.a < other.a


    @dataclasses.dataclass
    class Plain:
        a: float

        def __lt__(self, other):
            return self.a < other.a


    class Bare:
        def __init__(self, a: float = 0.0):
            self.a = a

        def __le__(self, other):
            return self.a <= other.a


    _CACHE = {}


    def keyed(key=(1, 2)):
        d = {key: 1}
        return len(d)


    def cached(key=(1, 2)):
        _CACHE[key] = 1
        return 1


    def keyed_by(key: tuple):
        d = {key: 1}
        return len(d)


    def nested(y0):
        t = y0
        def first(t):
            return t[0]
        return t + first([1.0])


    def picked(y0):
        t = y0
        pick = lambda t: t[0]
        return t + pick([1.0])


    def comprehended(y0):
        t = y0
        firsts = [t[0] for t in [[1.0], [2.0]]]
        return t + firsts[0]


    def late(y0):
        t = y0
        get = lambda: t[0]
        t = [1.0]
        return get() + y0


    def matched(y0):
        t = y0
        match [[1.0]]:
            case [t]:
                pass
        return t[0] + y0


    def defined(y0):
        t = y0
        def t():
            return [1.0]
        return t()[0] + y0


    def none_default_bug(x, scale=None):
        return x * scale


    def typo(x):
        if x > 100:
            return x.offest
        return x + 1


    import functools

    inc = lambda x: x + 1


    def add(x, y):
        return x + y


    add_one = functools.partial(add, y=1.0)


    def label(n):
        if n > 0:
            return "count: " + n
        return ""


    def either(x):
        return x == "a" or x + 1 > 3


    def indexed(x=1.0):
        return x[0]


    def text_or_mapping(x):
        return x.upper(), x.keys()


    def repeat(x):
        return x * "ab"


    def float_repeat_kind(x: float):
        if x != x:
            return x * "ab"
        return 1 if isinstance(x, float) else 0


    def float_repeat(x: float):
        return x * "ab"


    def copied_in_a_loop(y0):
        t = y0
        acc = 0.0
        for _ in range(2):
            acc = acc + t
            t = "x"
        return acc


    def turned_to_text(x):
        acc = 0.0
        for _ in range(2):
            acc = acc + x
            acc = str(acc)
        return acc


    class _Ctx:
        def __enter__(self):
            return "ctx"

        def __exit__(self, *a):
            return False


    def rebound_in_a_branch(y0, flag: bool):
        t = y0
        if flag:
            t = "s"
        return t + 1.0


    def rebound_by_with(y0):
        t = y0
        with _Ctx() as t:
            pass
        return t + 1.0


    def rebound_by_walrus(y0):
        t = y0
        if (t := "w"):
            pass
        return t + 1.0


    def rebound_after_del(y0):
        t = y0
        del t
        t = "d"
        return t + 1.0


    def rebound_by_star(y0):
        t = y0
        *t, = ["a"]
        return t + 1.0


    def rebound_by_augmenting(y0):
        t = y0
        t += 1.0
        return t.upper()


    def unpacked(y0):
        a, t = y0, 1
        return a + 1.0
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
    assert "shape_evidence_fns.py:6" in p.note
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


def test_an_annotation_the_body_contradicts_is_drawn_and_the_raise_stands(mod):
    p = _row(mod.first, "f(x) == f(x)")
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)
    assert "raised TypeError" in p.counterexample
    assert "mathema.probe_gap" not in (p.meta or {})


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
    assert "shape_evidence_fns.py:35" in p.note
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


def test_a_plain_local_copy_carries_the_parameters_uses(mod):
    p = _row(mod.running, "abs(f(xs, y0) - y0) <= abs(y0) + 1e9")
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.drawn_shapes"]["y0"]["shape"] == "number"


def test_a_copy_rebound_before_its_use_carries_nothing(mod):
    p = _row(mod.replaced, "f(y0) == 2")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    shape = p.meta["mathema.drawn_shapes"]["y0"]
    assert shape["source"] == "not read by the body"
    assert shape["detail"] == ("the body reads it only through a local it may "
                               "bind to another value first")


def test_a_parameter_the_body_never_reads_is_drawn_and_said_so(mod):
    p = _row(mod.unused, "f(x, y) <= x")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.drawn_shapes"]["y"]["source"] == "not read by the body"


def test_a_function_without_source_says_so():
    ns: dict = {}
    exec("def hidden(x):\n    return x\n", ns)
    p = _row(ns["hidden"], "f(x) == x")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "<unknown>" not in p.note
    assert ("shape of parameter x is not established (the source of hidden "
            "is not available)") in p.note


def test_a_generated_dataclass_ordering_draws_an_instance(mod):
    p = _row(mod.Pair.__lt__, "f(self, other) == f(self, other)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    shape = p.meta["mathema.drawn_shapes"]["other"]
    assert shape["source"] == "generated dataclass method"
    assert shape["detail"] == "an instance of Pair"


@pytest.mark.parametrize("cls, name", [("Bigger", "__lt__"), ("Plain", "__lt__"),
                                       ("Bare", "__le__")])
def test_an_ordering_method_not_generated_leaves_other_unknown(mod, cls, name):
    p = _row(getattr(getattr(mod, cls), name), "f(self, other) == f(self, other)")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta.get("mathema.probe_gap") == "shape-not-established"
    assert "other" in p.meta["mathema.shape"]


@pytest.mark.parametrize("name", ["keyed", "cached", "keyed_by"])
def test_a_tuple_default_or_annotation_is_drawn_as_a_tuple(mod, name):
    p = _row(getattr(mod, name), "f(key) == 1")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


@pytest.mark.parametrize("name", ["nested", "picked", "comprehended", "late",
                                  "matched", "defined"])
def test_a_copy_is_read_through_only_in_its_own_scope_and_binding(mod, name):
    p = _row(getattr(mod, name), "f(y0) == y0 + 1.0")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


@pytest.mark.parametrize("name, text", [("none_default_bug", "f(x) >= 0"),
                                        ("typo", "f(x) >= x")])
def test_a_raise_the_drawn_shape_does_not_explain_is_a_finding(mod, name, text):
    p = _row(getattr(mod, name), text)
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)
    assert "mathema.draw_defect" not in (p.meta or {})


@pytest.mark.parametrize("name", ["inc", "add_one"])
def test_a_lambda_or_a_partial_is_read_from_its_source(mod, name):
    p = _row(getattr(mod, name), "f(x) >= x")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.drawn_shapes"]["x"]["source"] == "body use"


def test_a_number_use_the_body_contradicts_is_drawn_and_the_raise_stands(mod):
    p = _row(mod.label, "f(n) == f(n)")
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)
    assert "mathema.draw_defect" not in (p.meta or {})


@pytest.mark.parametrize("name", ["either", "indexed"])
def test_a_settled_disagreement_draws_the_shape_that_settles_it(mod, name):
    p = _row(getattr(mod, name), "f(x) == f(x)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_a_disagreement_in_the_body_names_the_uses(mod):
    p = _row(mod.text_or_mapping, "f(x) == f(x)")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "its annotation" not in p.note
    assert "make its use in the body and its use `x.upper()` agree" in p.note


def test_a_partial_without_source_is_named_by_its_function():
    import functools
    ns: dict = {}
    exec("def hidden(x, y):\n    return x\n", ns)
    p = _row(functools.partial(ns["hidden"], y=1), "f(x) == x")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "(the source of hidden is not available)" in p.note


def test_a_count_of_text_repeats_is_drawn_as_an_integer(mod):
    p = _row(mod.repeat, "f(x) == f(x)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.drawn_shapes"]["x"]["shape"] == "number"


def test_a_count_of_repeats_does_not_change_a_float_annotation(mod):
    p = _row(mod.float_repeat_kind, "f(x) == 1")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    p = _row(mod.float_repeat, "f(x) == f(x)")
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)


def test_the_family_rows_of_a_float_annotation_draw_floats(mod, monkeypatch):
    import mathema
    monkeypatch.setenv("MATHEMA_BUILTIN_CHECKS", "on")
    rows = {p.name: p.verdict for p in mathema.check(mod.float_repeat_kind).probes}
    assert rows.get("odd") == "falsified", rows
    assert rows.get("idempotent") == "falsified", rows


@pytest.mark.parametrize("name, var", [("copied_in_a_loop", "y0"),
                                       ("turned_to_text", "x")])
def test_a_raise_on_a_value_that_is_not_the_drawn_one_is_a_finding(mod, name, var):
    p = _row(getattr(mod, name), f"f({var}) == f({var})")
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)
    assert "mathema.draw_defect" not in (p.meta or {})


@pytest.mark.parametrize("name, text, verdict", [
    ("rebound_in_a_branch", "f(y0, flag) == f(y0, flag)", "falsified"),
    ("rebound_by_with", "f(y0) == f(y0)", "falsified"),
    ("rebound_by_walrus", "f(y0) == f(y0)", "falsified"),
    ("rebound_after_del", "f(y0) == f(y0)", "falsified"),
    ("rebound_by_star", "f(y0) == f(y0)", "falsified"),
    ("rebound_by_augmenting", "f(y0) == f(y0)", "falsified"),
    ("unpacked", "f(y0) == f(y0)", "holds"),
])
def test_a_rebound_copy_keeps_the_finding_and_an_unpacked_copy_is_read(
        mod, name, text, verdict):
    p = _row(getattr(mod, name), text)
    assert p.verdict == verdict, (p.verdict, p.note, p.counterexample)
