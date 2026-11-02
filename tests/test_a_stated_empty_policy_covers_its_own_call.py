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
