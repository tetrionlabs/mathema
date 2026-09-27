# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where the resolved pseudo-infinity bounds an unbounded numeric
direction, a computation row shows it as a `let`: the displayed claim
and the record's `condition` begin `let |inf| be <value>, ...`. The
canonical statement never carries it, a bounded claim shows nothing,
and the level the value came from lives only in
`meta["mathema.pseudo_infinity"]["source"]`."""
import pytest

import mathema
from mathema.conjecture import claim


def sq(x: float) -> float:
    return x * x


def _rows(law, name="law", **kw):
    rec = mathema.check(sq, claims=[claim(law, name=name, **kw)])
    return rec, {p.name: p for p in rec.probes}


@pytest.mark.needs_full_proof_budget
def test_the_companion_condition_begins_with_the_let(monkeypatch):
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e6")
    rec, rows = _rows("for x in R, f(x) >= 0")
    comp = rows["law[float]"]
    assert comp.condition.startswith("let |inf| be 1e+06, for x in R"), \
        comp.condition
    assert "MATHEMA_PSEUDO_INFINITY" not in comp.condition
    assert comp.meta["mathema.pseudo_infinity"]["source"] == "environment"
    (row,) = [c for c in rec.to_spec()["claims"] if c["name"] == "law[float]"]
    assert row["condition"].startswith("let |inf| be 1e+06, "), row
    assert "law[float]: let |inf| be 1e+06, for x in R" in repr(rec), \
        repr(rec)


@pytest.mark.needs_full_proof_budget
def test_the_proof_keeps_its_own_quantifier(monkeypatch):
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e6")
    _rec, rows = _rows("for x in R, f(x) >= 0")
    assert rows["law"].verdict == "proven"
    assert "|inf|" not in (rows["law"].condition or "")


def test_a_bare_probe_claim_names_its_unbounded_direction(monkeypatch):
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e6")
    _rec, rows = _rows("f(x) >= 0", route="probe")
    assert rows["law"].condition == "let |inf| be 1e+06, for x in R", \
        rows["law"].condition


def test_the_canonical_statement_is_unchanged(monkeypatch):
    _rec, before = _rows("for x in R, f(x) >= 0", route="probe")
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e6")
    _rec, after = _rows("for x in R, f(x) >= 0", route="probe")
    assert after["law"].statement == before["law"].statement
    assert "|inf|" not in after["law"].statement


def test_a_bounded_claim_shows_nothing(monkeypatch):
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e6")
    rec, rows = _rows("for x in [-3, 3], f(x) >= 0", route="probe")
    assert "|inf|" not in (rows["law"].condition or "")
    assert "|inf|" not in repr(rec)


@pytest.mark.needs_full_proof_budget
def test_the_function_level_value_shows_the_same_way():
    rec = mathema.check(sq, claims=[claim("for x in R, f(x) >= 0",
                                          name="law")],
                        pseudo_infinity=1e6)
    comp = {p.name: p for p in rec.probes}["law[float]"]
    assert comp.condition.startswith("let |inf| be 1e+06, "), comp.condition
    assert "function level" not in comp.condition
    assert "function level" not in (comp.note or "")


@pytest.mark.needs_full_proof_budget
def test_a_claim_level_binding_is_not_repeated():
    rec, rows = _rows("let |inf| be 1e6, for x in R, f(x) >= 0")
    comp = rows["law[float]"]
    shown = [ln for ln in repr(rec).splitlines() if "law[float]" in ln]
    assert shown and shown[0].count("|inf|") == 1, shown
    assert (comp.condition or "").count("|inf|") <= 1
    assert "(claim)" not in (comp.note or "")


def test_notes_carry_the_value_without_its_level(monkeypatch):
    monkeypatch.setenv("MATHEMA_PSEUDO_INFINITY", "1e6")
    _rec, rows = _rows("for x in [0, oo), f(x) >= 0", route="probe")
    note = rows["law"].note or ""
    assert "1e+06" in note, note
    assert "MATHEMA_PSEUDO_INFINITY" not in note, note
