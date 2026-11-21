# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter whose shape nothing establishes is decided on its float
draw, as an unannotated parameter is: a real float finding falsifies, and
a TypeError or AttributeError at an operation on the drawn float is a
draw defect, never a falsification. The other base kinds are run too and
decide nothing: each kind the claim held on becomes a suggested claim
binding the parameter to that kind, kept in the row's meta and shown as
a suggestion."""
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


def test_a_pass_through_holds_on_floats_and_suggests_other_kinds(mod):
    p = _row(mod.same, "f(v) == v")
    assert p.verdict == "holds", (p.verdict, p.note)
    suggested = p.meta["mathema.suggested_claims"]
    assert "for v in Z, f(v) == v" in suggested
    assert "for v in Z, f(v) == v" in p.note
    assert "holds for v drawn as" not in p.note


@pytest.mark.parametrize("name, text", [
    ("acc_num_ok", "f(y0) == 4 * y0"),
    ("nested_def_copy", "f(y0) == 2 * y0"),
    ("dec2_num", "f(x) == 3.0 * x"),
])
def test_a_float_overflow_falsifies_as_it_does_unannotated(mod, name, text):
    p = _row(getattr(mod, name), text)
    assert p.verdict == "falsified", (p.verdict, p.note, p.counterexample)


def test_a_wrong_shape_float_draw_is_a_draw_defect_naming_kinds_that_held(mod):
    p = _row(mod.tri, "f(x) <= 499500")
    assert p.verdict == "unknown", (p.verdict, p.note, p.counterexample)
    assert p.meta["mathema.draw_defect"]["param"] == "x"
    assert "holds" not in p.verdict
    assert "The claim holds with x in {False, True} only; it fails on int at" in p.note


def test_a_truth_test_holds_on_floats_and_suggests_only_kinds_that_held(mod):
    p = _row(mod.is_empty, "f(xs) == (xs == 0)")
    assert p.verdict == "holds", (p.verdict, p.note)
    kinds = p.meta["mathema.base_kinds"]["xs"]
    for text in p.meta["mathema.suggested_claims"]:
        assert "{''}" not in text and "{None}" not in text, text
    assert kinds["empty list"]["outcome"] == "counterexample"


def _kinds(p, param):
    return p.meta["mathema.base_kinds"][param]


def test_each_kind_has_one_outcome_read_from_where_it_raised(mod):
    times = _kinds(_row(mod.dec2_num, "f(x) == f(x)"), "x")
    assert times["non-empty str"]["outcome"] == "f-undefined", times
    ordered = _kinds(_row(mod.same, "f(v) >= 0"), "v")
    assert ordered["empty str"]["outcome"] == "claim-undefined", ordered
    assert ordered["int"]["outcome"] == "counterexample", ordered


def test_only_a_kind_that_held_is_suggested(mod):
    p = _row(mod.same, "f(v) >= 0")
    for text in p.meta["mathema.suggested_claims"]:
        assert "{''}" not in text and " in Z," not in text, text


def test_a_kind_inside_one_with_a_counterexample_is_only_a_narrowing(mod):
    p = _row(mod.same, "f(v) * f(v) == f(v)")
    kinds = _kinds(p, "v")
    assert kinds["int"]["outcome"] == "counterexample", kinds
    assert not any("{False, True}" in c for c in p.meta["mathema.suggested_claims"])
    assert "The claim holds with v in {False, True} only; it fails on int at" in p.note


def test_a_suggestion_says_what_was_drawn(mod):
    p = _row(mod.same, "f(v) == v")
    assert "What was drawn: " in p.note
    assert "v as int: " in p.note and "distinct" in p.note
    assert "[-10**6, 10**6]" in p.note


def test_bool_is_checked_at_both_values_and_none_is_not_run(mod):
    kinds = _kinds(_row(mod.same, "f(v) == v"), "v")
    assert kinds["bool"]["outcome"] == "checked-all", kinds
    assert kinds["None"]["outcome"] == "undecided", kinds
    assert "classified, not judged" in kinds["None"]["reason"]


def test_a_complex_identity_is_never_a_counterexample(mod):
    kinds = _kinds(_row(mod.same, "f(v) == v"), "v")
    assert kinds["complex"]["outcome"] != "counterexample", kinds


def test_the_float_draw_is_recorded_as_assumed(mod):
    p = _row(mod.same, "f(v) == v")
    assert p.meta["mathema.assumed_shape"] == {"v": "float"}
    assert ("v was drawn as a float because nothing says what v is; "
            "annotate it or bind it in the claim (for v in ...)") in p.note


def test_several_parameters_are_each_varied_alone(mod):
    p = _row(mod.first_unless, "f(a, b) == a")
    assert set(p.meta["mathema.base_kinds"]) == {"a", "b"}
    assert "each parameter varied alone with the others drawn as floats" in p.note


def test_a_shape_the_annotation_or_the_claim_fixes_is_not_surveyed(mod):
    for p in (_row(mod.annotated, "f(x) == x"),
              _row(mod.same, "for v in [0, 1], f(v) == v")):
        assert "mathema.base_kinds" not in (p.meta or {}), p.meta
        assert "mathema.suggested_claims" not in (p.meta or {}), p.meta


def test_each_claim_on_an_annotated_function_runs_its_own_kind(mod):
    (unbound, bound) = check_conjectures(
        mod.annotated, [claim("f(x) == x", route="probe"),
                        claim("for x in Z, f(x) == x", route="probe")])
    assert unbound.verdict == "holds" and bound.verdict == "holds"
    for p in (unbound, bound):
        assert "mathema.base_kinds" not in (p.meta or {}), p.meta


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
def test_the_kind_runs_change_no_check_line(tmp_path, monkeypatch, capsys,
                                             spec, text, line):
    from mathema.cli import main
    (tmp_path / "kcli.py").write_text(_CLI_CASES)
    monkeypatch.chdir(tmp_path)
    main(["check", f"kcli.py:{spec}", "--claim", text])
    out = capsys.readouterr().out.strip().splitlines()
    assert line in out, out
