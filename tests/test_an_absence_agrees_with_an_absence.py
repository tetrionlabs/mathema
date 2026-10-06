# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Absence compares as absence. Two sides that are both None at a
present input agree under `==` and `~=`: `json.loads('null')` is None on
both sides of a round trip, so the round trip holds there. None against
a number fails every relation, `!=` included; an ordering with None on
a side fails; and None against None under `!=` fails too, since the two
sides agree. A NaN keeps its own rule: from present inputs it is no
value and agrees with nothing.

Whether f may return None from present inputs is the absence policy
line's question, not the comparison's: a return type that declares it
(`-> Optional[float]`) makes the None legitimate, and a return type that
does not gets a falsified policy line, so the claim's headline is never
a bare proven over a None the type does not admit. The wording names
absence, never a nan, for a None.
"""
from __future__ import annotations

import json
from typing import Optional

import pytest

import mathema
from mathema.claims import check_conjectures, claim


def round_trip(text: str) -> str:
    return json.dumps(json.loads(text))


def none_undeclared(x: float) -> float:
    return None


def none_declared(x: float) -> Optional[float]:
    return None


def one(x: float) -> float:
    return 1.0


def nan_undeclared(x: float) -> float:
    return float("nan")


def _probes(fn, law):
    return {p.name: p for p in mathema.check(fn, claims=[claim(law, name="c")]).probes}


def _head(fn, law) -> str:
    rec = mathema.check(fn, claims=[claim(law, name="c")])
    return next(line for line in repr(rec).splitlines() if line.startswith("  c "))


def test_a_json_null_round_trip_agrees_on_both_sides():
    (p,) = check_conjectures(round_trip, [claim(
        'let loads = json.loads, for text in {"null", "1", "[null]"}, '
        "loads(f(text)) == loads(text)")])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample, p.note)


#: the claim over present inputs only, so the lines under it are about
#: the output alone (a nan input is the missing policy line's case)
_REFLEXIVE = "for x in [0, 1] \\ {missing}, f(x) == f(x)"


def test_an_undeclared_none_agrees_on_the_value_line_and_is_flagged_on_the_policy_line():
    rows = _probes(none_undeclared, _REFLEXIVE)
    assert rows["c"].verdict in ("proven", "holds"), (rows["c"].verdict, rows["c"].note)
    assert rows["c[float]"].verdict == "holds", (rows["c[float]"].verdict,
                                                 rows["c[float]"].counterexample)
    flagged = [p for p in rows.values()
               if ((p.meta or {}).get("mathema.policy") or {}).get("kind") == "absent"
               and p.meta["mathema.policy"].get("parameter") is None]
    assert flagged, sorted(rows)
    (row,) = flagged
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert "does not declare" in (row.note or ""), row.note
    assert "nan" not in (row.note or "").lower(), row.note
    shown = repr(mathema.check(none_undeclared, claims=[claim(_REFLEXIVE, name="c")]))
    head = next(line for line in shown.splitlines() if line.startswith("  c "))
    assert head.rstrip().endswith("falsified at x = 0.0"), head
    assert "falsified  policy       absent(f) introduces" in shown, shown
    assert "declare it in the return type: Optional[float]" in shown, shown


def test_a_declared_none_is_legitimate_and_the_headline_is_not_falsified():
    rows = _probes(none_declared, _REFLEXIVE)
    assert rows["c"].verdict in ("proven", "holds"), rows["c"].verdict
    assert rows["c[float]"].verdict == "holds", rows["c[float]"].counterexample
    declared = [p for p in rows.values()
                if ((p.meta or {}).get("mathema.policy") or {}).get("kind") == "absent"
                and p.meta["mathema.policy"].get("parameter") is None]
    assert declared and all(p.verdict == "proven" for p in declared), \
        [(p.name, p.verdict) for p in declared]
    head = _head(none_declared, _REFLEXIVE)
    assert "falsified" not in head, head


@pytest.mark.parametrize("law", [
    "for x in [0, 1], f(x) == 1",
    "let g = tests.test_an_absence_agrees_with_an_absence.one, "
    "for x in [0, 1], f(x) == g(x)",
    "for x in [0, 1], f(x) >= 0",
    "for x in [0, 1], f(x) <= 1",
])
def test_none_against_a_number_fails_every_relation(law):
    (p,) = check_conjectures(none_undeclared, [claim(law)])
    assert p.verdict == "falsified", (law, p.verdict, p.note)
    assert "None" in (p.counterexample or ""), p.counterexample
    assert "nan" not in (p.counterexample or "").lower(), p.counterexample


@pytest.mark.parametrize("law", [
    "for x in [0, 1], f(x) != f(x)",
    "for x in [0, 1], f(x) <= f(x)",
    "for x in [0, 1], f(x) < f(x)",
])
def test_none_against_none_fails_a_disequality_and_every_ordering(law):
    (p,) = check_conjectures(none_undeclared, [claim(law)])
    assert p.verdict == "falsified", (law, p.verdict, p.note)
    assert "None vs None" in (p.counterexample or ""), p.counterexample
    assert "nan" not in (p.counterexample or "").lower(), p.counterexample


def test_a_nan_from_present_inputs_still_agrees_with_nothing():
    (p,) = check_conjectures(nan_undeclared, [claim("for x in [0, 1], f(x) == f(x)",
                                                     route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "nan" in (p.counterexample or ""), p.counterexample
