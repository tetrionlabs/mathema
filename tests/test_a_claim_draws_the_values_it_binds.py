# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's own binding is what f is called with. A mapping parameter
bound to an interval takes numbers from that interval, never a dict. A
name the claim passes inside an expression (`f([triggers, "dependency"])`)
is drawn from its binding as a value, whatever kind f's parameter of
that name has. A keyword written in the claim's call is part of the call
derive reads, so it does not stop derive. An absence is blamed on a
parameter only when f answers differently with that parameter present."""
import pytest

import mathema
from mathema.conjecture import check_conjectures, claim

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


def number_text(value: dict) -> str:
    if not isinstance(value, (int, float)):
        return "other"
    return f"{value:.2g}"


_OWN = ("form", "provenance", "defaults", "claims")


def cause_of(triggers) -> str:
    triggers = list(triggers or [])
    if any(t in _OWN for t in triggers):
        return "this function changed"
    if "dependency" in triggers:
        return "a callee changed"
    return "nothing changed"


def move(before: str, after: str, *, commit: "str | None") -> "dict | None":
    if before == after:
        return None
    out = {"from": before, "to": after}
    if commit:
        out["commit"] = commit
    return out


def shifted(x: float, *, k: float) -> float:
    return x + k


def _row(fn, text: str, name: str = "c"):
    rec = mathema.check(fn, claims=[claim(text, name=name)])
    return next(p for p in rec.probes if p.name == name)


def test_a_mapping_parameter_bound_to_an_interval_takes_numbers():
    row = _row(number_text, 'for value in [1, 3], f(value) != "other"')
    assert row.verdict in ("proven", "holds"), (row.verdict, row.counterexample)


def test_a_name_passed_inside_a_list_is_drawn_as_a_value():
    row = _row(cause_of, 'for triggers in {"form", "provenance", "defaults", "claims"}, '
                         'f([triggers, "dependency"]) == "this function changed"')
    assert row.verdict in ("proven", "holds"), (row.verdict, row.counterexample)


def test_a_name_passed_inside_a_list_is_still_falsified_when_wrong():
    row = _row(cause_of, 'for triggers in {"form", "seed"}, '
                         'f([triggers, "dependency"]) == "a callee changed"')
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert "form" in (row.counterexample or ""), row.counterexample


def test_a_mapping_parameter_bound_to_an_interval_is_still_falsified_when_wrong():
    row = _row(number_text, 'for value in [1, 3], f(value) == "other"')
    assert row.verdict == "falsified", (row.verdict, row.note)


def test_a_keyword_in_the_call_leaves_derive_to_decide():
    row = _row(shifted, "for x in [0, 1], f(x, k=1) == x + 1")
    assert row.verdict == "proven", (row.verdict, row.note)
    assert "does not model the pinned" not in (row.note or ""), row.note


def test_a_keyword_in_the_call_is_still_falsified_when_wrong():
    row = _row(shifted, "for x in [0, 1], f(x, k=1) == x + 2")
    assert row.verdict == "falsified", (row.verdict, row.note)


def test_an_absence_f_gives_with_the_parameter_present_is_not_its_own():
    """f returns None whenever before equals after, commit or no commit,
    so a None at commit = None says nothing about commit."""
    rec = check_conjectures(move, [
        claim("absent(f, commit) drops", name="commit_dropped"),
        claim('for before in {"proven", "holds"}, '
              'f(before, before, commit=None) == None', name="no_move")])
    row = next(p for p in rec if p.name == "commit_dropped")
    assert row.verdict != "falsified", (row.counterexample, row.note)
