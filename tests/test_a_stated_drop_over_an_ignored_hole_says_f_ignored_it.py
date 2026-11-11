# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A stated `drops` row whose only calls at the hole left f indifferent
to it (no fill of the slot changes the value) is unknown, and its
reason says that calls reached the hole and f ignored it, never that
no call reached it. A function that filters the hole out of records
is not indifferent: refilled with a record, the record comes through,
so the slot is read and the hole is dropped."""
from mathema import check


def no_moves(moves: list, k: str) -> list:
    return []


def keep_other_moves(moves: list, k: str) -> list:
    return [dict(m) for m in moves if isinstance(m, dict) and m.get("k") != k]


def _stated_drop(rec):
    (row,) = [p for p in rec.probes if p.statement.startswith("missing(f, moves)")
              and (p.meta or {}).get("mathema.policy", {}).get("source") == "stated"]
    return row


def test_the_reason_names_the_ignored_hole():
    rec = check(no_moves, claims=[
        'for k in {"a", "b"}, f([None, {"k": "z"}], k) == []',
        "missing(f, moves) drops"])
    row = _stated_drop(rec)
    assert row.verdict == "unknown", (row.verdict, row.note)
    assert "no call reached" not in row.note, row.note
    assert "ignores" in row.note and "moves" in row.note, row.note


def test_a_filter_over_records_drops_the_hole():
    rec = check(keep_other_moves, claims=[
        'for k in {"a", "b"}, f([None, {"k": "z"}], k) == [{"k": "z"}]',
        "missing(f, moves) drops"])
    row = _stated_drop(rec)
    assert row.verdict == "holds", (row.verdict, row.note)
