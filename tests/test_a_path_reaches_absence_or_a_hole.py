# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a path reaches when the value is not there: where the `None`
sits decides the kind. A field, attribute or key holding `None` is
absent, member `null`; a key or attribute not there, an index past the
end, or a step below an absent object is absent, member `unset`; an
element of a list holding `None` is a hole, member `null`, and a step
below it reaches that hole; NaN is a hole wherever it sits."""
import math
from dataclasses import dataclass, field
from typing import Optional

import pytest

from mathema import check_conjectures, claim
from mathema.domain import (
    ABSENT_NULL, ABSENT_UNSET, domain_contains, member, member_of, parse_binding,
    path_bindings_hold, path_steps, path_values, render_domain,
)


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


def kind_and_member(leaf):
    """`(kind, member)` of what a path reached, or None for a value."""
    if leaf == ABSENT_NULL or leaf == ABSENT_UNSET:
        return ("absent", leaf.member)
    word = member_of(leaf)
    return ("missing", word) if word is not None else None


CASES = [
    (1, Order(note=None), ".note", [("absent", "null")]),
    (2, Order(address=None), ".address.zip", [("absent", "unset")]),
    (3, Order(address=Address(zip=None)), ".address.zip", [("absent", "null")]),
    (4, Order(lines=[]), ".lines[0].qty", [("absent", "unset")]),
    (5, Order(lines=[Line(), None]), ".lines[*].qty", [None, ("missing", "null")]),
    (6, Order(lines=[Line(math.nan)]), ".lines[*].qty", [("missing", "nan")]),
    (7, {}, ".note", [("absent", "unset")]),
    (8, {"note": None}, ".note", [("absent", "null")]),
]


@pytest.mark.parametrize("case, value, path, expected", CASES, ids=[str(c[0]) for c in CASES])
def test_the_kind_and_member_a_path_reaches(case, value, path, expected):
    leaves = path_values(value, path_steps(path))
    assert [kind_and_member(v) for v in leaves] == expected


def test_the_value_a_path_reaches_is_the_value_itself():
    assert path_values(Order(lines=[Line(2.0), None]), path_steps(".lines[*].qty"))[0] == 2.0


def _bound(text):
    return parse_binding(f'd.note in {{"x", "y", None}} {text}')[1]


def test_excluding_unset_keeps_a_key_holding_none():
    bindings = {"d.note": _bound("\\ {unset}")}
    assert path_bindings_hold({"note": None}, "d", bindings)
    assert not path_bindings_hold({}, "d", bindings)


def test_excluding_null_keeps_a_key_left_out():
    bindings = {"d.note": _bound("\\ {null}")}
    assert path_bindings_hold({}, "d", bindings)
    assert not path_bindings_hold({"note": None}, "d", bindings)


def test_excluding_absent_refuses_both_members():
    bindings = {"d.note": _bound("\\ {absent}")}
    assert not path_bindings_hold({}, "d", bindings)
    assert not path_bindings_hold({"note": None}, "d", bindings)
    assert path_bindings_hold({"note": "x"}, "d", bindings)


@pytest.mark.parametrize("case, value, path, expected", CASES, ids=[str(c[0]) for c in CASES])
def test_excluding_missing_refuses_only_the_holes(case, value, path, expected):
    bound = parse_binding(f"o{path} in R \\ {{missing}}")[1]
    reached = [leaf for leaf in path_values(value, path_steps(path))
               if kind_and_member(leaf) is not None]
    holds = all(domain_contains(leaf, bound) for leaf in reached)
    assert holds == (case not in (5, 6)), (case, reached)


def test_null_on_an_element_path_is_a_hole():
    (_, bound) = parse_binding("o.lines[*] in R \\ {null}")
    assert member("null") in bound.excluded
    (_, bound) = parse_binding('o.note in {"x"} | {None} \\ {null}')
    assert ABSENT_NULL in bound.excluded


@pytest.mark.parametrize("text", ["\\ {null}", "\\ {unset}", "| {null}"])
def test_an_absence_member_renders_and_reads_back(text):
    (name, bound) = parse_binding(f'd.note in {{"x", "y"}} | {{None}} {text}')
    for ascii_mode in (True, False):
        shown = render_domain(bound, ascii_mode=ascii_mode, words=True)
        assert parse_binding(f"d.note in {shown}")[1] == bound, shown


def test_an_absence_member_survives_the_record():
    from mathema.domain import _json_value, _value_from_json
    for s in (ABSENT_NULL, ABSENT_UNSET, member("null")):
        assert _value_from_json(_json_value(s)) == s
    # a record written before absence had members reads `null` as the hole
    assert _value_from_json({"sentinel": "null"}) == member("null")


def note_label(d: dict) -> str:
    note = d.get("note")
    return "-" if note is None else note.upper()


def note_upper(d: dict) -> str:
    return d["note"].upper()


def test_a_dict_key_is_drawn_left_out_and_holding_none():
    [p] = check_conjectures(note_label, [claim(
        'for d.note in {"a", "b"} | {None}, f(d) != "-"', route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    words = p.counterexample
    assert "d.note unset" in words or "d.note = null (absent)" in words, words


@pytest.mark.parametrize("member_word, witness, shown", [
    ("unset", "d.note unset", "d = {"),
    ("null", "d.note = null (absent)", "'note': None")])
def test_each_member_of_absence_is_drawn_and_named(member_word, witness, shown):
    other = "null" if member_word == "unset" else "unset"
    [p] = check_conjectures(note_label, [claim(
        f'for d.note in {{"a", "b"}} | {{None}} \\ {{{other}}}, f(d) != "-"',
        route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert witness in p.counterexample, p.counterexample
    assert shown in p.counterexample, p.counterexample


def test_a_raise_at_a_key_left_out_is_classified_and_said_by_its_member():
    """A raise where the path reached no value is a raise at a missing
    input: recorded under the path and member, never a counterexample."""
    [p] = check_conjectures(note_upper, [claim(
        'for d.note in {"a", "b"} | {None} \\ {null}, len(f(d)) == 1', route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "at d.note, a key left out, f raised KeyError" in p.note, p.note


def test_a_binding_that_admits_no_absence_draws_the_key_present():
    [p] = check_conjectures(note_upper, [claim(
        'for d.note in {"a", "b"}, len(f(d)) == 1', route="probe")])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note, p.counterexample)
