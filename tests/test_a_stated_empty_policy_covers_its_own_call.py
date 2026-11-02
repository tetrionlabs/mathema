# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A stated empty policy is a claim about one call: `f([], 'spectral')
== []` says what f gives for the empty input with the method
'spectral', and nothing about the method 'diag'. The empty-input line of
a value claim beside it reads the policy wherever the line's call is the
policy's call (the same literal arguments, a default counting as the
value it supplies), and reads the code alone everywhere else. The value
a policy names is compared as a value, a container included: `f([]) ==
[]` holds where f returns the empty list.
"""
from __future__ import annotations

import pytest

from mathema._empty_input import _same_pin, stated_policies
from mathema.claims import check_conjectures, claim


def fix(xs, method="spectral"):
    if method == "spectral":
        return [max(x, 0.0) for x in xs]
    if method == "diag":
        if not xs:
            raise ValueError("no entries to shift")
        low = min(xs)
        return [x + 1.0 - low for x in xs]
    raise NotImplementedError(method)


_SPECTRAL = "for xs in [0, 1]^n, f(xs, 'spectral') == xs"
_DIAG = "for xs in [0, 1]^n, min(f(xs, 'diag')) >= 1"


def _rows(laws):
    """The claim rows by name, and the empty-input line under each claim
    by the claim's name."""
    probes = check_conjectures(fix, [claim(t, name=f"c{i}")
                                     for i, t in enumerate(laws)],
                                float_companions=True)
    claims = {p.name: p for p in probes}
    lines = {(p.meta or {}).get("mathema.companion_of"): p for p in probes
             if p.name == "is_empty_safe[xs]"}
    return claims, lines


def _lines(laws):
    return _rows(laws)[1]


def test_a_container_value_policy_is_read_as_a_value():
    rows = _lines([_SPECTRAL, "f([], 'spectral') == []"])
    line = rows["c0"]
    assert line.name == "is_empty_safe[xs]", line
    assert line.verdict == "holds", (line.verdict, line.note)


def test_a_container_value_policy_still_falsifies_a_different_value():
    rows = _lines([_SPECTRAL, "f([], 'spectral') == [0.0]"])
    line = rows["c0"]
    assert line.verdict == "falsified", (line.verdict, line.note)
    assert "where the stated policy is f([], 'spectral') == [0.0]" \
        in line.note, line.note


def test_a_policy_for_one_method_says_nothing_about_another():
    # 'diag' refuses the empty input behind its own guard, which the
    # line reads as deliberate; the 'spectral' policy is not its call
    rows = _lines([_DIAG, "f([], 'spectral') == []"])
    line = rows["c0"]
    assert line.name == "is_empty_safe[xs]", line
    assert line.verdict == "holds", (line.verdict, line.note)
    assert "stated policy" not in (line.note or ""), line.note


def test_a_default_argument_counts_as_the_value_it_supplies():
    rows = _lines([_SPECTRAL, "f([]) == [0.0]"])
    assert rows["c0"].verdict == "falsified", rows["c0"].note
    rows = _lines([_DIAG, "f([]) == [0.0]"])
    assert rows["c0"].verdict == "holds", rows["c0"].note


def test_the_siblings_keep_their_verdicts_when_the_policy_is_stated():
    before = _rows([_SPECTRAL, _DIAG])[0]
    after = _rows([_SPECTRAL, _DIAG, "f([], 'spectral') == []"])[0]
    for name in ("c0", "c1"):
        assert after[name].verdict == before[name].verdict, \
            (name, before[name].note, after[name].note)


_NAN = float("nan")
_NAN_SUM = "for xs in [0, 1]^n, f(xs) == sum(xs)"


def _returns(value):
    def f(xs):
        if not xs:
            return value
        return sum(xs)
    return f


def _empty_line(fn, policy):
    (line,) = _line_of(fn, _NAN_SUM, policy)
    return line


@pytest.mark.parametrize("value", [5.0, None, _NAN, "x", [5.0], [[]]],
                         ids=repr)
@pytest.mark.parametrize("relation", ["==", "~="])
def test_nothing_but_an_empty_container_meets_an_empty_container_policy(
        value, relation):
    line = _empty_line(_returns(value), f"f([]) {relation} []")
    assert line.verdict == "falsified"


@pytest.mark.parametrize("value,written", [
    ([], "0"), ([], "5"), ([5.0, 5.0], "5"), (5.0, "[5.0, 5.0]"),
    ([[], []], "0"), ([0.0, 1.0], "0"), (0.0, "[1.0]"),
], ids=repr)
@pytest.mark.parametrize("relation", ["==", "~="])
def test_a_shape_mismatch_does_not_meet_a_value_policy(value, written, relation):
    line = _empty_line(_returns(value), f"f([]) {relation} {written}")
    assert line.verdict == "falsified"


@pytest.mark.parametrize("value,written", [
    ([], "[]"), (5.0, "5"), ([5.0, 5.0], "[5.0, 5.0]"), ((), "[]"),
    ([0.0, 0.0], "0"),
], ids=repr)
@pytest.mark.parametrize("relation", ["==", "~="])
def test_the_same_shape_meets_a_value_policy(value, written, relation):
    assert _empty_line(_returns(value),
                       f"f([]) {relation} {written}").verdict == "holds"


def nan_fill(xs, fill=float("nan")):
    if not xs:
        return fill
    return sum(xs)


def nan_pair_fill(xs, fill=(float("nan"), 1.0)):
    if not xs:
        return fill
    return sum(xs)


def fill_by_value(xs, fill=float("nan")):
    if not xs:
        if fill == fill:
            return None
        return 7.0
    return sum(xs)


def _line_of(fn, value_claim, policy):
    rows = check_conjectures(fn, [claim(value_claim, name="c"),
                                  claim(policy, name="policy")],
                             float_companions=True)
    return [r for r in rows if r.name.startswith("is_empty_safe")]


def test_a_nan_default_is_covered_by_the_policy_that_leaves_it_out():
    (line,) = _line_of(nan_fill, _NAN_SUM, "f([]) in {missing}")
    assert line.verdict == "holds"
    assert "as f([]) in {missing} states" in line.note


def test_a_policy_naming_nan_covers_the_call_at_the_nan_default():
    (line,) = _line_of(nan_fill, _NAN_SUM, "f([], nan) in {missing}")
    assert line.verdict == "holds"
    assert "states" in line.note


def test_a_nan_inside_a_default_container_is_the_same_pin():
    # f([]) gives a pair, no missing value, and the policy is about this call
    (line,) = _line_of(nan_pair_fill, _NAN_SUM, "f([]) in {missing}")
    assert line.verdict == "falsified"
    assert "where the stated policy" in line.note


def test_a_policy_pinned_at_a_number_says_nothing_about_the_nan_default():
    (line,) = _line_of(fill_by_value, _NAN_SUM, "f([], 1.0) in {missing}")
    assert "stated policy" not in (line.note or "")
    assert "states" not in (line.note or "")


def test_a_nan_default_is_covered_by_a_value_policy_too():
    (line,) = _line_of(fill_by_value, _NAN_SUM, "f([]) == 7.0")
    assert line.verdict == "holds"
    assert "as f([]) == 7.0 states" in line.note


@pytest.mark.parametrize("have,want,same", [
    (_NAN, _NAN, True), (float("nan"), float("nan"), True),
    ([_NAN, 1.0], (float("nan"), 1.0), True), (_NAN, 1.0, False),
    (1.0, _NAN, False), ([_NAN], _NAN, False), (1.0, 1.0, True),
    (1.0, 1.0 + 1e-12, False), (None, None, True), (None, _NAN, False),
    (float("inf"), float("inf"), True), (float("inf"), -float("inf"), False),
], ids=repr)
def test_a_pin_is_met_by_the_value_it_names(have, want, same):
    assert _same_pin(have, want) is same


def test_the_words_nan_and_inf_are_literal_pins():
    def fn(xs, fill=0.0):
        return fill
    (nan_pin, inf_pin, neg_pin, pair_pin) = [
        stated_policies(fn, [claim(c, name="p")], "xs")[0][5]["fill"]
        for c in ("f([], nan) in {missing}", "f([], inf) == 1",
                  "f([], -inf) == 1", "f([], [nan, 1.0]) == 1")]
    assert nan_pin != nan_pin
    assert inf_pin == float("inf")
    assert neg_pin == -float("inf")
    assert pair_pin[0] != pair_pin[0] and pair_pin[1] == 1.0
