# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raise at a missing value is the missing value's only when the same
call, that parameter present and every other argument held, does not
raise. When it raises there too, other draws of the other arguments are
tried; where none lets f run with the value present, the row is unknown,
naming the other argument, never falsified. A row that is falsified
shows both calls: the one at the missing value and the one with it
present."""
import math
from typing import Any

from mathema import analyze, check
from mathema.conjecture import claim
from mathema.policy import _run_floor


def label(language: Any, name: str | None = None) -> str:
    kind = language.kind
    return name if name is not None else kind


def shout(language: Any, name: str | None = None) -> str:
    return name.upper() + str(language)


def rooted(x: float, name: str | None = None) -> str:
    r = math.sqrt(x)
    return name if name is not None else str(r)


def rooted_shout(x: float, name: str | None = None) -> str:
    r = math.sqrt(x)
    return name.upper() + str(r)


def tag(k: float, name: str | None = None) -> float:
    r = math.sqrt(k)
    return r if name is None else r + len(name)


def _row(fn, name, claims=None):
    rows = {p.name: p for p in check(fn, claims=claims).probes}
    return rows[name]


def test_a_raise_another_argument_causes_leaves_the_absence_row_unknown():
    row = _row(label, "absent[name]")
    assert row.verdict == "unknown", (row.verdict, row.counterexample, row.note)
    assert "language" in row.note, row.note
    assert "name = None" in row.note, row.note


def test_a_raise_the_absence_causes_is_falsified_with_the_present_call_shown():
    row = _row(shout, "absent[name]")
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert "name = None: f raised AttributeError" in row.counterexample
    assert ", and at name = " in row.counterexample, row.counterexample
    assert " f returned " in row.counterexample, row.counterexample


def test_another_argument_raising_on_some_draws_is_redrawn_and_the_absence_decided():
    facts = analyze(rooted)
    (call,) = _run_floor(rooted, facts, [{"x": -1.0, "name": None}], {})
    assert call.others is None, call
    assert call.raised is None and call.point["x"] >= 0 and call.point["name"] is None
    assert call.output == str(math.sqrt(call.point["x"]))


def test_a_redrawn_call_that_still_raises_at_the_absence_is_the_absences():
    facts = analyze(rooted_shout)
    (call,) = _run_floor(rooted_shout, facts, [{"x": -1.0, "name": None}], {})
    assert call.others is None, call
    assert call.raised == "AttributeError" and call.point["x"] >= 0
    at, output, raised = call.present
    assert raised is None and at["x"] == call.point["x"]
    assert isinstance(at["name"], str) and output == at["name"].upper() + str(
        math.sqrt(at["x"]))


def test_a_raise_on_every_draw_of_the_other_argument_is_undecided():
    facts = analyze(label)
    (call,) = _run_floor(label, facts, [{"language": 0, "name": None}], {})
    assert call.others == ("language",), call


def test_a_stated_raise_is_not_confirmed_by_another_arguments_raise():
    stated = claim("absent(f, name) raises(AttributeError)", name="p")
    row = _row(label, "p", [stated])
    assert row.verdict == "unknown", (row.verdict, row.note)
    assert "language" in row.note, row.note


def test_a_claims_draws_that_raise_for_another_argument_leave_the_absence_its_own():
    claims = [claim('for k in [-1, 1], name in {"ab"}|absent, f(k, name) >= 0', name="c"),
              claim("is_absent_safe(f)", name="g")]
    rows = {p.name: p for p in check(tag, claims=claims).probes}
    assert rows["absent[name]"].verdict == "holds", rows["absent[name]"].note
    assert "drops" in rows["absent[name]"].note
    assert rows["g"].verdict == "holds", (rows["g"].counterexample, rows["g"].note)


def truncated_root(k: float, x: float) -> float:
    return int(x) + math.sqrt(k)


def test_a_hole_is_read_the_same_way_at_another_draw_of_the_other_argument():
    facts = analyze(truncated_root)
    (call,) = _run_floor(truncated_root, facts, [{"k": -1.0, "x": float("nan")}], {})
    assert call.others is None, call
    assert call.raised == "ValueError" and call.point["k"] >= 0, call
    assert call.present[2] is None and call.present[0]["k"] == call.point["k"]
