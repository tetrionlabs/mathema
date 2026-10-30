# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Absence compares as absence. Two sides that are both None at a
present input agree under `==` and `~=`: `json.loads('null')` is None on
both sides of a round trip, so the round trip holds there. None against
a number fails every relation, `!=` included; an ordering with None on
a side fails; and None against None under `!=` fails too, since the two
sides agree. A NaN keeps its own rule: from present inputs it is no
value and agrees with nothing.

A None f returns from present inputs is legitimate only where the
return type declares it (`-> Optional[float]`). Where it does not, the
None is no value and the value claim fails there, even where both sides
are that None: the computation line is falsified with the call as its
witness, and no separate policy row is made for it. The wording names
absence, never a nan, for a None.
"""
from __future__ import annotations

import json
import typing
from typing import Any, Optional

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


def test_an_undeclared_none_falsifies_the_value_claim_with_no_row_of_its_own():
    rows = _probes(none_undeclared, _REFLEXIVE)
    computation = rows["c[float]"]
    assert computation.verdict == "falsified", (computation.verdict, computation.note)
    assert computation.counterexample.startswith(
        "x = 0: f returned None from present inputs, and its return type "
        "(float) does not declare it"), computation.counterexample
    assert "Optional[float]" in computation.counterexample, computation.counterexample
    assert "nan" not in computation.counterexample.lower(), computation.counterexample
    # the failure is the implementation's: an absence where the declared
    # return type promises a value
    assert computation.stratum == {
        "mathematics": "sound", "blame": "implementation",
        "cause": "implementation:absent", "witness": "x = 0"}, computation.stratum
    flagged = [p for p in rows.values()
               if ((p.meta or {}).get("mathema.policy") or {}).get("kind") == "absent"
               and p.meta["mathema.policy"].get("parameter") is None]
    assert not flagged, [(p.name, p.verdict) for p in flagged]
    shown = repr(mathema.check(none_undeclared, claims=[claim(_REFLEXIVE, name="c")]))
    head = next(line for line in shown.splitlines() if line.startswith("  c "))
    assert head.rstrip().endswith("falsified at x = 0"), head
    assert "absent(f) introduces" not in shown, shown


@pytest.mark.xfail(strict=True, reason=(
    "derive-undeclared-none-exit-proven: derive reads f's `return None` as an "
    "opaque value and proves f(x) == f(x) by reflexivity, so the mathematics "
    "row stays proven where f has no value"))
def test_an_undeclared_none_falsifies_the_mathematics_row_on_route_derive():
    # f(x: float) -> float returns None everywhere: by decision D a None the
    # return type does not declare is no value, and a value claim fails at a
    # point where its side has no value, as the nan twin is falsified at 1/2
    (p,) = check_conjectures(none_undeclared, [claim(_REFLEXIVE, route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)


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


def none_annotated_none(x: float) -> None:
    return None


def none_annotated_any(x: float) -> Any:
    return None


def none_annotated_object(x: float) -> object:
    return None


def none_quoted_any(x: float) -> "typing.Any":
    return None


def none_unannotated(x: float):
    return None


@pytest.mark.parametrize("fn, declared", [
    (none_annotated_none, "None"), (none_annotated_any, "Any"),
    (none_annotated_object, "object"), (none_quoted_any, "Any")])
def test_a_return_type_that_admits_none_declares_the_absence(fn, declared):
    # None, Any and object all admit None: the absence is declared, judged
    # by the absent policy row, and never a failure of the value claim
    rows = _probes(fn, _REFLEXIVE)
    assert rows["c"].verdict in ("proven", "holds"), (rows["c"].verdict, rows["c"].note)
    assert rows["c[float]"].verdict == "holds", rows["c[float]"].counterexample
    declared_rows = [p for p in rows.values()
                     if ((p.meta or {}).get("mathema.policy") or {}).get("kind") == "absent"
                     and p.meta["mathema.policy"].get("parameter") is None]
    assert declared_rows and all(p.verdict == "proven" for p in declared_rows), \
        [(p.name, p.verdict) for p in declared_rows]
    assert f"from the return type {declared}:" in declared_rows[0].note, \
        declared_rows[0].note
    shown = repr(mathema.check(fn, claims=[claim(_REFLEXIVE, name="c")]))
    assert "Optional[None]" not in shown and "Optional[Any]" not in shown \
        and "Optional[object]" not in shown, shown


def test_an_unannotated_return_does_not_declare_the_absence():
    rows = _probes(none_unannotated, _REFLEXIVE)
    computation = rows["c[float]"]
    assert computation.verdict == "falsified", (computation.verdict, computation.note)
    assert "its return type (no annotation) does not declare it" in \
        computation.counterexample, computation.counterexample
