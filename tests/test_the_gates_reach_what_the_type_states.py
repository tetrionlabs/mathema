# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The absence and missing gates reach what a parameter's type states,
without a claim binding the path: a record's optional fields and the
elements of its list fields, a TypedDict's keys marked NotRequired or
holding an Optional value. A plain dict states nothing about its keys,
so the gate reaches them only through a claim, and says so."""
from dataclasses import dataclass, field
from typing import Optional, TypedDict

try:
    from typing import NotRequired
except ImportError:  # pragma: no cover
    from typing_extensions import NotRequired

from mathema.conjecture import check_conjectures, claim


@dataclass
class Line:
    qty: float
    price: float


@dataclass
class Order:
    lines: list[Line] = field(default_factory=list)


def total_qty(o: Order) -> float:
    return sum(line.qty for line in o.lines)


class Trade(TypedDict):
    side: str
    memo: NotRequired[str]
    venue: Optional[str]


def memo_len(t: Trade) -> int:
    return len(t["memo"])


def venue_len(t: Trade) -> int:
    return len(t["venue"])


def note_of(d: dict) -> str:
    return d["note"].strip()


def _gate(fn, text):
    return check_conjectures(fn, [claim(text)])[-1]


def test_the_missing_gate_draws_a_hole_inside_a_list_of_records():
    row = _gate(total_qty, "is_missing_safe(f)")
    assert "o.lines[*].qty" in row.note, row.note
    (entry,) = row.meta["mathema.gate"]["parameters"]["o.lines[*].qty"]
    assert (entry["member"], entry["behaviour"]) == ("nan", "propagates")


def test_the_absent_gate_leaves_a_not_required_key_out():
    row = _gate(memo_len, "is_absent_safe(f)")
    assert row.verdict == "falsified", row.note
    assert row.counterexample == "t.memo unset: f raised KeyError"


def test_the_absent_gate_holds_none_at_an_optional_key():
    row = _gate(venue_len, "is_absent_safe(f)")
    assert row.verdict == "falsified", row.note
    assert row.counterexample == "t.venue = null (absent): f raised TypeError"


def test_a_plain_dict_is_reached_only_through_a_claim_and_says_so():
    row = _gate(note_of, "is_absent_safe(f)")
    assert ("d is a plain dict, which states nothing about its keys, so the gate "
            "reaches a key only through a claim that binds it") in row.note, row.note
