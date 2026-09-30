# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A field's or key's no-value is a missing input as a parameter's is: a
raise there is classified, never a counterexample to a value claim, and
filed under its path and member (a key holding `None` is `null`, a key
left out `unset`, a `None` element under `[*]` the hole `null`). The
record says what f did there in a sentence, a policy row states it by
path (`absent(f, d.note, unset) drops`), and `is_absent_safe(f)` reaches
into fields and keys."""
import math
from dataclasses import dataclass, field
from typing import Optional

import pytest

from mathema import check, check_conjectures, claim
from mathema._missing_policy import keys_of
from mathema._missing_words import path_said


@dataclass
class Address:
    zip: Optional[str] = "12345"


@dataclass
class Line:
    qty: float = 1.0


@dataclass
class Order:
    note: Optional[str] = "leave at the door"
    address: Optional[Address] = None
    lines: list = field(default_factory=list)


#: the eight cases of the handoff: the value, the path a binding names,
#: the key it is filed under, and the sentence the record says
CASES = [
    (Order(note=None), "o.note", ("o.note", "absent", "null"),
     "at o.note = null (absent) f raised TypeError"),
    (Order(address=None), "o.address.zip", ("o.address.zip", "absent", "unset"),
     "at o.address.zip, below an absent o.address, f raised TypeError"),
    (Order(address=Address(zip=None)), "o.address.zip",
     ("o.address.zip", "absent", "null"),
     "at o.address.zip = null (absent) f raised TypeError"),
    (Order(lines=[]), "o.lines[0].qty", ("o.lines[0].qty", "absent", "unset"),
     "at o.lines[0].qty, an index past the end, f raised TypeError"),
    (Order(lines=[Line(), None]), "o.lines[*].qty", ("o.lines[*].qty", "missing", "null"),
     "at o.lines[1] = null (hole) f raised TypeError"),
    (Order(lines=[Line(math.nan)]), "o.lines[*].qty", ("o.lines[*].qty", "missing", "nan"),
     "at o.lines[0].qty = nan f raised TypeError"),
    ({}, "o.note", ("o.note", "absent", "unset"),
     "at o.note, a key left out, f raised TypeError"),
    ({"note": None}, "o.note", ("o.note", "absent", "null"),
     "at o.note = null (absent) f raised TypeError"),
]


@pytest.mark.parametrize("value, path, key, sentence", CASES,
                         ids=[str(i + 1) for i in range(len(CASES))])
def test_each_path_case_is_filed_under_its_path_and_member(value, path, key, sentence):
    assert key in keys_of({"o": value}, {"o": [path]})
    assert path_said(path, key[2], {"o": value}, raised="TypeError") == sentence


def test_a_record_field_holding_none_is_filed_by_its_path():
    """With no binding naming the field, a `None` field is still the
    field's absence, not the parameter's."""
    keys = keys_of({"o": Order(note=None)})
    assert ("o.note", "absent", "null") in keys
    assert not any(k[0] == "o" for k in keys)


def note_upper(d: dict) -> str:
    return d["note"].upper()


def note_or_dash(d: dict) -> str:
    """A key left out reads as a dash; a key holding None raises."""
    if "note" not in d:
        return "-"
    return d["note"].upper()


def _rows(fn, *texts):
    rec = check(fn, claims=[claim(t, name=f"c{i}") for i, t in enumerate(texts)])
    return {p.name: p for p in rec.probes}


@pytest.mark.parametrize("admitted", ["| {None}", "| {None} \\ {null}",
                                      "| {None} \\ {unset}"])
def test_a_raise_at_an_admitted_absence_along_a_path_is_classified(admitted):
    rows = _rows(note_upper, f'for d.note in {{"a", "b"}} {admitted}, len(f(d)) == 1')
    assert rows["c0"].verdict in ("holds", "proven"), (rows["c0"].verdict, rows["c0"].note)


def test_the_record_says_what_f_did_at_each_member():
    rows = _rows(note_upper, 'for d.note in {"a", "b"} | {None}, len(f(d)) == 1')
    note = rows["c0"].note
    assert "at d.note, a key left out, f raised KeyError" in note, note
    assert "at d.note = null (absent) f raised AttributeError" in note, note


def test_an_unaccounted_raise_at_a_path_is_its_own_falsified_row():
    rows = _rows(note_upper, 'for d.note in {"a", "b"} | {None} \\ {null}, len(f(d)) == 1')
    row = rows["absent[d.note]"]
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.counterexample == "d.note unset: f raised KeyError"
    assert "state `absent(f, d.note) raises(KeyError)`" in row.note, row.note


def test_members_that_behave_differently_get_a_row_each():
    rows = _rows(note_or_dash, 'for d.note in {"a", "b"} | {None}, f(d) != ""')
    assert rows["absent[d.note, unset]"].verdict == "holds", rows["absent[d.note, unset]"].note
    assert rows["absent[d.note, unset]"].statement == "absent(f, d.note, unset) drops"
    assert rows["absent[d.note, null]"].verdict == "falsified"
    assert rows["absent[d.note, null]"].counterexample == \
        "d.note = null (absent): f raised AttributeError"


def test_a_stated_path_row_is_confirmed():
    rows = _rows(note_upper, 'for d.note in {"a", "b"} | {None}, len(f(d)) == 1',
                 "absent(f, d.note, unset) raises(KeyError)",
                 "absent(f, d.note, null) raises(AttributeError)")
    assert rows["c1"].verdict == "holds", (rows["c1"].verdict, rows["c1"].note)
    assert rows["c2"].verdict == "holds", (rows["c2"].verdict, rows["c2"].note)
    assert "absent[d.note]" not in rows


def test_a_stated_path_row_is_contradicted():
    rows = _rows(note_upper, 'for d.note in {"a", "b"} | {None}, len(f(d)) == 1',
                 "absent(f, d.note, unset) drops")
    row = rows["c1"]
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.counterexample == "d.note unset: f raised KeyError"
    assert "state `absent(f, d.note, unset) raises(KeyError)`" in row.note, row.note


def test_a_path_policy_reads_back_in_every_form():
    from mathema.policy import parse_policy, policy_text
    for text in ("absent(f, o.note) raises(TypeError)", "absent(f, d.note, unset) drops",
                 "missing(f, o.lines[*].qty) propagates"):
        assert policy_text(parse_policy(text)) == text
        assert claim(text).relation == "policy"


# --- the gate reaches into fields ------------------------------------------

@dataclass
class Parcel:
    label: Optional[str] = "fragile"
    weight: float = 1.0


def label_len(p: Parcel) -> int:
    return len(p.label)


def test_the_absence_gate_falsifies_on_an_unstated_raise_at_a_field():
    [row] = check_conjectures(label_len, [claim("is_absent_safe(f)")])
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.counterexample == "p.label = null (absent): f raised TypeError"
    assert "p.label (field): null raises TypeError, and no claim says it may" in row.note


def test_the_absence_gate_is_proven_once_the_field_row_is_stated():
    rows = check_conjectures(label_len, [claim("absent(f, p.label) raises(TypeError)"),
                                         claim("is_absent_safe(f)")])
    stated = next(r for r in rows if r.statement.startswith("absent(f, p.label)"))
    assert stated.verdict == "holds", (stated.verdict, stated.note)
    gate = next(r for r in rows if r.statement == "is_absent_safe(f)")
    assert gate.verdict == "proven", (gate.verdict, gate.note)
    assert "p.label (field): null raises TypeError, stated" in gate.note


# --- --write writes a path row by its name ---------------------------------

_MOD = (
    "# SPDX-License-Identifier: BUSL-1.1\n# Copyright 2026 Tetrion Ltd\n\n"
    "def note_or_dash(d: dict) -> str:\n"
    "    if \"note\" not in d:\n        return \"-\"\n"
    "    if d[\"note\"] is None:\n        return \"\"\n"
    "    return d[\"note\"].upper()\n")
_CLAIMS = (
    "slips.note_or_dash:\n  claims:\n    - name: short\n"
    "      statement: 'for d.note in {\"a\", \"b\"} | {None}, len(f(d)) <= 1'\n")


def test_write_writes_a_path_row_by_its_name(tmp_path, monkeypatch, capsys):
    import yaml
    (tmp_path / "slips.py").write_text(_MOD)
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "s.claims.yaml").write_text(_CLAIMS)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    from mathema.cli import main
    main(["claims", "slips.note_or_dash", "--root", str(tmp_path), "--write"])
    out = capsys.readouterr().out
    assert "absent[d.note]" in out, out
    written = yaml.safe_load((tmp_path / "claims" / "policies.claims.yaml").read_text())
    [row] = written["slips.note_or_dash"]["claims"]
    assert (row["name"], row["statement"]) == ("absent[d.note]", "absent(f, d.note) drops")
