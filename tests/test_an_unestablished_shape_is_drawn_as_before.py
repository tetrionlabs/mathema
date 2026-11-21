# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter whose shape nothing establishes (no annotation, default or
use the reading follows says what kind of value it takes) is drawn over
the base kinds, one companion run each: None, bool, int, float,
complex, and str, bytes, list, tuple, dict and set empty and non-empty.
The claim holds for the kinds it holds on, and the row names them; a
kind where the claim fails, or where the draw does not apply (a
TypeError or AttributeError at an operation on the drawn value), is
left out and kept in the row's meta. With no kind left the claim is
falsified at the first failing kind's witness, or unknown when no kind
applied. A parameter whose shape is established still falsifies on one
failure."""
import importlib.util
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

FNS = '''
    import functools


    def acc_keeps(y0):
        total = y0
        for v in (1.0, 2.0):
            total = total + v
        return total


    def copy_then_overwrite(y0):
        t = y0
        t = 2.0
        return t + 1.0


    def acc_wrap(y0):
        t = y0
        out = 0.0
        for k in range(2):
            if k > 0:
                out = out + t[0]
            t = [t]
        return out


    def running(xs, y0):
        total = y0
        for v in xs:
            if v > 0:
                total = total + v
        return total


    def mean_req_noev(xs: list, k):
        if k:
            return sum(xs) / len(xs)
        return 0.0


    def kwonly(xs: list, *, k=None):
        if k is None:
            return 0.0
        return sum(xs) / len(xs)


    same2 = (lambda x: x, lambda x: x)


    def same(x):
        return x


    def aug_num(y0):
        t = y0
        t += 1.0
        return t


    def match_seq(x):
        match x:
            case [a, *_]:
                return a
            case _:
                return 0.0


    def nest_capture_num(y0):
        t = y0
        def g():
            return t + 1.0
        return g()


    def deco_plain(fn):
        def w(x):
            return fn(x)
        return w


    @deco_plain
    def dec2_num(x):
        return x * 3.0


    def loop_bind_while(y0):
        t = y0
        n = 0
        while n < 2:
            v = t + 1.0
            t = v
            n += 1
        return t


    def dbl_bind(y0):
        t, t = [1.0], y0
        return t + 1.0


    lam_nest = lambda x: (lambda y: y[0])([x]) + 1.0
    lam_shadow = lambda x: (lambda x: x[0])(x) * 2.0


    def is_empty(xs):
        return not xs


    def first_or_self(xs):
        return xs if xs else 0.0


    def has_any(xs):
        return bool(xs)


    def last_or_zero(xs):
        t = xs
        return t if t else 0


    def tri(x):
        return sum(range(x))


    def lit_index(x):
        return (1.0, 2.0, 3.0)[x] * 2.0


    def unequal(x):
        return x


    def annotated(x: float):
        return x
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("kinds") / "base_kind_fns.py"
    path.write_text(textwrap.dedent(FNS))
    spec = importlib.util.spec_from_file_location("base_kind_fns", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["base_kind_fns"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("base_kind_fns", None)


def _row(fn, text, route="probe"):
    made = claim(text) if route is None else claim(text, route=route)
    (p,) = check_conjectures(fn, [made])
    return p


# develop's verdict for the claim develop was run with
@pytest.mark.parametrize("name, text, verdict, route", [
    ("acc_keeps", "f(y0) == y0 + 3.0", "holds", "probe"),
    ("copy_then_overwrite", "f(y0) == 3.0", "holds", "probe"),
    ("acc_wrap", "f(y0) == y0", "holds", "probe"),
    ("running", "abs(f(xs, y0) - y0) <= abs(y0) + 1e9", "falsified", "probe"),
    ("mean_req_noev", "f(xs, k) == f(xs, k)", "holds", "probe"),
    ("kwonly", "f(xs, k=k) == f(xs, k=k)", "holds", "probe"),
    ("same2[0]", "f(x) == x", "holds", "probe"),
    ("same", "f(x) == x", "holds", "probe"),
    ("aug_num", "f(y0) == f(y0)", "holds", None),
    ("aug_num", "f(y0) == y0 + 1.0", "holds", None),
    ("match_seq", "f(x) == f(x)", "holds", None),
    ("nest_capture_num", "f(y0) == f(y0)", "holds", None),
    ("nest_capture_num", "f(y0) == y0 + 1.0", "holds", None),
    ("dec2_num", "f(x) == f(x)", "holds", None),
    ("loop_bind_while", "f(y0) == f(y0)", "holds", None),
    ("loop_bind_while", "f(y0) == y0 + 2.0", "holds", None),
    ("dbl_bind", "f(y0) == f(y0)", "holds", None),
    ("dbl_bind", "f(y0) == y0 + 1.0", "holds", None),
    ("lam_nest", "f(x) == f(x)", "holds", None),
    ("lam_nest", "f(x) == x + 1.0", "holds", None),
    ("lam_shadow", "f(x) == f(x)", "holds", None),
    ("lam_shadow", "f(x) == 2.0 * x[0]", "holds", None),
    ("first_or_self", "f(xs) == f(xs)", "holds", None),
])
def test_a_shape_nothing_establishes_keeps_develops_verdict(mod, name, text,
                                                            verdict, route):
    p = _row(eval(name, vars(mod)), text, route)
    assert p.verdict == verdict, (p.verdict, p.note, p.counterexample)


@pytest.mark.parametrize("name, text, param", [
    ("is_empty", "f(xs) == (xs == 0)", "xs"),
    ("has_any", "f(xs) == (xs != 0)", "xs"),
    ("last_or_zero", "f(xs) == xs", "xs"),
])
def test_a_claim_decided_over_base_kinds_names_them(mod, name, text, param):
    p = _row(getattr(mod, name), text, None)
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert f"holds for {param} drawn as " in p.note


def test_same_holds_on_every_kind_core_compares(mod):
    p = _row(mod.same, "f(x) == x")
    kinds = p.meta["mathema.base_kinds"]["x"]
    held = {k for k, r in kinds.items() if r["verdict"] == "holds"}
    # None is an absent value and a complex result is not real: core
    # decides neither under a real claim
    assert held == set(kinds) - {"None", "complex"}, kinds


def test_is_empty_holds_on_numbers_and_is_not_falsified(mod):
    p = _row(mod.is_empty, "f(xs) == (xs == 0)")
    assert p.verdict == "holds", (p.verdict, p.note)
    kinds = p.meta["mathema.base_kinds"]["xs"]
    assert {"int", "float", "complex"} <= {
        k for k, r in kinds.items() if r["verdict"] == "holds"}
    assert kinds["empty list"]["verdict"] == "falsified"


def test_acc_keeps_holds_on_the_real_numbers(mod):
    p = _row(mod.acc_keeps, "f(y0) == y0 + 3.0")
    assert "holds for y0 drawn as bool, int, float" in p.note
    kinds = p.meta["mathema.base_kinds"]["y0"]
    assert kinds["non-empty str"]["verdict"] == "does not apply"


def test_a_claim_failing_on_every_kind_is_falsified_with_a_witness(mod):
    p = _row(mod.unequal, "f(x) != x")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample


def test_an_annotated_parameter_still_falsifies_on_one_failure(mod):
    p = _row(mod.annotated, "f(x) > x")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "base_kinds" not in str(p.meta)


@pytest.mark.parametrize("name, text", [
    ("tri", "f(x) <= 499500"), ("lit_index", "f(x) == f(x)"),
])
def test_a_wrong_shape_draw_never_falsifies(mod, name, text):
    p = _row(getattr(mod, name), text)
    kinds = p.meta["mathema.base_kinds"]["x"]
    assert all(r["verdict"] != "falsified" or "TypeError" not in str(r.get("witness"))
               for r in kinds.values()), kinds
