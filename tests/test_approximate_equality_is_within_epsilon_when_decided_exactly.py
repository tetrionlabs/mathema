# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`a ~= b` is `abs(a - b) <= ε` on both lines, ε the claim's declared
tolerance, else 1e-9: on the mathematics line decided exactly, on the
computation line in float64. A gap inside ε is the claim holding, at
every magnitude, wherever the relation is decided: the probe's draws,
the exact reading of a draw, a finite sweep. A gap past ε is a
falsification, and `==` stays exact equality."""
import ast

import pytest

from mathema._allowance import relation_within
from mathema.conjecture import _exact_verdict, check_conjectures, claim

_ROUTES = ["best", "probe"]
_SEQUENCE = "for xs in [0, 1]^n \\ {missing}, f(xs) ~= sum(xs)"


def loop_near(xs: list) -> float:
    t = 0.0
    for v in xs:
        t += v
    return t + 5e-10


def loop_under(xs: list) -> float:
    t = 0.0
    for v in xs:
        t += v
    return t + 9e-10


def loop_over(xs: list) -> float:
    t = 0.0
    for v in xs:
        t += v
    return t + 1.1e-9


def loop_inside_declared(xs: list) -> float:
    t = 0.0
    for v in xs:
        t += v
    return t + 5e-7


def loop_past_declared(xs: list) -> float:
    t = 0.0
    for v in xs:
        t += v
    return t + 2e-6


def while_near(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    return x + 5e-10


def while_over(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    return x + 1.1e-9


def rounded_near(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    # in float the shift through 1e8 rounds by up to 7.5e-9; in exact
    # arithmetic it cancels, leaving the gap x / 4e9, at most 5e-10
    return (x + 100000000) - 100000000 + x / 4000000000


def rounded_over(x: float) -> float:
    i = 0
    while i < 3:
        i += 1
    # the same shift, leaving the exact gap x / 500000000, at least
    # 2e-9 over [1, 2]
    return (x + 100000000) - 100000000 + x / 500000000


def _verdict(fn, law, route, **kw):
    (p,) = check_conjectures(fn, [claim(law, route=route, **kw)])
    return p


@pytest.mark.parametrize("route", _ROUTES)
def test_a_sequence_gap_inside_epsilon_holds(route):
    p = _verdict(loop_near, _SEQUENCE, route)
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
    assert p.counterexample is None


@pytest.mark.parametrize("route", _ROUTES)
def test_a_sequence_gap_just_under_epsilon_holds(route):
    p = _verdict(loop_under, _SEQUENCE, route)
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


@pytest.mark.parametrize("route", _ROUTES)
def test_a_sequence_gap_just_over_epsilon_is_falsified(route):
    p = _verdict(loop_over, _SEQUENCE, route)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample


@pytest.mark.parametrize("route", _ROUTES)
def test_a_declared_tolerance_is_epsilon(route):
    inside = _verdict(loop_inside_declared, _SEQUENCE, route, tolerance=1e-6)
    assert inside.verdict == "holds", (inside.verdict, inside.counterexample)
    past = _verdict(loop_past_declared, _SEQUENCE, route, tolerance=1e-6)
    assert past.verdict == "falsified", (past.verdict, past.note)
    assert past.counterexample


@pytest.mark.parametrize("route", _ROUTES)
def test_a_scalar_unliftable_body_holds_inside_epsilon(route):
    p = _verdict(while_near, "for x in [0, 1], f(x) ~= x", route)
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


@pytest.mark.parametrize("route", _ROUTES)
def test_a_scalar_unliftable_body_past_epsilon_is_falsified(route):
    p = _verdict(while_over, "for x in [0, 1], f(x) ~= x", route)
    assert p.verdict == "falsified", (p.verdict, p.note)


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("fn,law", [
    (loop_near, _SEQUENCE.replace("~=", "==")),
    (while_near, "for x in [0, 1], f(x) == x"),
])
def test_equality_with_the_same_gap_stays_falsified(route, fn, law):
    p = _verdict(fn, law, route)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample


@pytest.mark.parametrize("route", _ROUTES)
def test_a_draw_decided_exactly_holds_inside_epsilon(route):
    # the float computation misses by more than ε, the exact gap is
    # inside it: the mathematics at the draw decides, and it holds
    p = _verdict(rounded_near, "for x in [1, 2], f(x) ~= x", route)
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


@pytest.mark.parametrize("route", _ROUTES)
def test_a_draw_decided_exactly_past_epsilon_is_falsified(route):
    p = _verdict(rounded_over, "for x in [1, 2], f(x) ~= x", route)
    assert p.verdict == "falsified", (p.verdict, p.note)


_FINITE = "for x in {0, 1e-06, 2e-06}, f(x) ~= x"


def test_a_finite_sweep_proves_a_gap_inside_epsilon():
    p = _verdict(while_near, _FINITE, "best")
    assert p.verdict == "proven", (p.verdict, p.counterexample, p.note)
    assert p.route == "derive:brute_force"


def test_a_finite_sweep_falsifies_a_gap_past_epsilon():
    p = _verdict(while_over, _FINITE, "best")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_finite_sweep_falsifies_equality_with_the_same_gap():
    p = _verdict(while_near, _FINITE.replace("~=", "=="), "best")
    assert p.verdict == "falsified", (p.verdict, p.note)


def _exact_at(fn, law, x, **kw):
    cj = claim(law, **kw)
    code_l = compile(ast.parse(cj.lhs, mode="eval"), "<lhs>", "eval")
    code_r = compile(ast.parse(cj.rhs, mode="eval"), "<rhs>", "eval")
    return _exact_verdict(cj, code_l, code_r, {"x": x, "f": fn}, fn, {})


def shift(x):
    return x + x / 2000


def test_the_exact_verdict_reads_approximate_equality_within_epsilon():
    # at x = 1e-6 the exact gap is 5e-10
    assert _exact_at(shift, "for x in [0, 1], f(x) ~= x", 1e-6) is True
    # at x = 4e-6 it is 2e-9
    assert _exact_at(shift, "for x in [0, 1], f(x) ~= x", 4e-6) is False


def test_the_exact_verdict_reads_a_declared_tolerance_as_epsilon():
    law = "for x in [0, 1], f(x) ~= x"
    assert _exact_at(shift, law, 1e-3, tolerance=1e-6) is True
    assert _exact_at(shift, law, 4e-3, tolerance=1e-6) is False


def test_the_exact_verdict_keeps_equality_exact():
    assert _exact_at(shift, "for x in [0, 1], f(x) == x", 1e-6) is False


@pytest.mark.parametrize("magnitude", [0.0, 1e-6, 1e-3])
def test_the_computation_line_reads_approximate_equality_within_epsilon(
        magnitude):
    assert relation_within(magnitude + 5e-10, magnitude, "~=") is True
    assert relation_within(magnitude + 2e-9, magnitude, "~=") is False


@pytest.mark.parametrize("relation", ["==", "<", ">"])
def test_the_computation_line_leaves_the_other_relations_as_they_were(
        relation):
    # at 1e-6 the allowance is 2e-13: a gap of 5e-10 is a miss under ==
    # and a strict ordering gets no allowance
    assert relation_within(1e-6 + 5e-10, 1e-6, relation) is (relation == ">")


def _empty_line(fn, relation):
    from mathema import check
    record = check(fn, claims=[claim(_SEQUENCE, name="value"),
                               claim(f"f([]) {relation} 0", name="empty")])
    return {p.name: p for p in record.probes}


def test_an_empty_policy_stated_with_approximate_equality_is_within_epsilon():
    # loop_near([]) returns 5e-10, inside ε of the stated 0
    probes = _empty_line(loop_near, "~=")
    line = probes["is_empty_safe[xs]"]
    assert line.verdict == "holds", (line.verdict, line.note)
    assert probes["value"].verdict == "holds", probes["value"].note


def test_an_empty_policy_past_epsilon_is_falsified():
    probes = _empty_line(loop_over, "~=")
    line = probes["is_empty_safe[xs]"]
    assert line.verdict == "falsified", (line.verdict, line.note)


def test_an_empty_policy_stated_with_equality_stays_exact():
    probes = _empty_line(loop_near, "==")
    line = probes["is_empty_safe[xs]"]
    assert line.verdict == "falsified", (line.verdict, line.note)
