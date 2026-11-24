# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The rules for a named missing value hold whichever route decides the
claim. On the probe route, as on derive: a None result its return type
does not admit falsifies at the named value; a None it admits, and a
raise behind the function's own guard, leave the value out of the
printed domain; an uncovered raise leaves it out too and links the
claim to its falsified policy row."""
from typing import Optional

import mathema
from mathema.conjecture import check_conjectures, claim

TEXT = "for x in {1, None}, y in [0, 1], f(x, y) == 0"


def none_under_float(x: Optional[float], y: float) -> float:
    if x is None:
        return None  # type: ignore[return-value]
    return (x - 1) * y


def none_under_optional(x: Optional[float], y: float) -> "float | None":
    if x is None:
        return None
    return (x - 1) * y


def guarded(x: Optional[float], y: float) -> float:
    if x is None:
        raise ValueError("x is required")
    return (x - 1) * y


def scaled(x: Optional[float], y: float) -> float:
    return (x - 1) * y  # type: ignore[operator]


def _probe_row(fn):
    (row,) = check_conjectures(fn, [claim(TEXT, route="probe")])
    return row


def _probe_rows(fn):
    rec = mathema.check(fn, claims=[claim(TEXT, name="c", route="probe")])
    return {p.name: p for p in rec.probes}


def test_none_under_a_float_return_falsifies_on_the_probe():
    row = _probe_row(none_under_float)
    assert row.route == "probe", row.route
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.counterexample.startswith("x = None"), row.counterexample
    assert "return type float does not admit" in row.note, row.note


def test_an_admitted_none_is_left_out_on_the_probe():
    rows = _probe_rows(none_under_optional)
    main = rows["c"]
    assert (main.route or "").startswith("probe"), main.route
    assert main.verdict == "holds", (main.verdict, main.note)
    assert main.statement.startswith("for x in {1}, "), main.statement


def test_a_guarded_raise_is_left_out_on_the_probe():
    rows = _probe_rows(guarded)
    main = rows["c"]
    assert main.verdict == "holds", (main.verdict, main.note)
    assert main.statement.startswith("for x in {1}, "), main.statement
    assert ("x = None raises ValueError, from the guard on line 2 (absent[x])"
            in main.note), main.note


def test_an_uncovered_raise_is_linked_to_its_policy_row_on_the_probe():
    rows = _probe_rows(scaled)
    main = rows["c"]
    assert main.verdict == "holds", (main.verdict, main.note)
    assert main.statement.startswith("for x in {1}, "), main.statement
    assert main.meta["mathema.claim_group"] == [
        {"row": "absent[x]", "verdict": "falsified", "value": "x = None"}]
