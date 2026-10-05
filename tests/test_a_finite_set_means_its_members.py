# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A finite set is exactly its members: `{6, 28, 496}` admits no missing
value of either kind, `{0.25, None}` admits 0.25 and the absence of the
object, `{0.25, nan}` 0.25 and the NaN hole, `{missing}` the hole class
and `{None}` absence alone. Whatever the parameter's annotation says,
the set is what the claim quantifies over."""
import math

import pytest

import mathema
from mathema.domain import (ABSENT, MISSING, domain_contains, finite_members,
                            member, parse_binding, render_domain)


def bound(text: str):
    return parse_binding(f"x in {text}")[1]


def test_a_set_of_numbers_admits_nothing_missing():
    b = bound("{6, 28, 496}")
    assert not domain_contains(None, b)
    assert not domain_contains(float("nan"), b)
    assert render_domain(b, ascii_mode=True) == "{6, 28, 496}"


def test_a_listed_none_is_absence_only():
    b = bound("{0.25, None}")
    assert b == frozenset({0.25, ABSENT})
    assert domain_contains(None, b)
    assert not domain_contains(float("nan"), b)


def test_a_listed_nan_is_that_hole_only():
    b = bound("{0.25, nan}")
    assert b == frozenset({0.25, member("nan")})
    assert domain_contains(float("nan"), b)
    assert not domain_contains(None, b)


def test_a_listed_class_is_every_hole():
    b = bound("{missing}")
    assert b == frozenset({MISSING})
    assert domain_contains(float("nan"), b)
    assert not domain_contains(None, b)


def test_a_listed_none_alone_is_absence():
    assert bound("{None}") == frozenset({ABSENT})


def test_the_members_a_sweep_visits_are_real_values():
    swept = finite_members(bound("{0.25, None, missing}"), 10, members=("nan",))
    assert swept[0] == 0.25 and swept[1] is None and math.isnan(swept[2])
    assert not any(type(v).__name__ == "_Sentinel" for v in swept)


def fixed_six(n: int) -> int:
    return n % 10


@pytest.mark.parametrize("text", ["{6, 28, 496}"])
def test_a_set_of_numbers_is_proven_without_a_missing_point(text):
    report = mathema.check(fixed_six, claims=[
        mathema.claim(f"for n in {text}, f(n) >= 0", name="c")])
    probe = next(p for p in report.probes if p.name == "c")
    assert probe.verdict == "proven"
    assert probe.statement == f"for n in {text}, f(n) >= 0"
