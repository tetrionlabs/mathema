# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function is called with real values, never with a sentinel: where a
claim's finite set lists `None`, the function receives `None`; where it
lists the hole class, it receives each member the parameter's type
resolves to (`nan` for a float), each at least once per claim, and the
record says what was tried."""
import math
from typing import Optional

import pytest

import mathema
from mathema.domain import is_sentinel

SEEN: list = []


def recording(x: Optional[float]) -> float:
    SEEN.append(x)
    return 0.0


def recording_raises(x: Optional[float]) -> float:
    SEEN.append(x)
    raise ValueError("no value")


def run(fn, text: str, route: str = "best"):
    SEEN.clear()
    report = mathema.check(fn, claims=[mathema.claim(text, name="c", route=route)])
    return next(p for p in report.probes if p.name == "c")


@pytest.mark.parametrize("route", ["best", "probe"])
@pytest.mark.parametrize("text", ["for x in {0.25, None}, f(x) >= 0",
                                  "for x in {missing}, f(x) >= 0",
                                  "for x in {0.25, None, missing}, f(x) == 0"])
def test_the_function_never_sees_a_sentinel(text, route):
    run(recording, text, route)
    assert SEEN
    assert not any(is_sentinel(v) for v in SEEN)


@pytest.mark.parametrize("route", ["best", "probe"])
def test_every_listed_member_is_called_at_least_once(route):
    run(recording, "for x in {0.25, None, missing}, f(x) >= 0", route)
    assert any(v is None for v in SEEN)
    assert any(isinstance(v, float) and math.isnan(v) for v in SEEN)
    assert 0.25 in SEEN


def test_the_record_names_the_members_tried():
    probe = run(recording, "for x in {None, missing}, f(x) >= 0", route="probe")
    assert probe.meta["mathema.missing"]["tried"]["x"] == ["None", "nan"]


def test_a_raises_claim_over_the_class_is_called_with_nan():
    probe = run(recording_raises, "for x in {missing}, raises(f(x), ValueError)")
    assert probe.verdict == "proven"
    assert SEEN and all(isinstance(v, float) and math.isnan(v) for v in SEEN)


def sqrt_guarded(x: float) -> float:
    if x is None or x != x:
        raise ValueError("missing")
    return math.sqrt(x)


def zero_if_missing(x: Optional[float]) -> float:
    if x is None or x != x:
        return 0.0
    return float(x)


def label_any_missing(s: Optional[str]) -> str:
    if s is None or (isinstance(s, float) and s != s):
        return "-"
    return s.strip().upper()


def label(s: Optional[str]) -> str:
    if s is None:
        return "-"
    return s.strip().upper()


def test_s6_absence_raising_is_the_witness():
    probe = run(sqrt_guarded, "for x in {0.25, None}, f(x) >= 0")
    assert probe.verdict == "falsified"
    assert probe.counterexample == "x=None"
    assert "ValueError" in (probe.sketch or "")


def test_s10_a_replaced_absence_is_proven():
    assert run(zero_if_missing, "for x in {0.25, None}, f(x) >= 0").verdict in (
        "proven", "holds")


def test_p2_every_member_raises_the_stated_exception():
    assert run(sqrt_guarded, "for x in {missing}, raises(f(x), ValueError)").verdict == \
        "proven"


def test_p3_a_replacement_policy_is_proven():
    assert run(zero_if_missing, "for x in {missing}, f(x) == 0").verdict in (
        "proven", "holds")


def test_g2_a_listed_absence_reaches_a_string_function_as_none():
    assert run(label_any_missing, 'for s in {"a", None}, f(s) != ""').verdict in (
        "proven", "holds")


def test_g8_a_string_has_no_hole():
    probe = run(label, 'for s in {missing}, f(s) == "-"')
    assert probe.verdict == "skipped:misspecified"
    assert "a string has no hole" in probe.note
