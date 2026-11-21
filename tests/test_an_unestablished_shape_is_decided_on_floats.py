# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter whose shape nothing establishes is decided on its float
draw, as an unannotated parameter is: a real float finding falsifies, and
a TypeError or AttributeError at an operation on the drawn float is a
draw defect, never a falsification. No other type is drawn for it, and
the row records that the float was assumed."""
import importlib.util
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

FNS = '''
    def annotated(x: float):
        return x


    def deco_plain(fn):
        def w(x):
            return fn(x)
        return w


    def same(v):
        return v


    def acc_num_ok(y0):
        t = y0
        for _ in range(2):
            t = t * 2.0
        return t


    def nested_def_copy(y0):
        t = y0
        def g():
            return t * 2.0
        return g()


    @deco_plain
    def dec2_num(x):
        return x * 3.0


    def tri(x):
        return sum(range(x))


    def is_empty(xs):
        return not xs


    def first_unless(a, b):
        return a if b else a
'''


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("floats") / "float_companion_fns.py"
    path.write_text(textwrap.dedent(FNS))
    spec = importlib.util.spec_from_file_location("float_companion_fns", path)
    m = importlib.util.module_from_spec(spec)
    sys.modules["float_companion_fns"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("float_companion_fns", None)


def _row(fn, text):
    (p,) = check_conjectures(fn, [claim(text, route="probe")])
    return p


def test_a_pass_through_holds_on_floats_and_draws_no_other_type(mod):
    p = _row(mod.same, "f(v) == v")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "mathema.base_kinds" not in p.meta
    assert "mathema.suggested_claims" not in p.meta


@pytest.mark.parametrize("name, text", [
    ("acc_num_ok", "f(y0) == 4 * y0"),
    ("nested_def_copy", "f(y0) == 2 * y0"),
    ("dec2_num", "f(x) == 3.0 * x"),
])
def test_a_float_overflow_falsifies_as_it_does_unannotated(mod, name, text):
    p = _row(getattr(mod, name), text)
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)


def test_a_wrong_shape_float_draw_is_a_draw_defect(mod):
    p = _row(mod.tri, "f(x) <= 499500")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.draw_defect"]["param"] == "x"


def test_a_truth_test_holds_on_floats(mod):
    p = _row(mod.is_empty, "f(xs) == (xs == 0)")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_the_float_draw_is_recorded_as_assumed(mod):
    p = _row(mod.same, "f(v) == v")
    assert p.meta["mathema.assumed_shape"] == {"v": "float"}
    assert ("v was drawn as a float because nothing says what v is; "
            "annotate it or bind it in the claim (for v in ...)") in p.note


def test_several_unestablished_parameters_are_each_recorded(mod):
    p = _row(mod.first_unless, "f(a, b) == a")
    assert p.meta["mathema.assumed_shape"] == {"a": "float", "b": "float"}


def test_a_shape_the_annotation_or_the_claim_fixes_is_not_assumed(mod):
    for p in (_row(mod.annotated, "f(x) == x"),
              _row(mod.same, "for v in [0, 1], f(v) == v")):
        assert "mathema.assumed_shape" not in (p.meta or {}), p.meta


def test_each_claim_on_an_annotated_function_runs_its_own_kind(mod):
    (unbound, bound) = check_conjectures(
        mod.annotated, [claim("f(x) == x", route="probe"),
                        claim("for x in Z, f(x) == x", route="probe")])
    assert unbound.verdict == "holds" and bound.verdict == "holds"
    for p in (unbound, bound):
        assert "mathema.assumed_shape" not in (p.meta or {}), p.meta


_CLI_CASES = '''
def truthy(x):
    if x:
        return 1
    return 0


def flip(x):
    return not x


def pick(a, b):
    return a or b
'''


@pytest.mark.parametrize("spec, text, line", [
    ("truthy", "f(x) >= 0",
     "ok   kcli.truthy: source, no side effects; claims 1/1 checked "
     "(0 proven, 1 holds, 0 falsified)"),
    ("flip", "f(f(x)) == x",
     "FAIL kcli.flip: source, no side effects; claims 1/1 checked "
     "(0 proven, 0 holds, 1 falsified)  <- 1 falsified claim(s)"),
    ("pick", "f(a, b) == (a or b)",
     "ok   kcli.pick: source, no side effects; claims 1/1 checked "
     "(0 proven, 1 holds, 0 falsified)"),
])
def test_the_float_path_changes_no_check_line(tmp_path, monkeypatch, capsys,
                                             spec, text, line):
    from mathema.cli import main
    (tmp_path / "kcli.py").write_text(_CLI_CASES)
    monkeypatch.chdir(tmp_path)
    main(["check", f"kcli.py:{spec}", "--claim", text])
    out = capsys.readouterr().out.strip().splitlines()
    assert line in out, out
