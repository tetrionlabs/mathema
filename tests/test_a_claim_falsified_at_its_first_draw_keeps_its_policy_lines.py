# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What f does at a missing or absent input is judged whatever the
claim's own draws found: a claim falsified at its first draw, before the
probe reached a hole, keeps the policy lines its parameters' types
admit, as a claim falsified later does. A chained claim falsified at its
first link is one such claim."""
from typing import Optional

import pytest

import mathema


def doubled_plus_one(x: float) -> float:
    return 2 * x + 1


def optional_doubled(x: Optional[float]) -> float:
    return 2 * x + 1


def _rows(fn, text):
    rec = mathema.check(fn, claims=[mathema.claim(text, name="c")])
    return {p.name: p for p in rec.probes}, str(rec)


@pytest.mark.parametrize("text", [
    "for x in [0, 1], 3 < f(x) <= 1 < 2",
    "for x in [0, 1], f(x) > 5",
    # the same function falsified past its first draw, for comparison
    "for x in [0, 1], 0 <= f(x) <= 1",
])
def test_a_float_parameter_keeps_its_missing_line(text):
    rows, shown = _rows(doubled_plus_one, text)
    assert rows["c"].verdict == "falsified", (rows["c"].verdict, rows["c"].note)
    assert "missing[x]" in rows, sorted(rows)
    # 2 * nan + 1 is nan: f propagates the hole, as the default says
    assert rows["missing[x]"].verdict == "holds", rows["missing[x]"].note
    assert "policy       f(nan)" in shown, shown


def test_an_optional_parameter_keeps_both_its_lines():
    rows, shown = _rows(optional_doubled, "for x in [0, 1], f(x) > 5")
    assert rows["c"].verdict == "falsified", rows["c"].verdict
    assert rows["missing[x]"].verdict == "holds", rows["missing[x]"].note
    # 2 * None raises TypeError and nothing states that it may
    assert rows["absent[x]"].verdict == "falsified", rows["absent[x]"].note
    assert "policy       f(nan)" in shown and "policy       f(None)" in shown, shown
