# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A hole in a container whose elements are dicts or records is refilled
with a dict or a record, so a function that keeps only those elements
shows that it read the slot: the fill comes out and the hole does not,
which is a drop. The element kind comes from the annotation
(`list[dict]`), from an `isinstance` check on the elements in the body,
or from the other elements of the drawn container. A function that
passes the hole through still propagates, and one that never reads the
slot is still indifferent to it."""
import math
from dataclasses import dataclass

from mathema._missing_policy import refill
from mathema.conjecture import check_conjectures, claim

NAN = math.nan


@dataclass
class Move:
    frm: str
    to: str
    weight: float


def keep_dicts(xs):
    return [t for t in xs if isinstance(t, dict)]


def keep_maps(xs: list[dict]) -> list[dict]:
    return [t for t in xs if hasattr(t, "keys")]


def keep_moves(xs):
    return [t for t in xs if isinstance(t, Move)]


def keep_all(xs):
    return list(xs)


def constant(xs: list[dict]) -> int:
    return 0


def drop_move(transitions: list, frm: str, to: str, *, at: str) -> list[dict]:
    out = [dict(t) for t in transitions or [] if isinstance(t, dict)]
    for i in range(len(out) - 1, -1, -1):
        t = out[i]
        if (t.get("from") == frm and t.get("to") == to and t.get("at") == at
                and not t.get("acknowledged") and not t.get("recovered")):
            del out[i]
            break
    return out


def _row(fn, *texts):
    rows = {p.statement: p for p in check_conjectures(fn, [claim(t) for t in texts])}
    return rows[texts[-1]]


def test_an_isinstance_check_on_the_elements_makes_the_fill_a_dict():
    row = _row(keep_dicts, "missing(f, xs) drops")
    assert row.verdict == "holds", (row.verdict, row.note)


def test_a_list_of_dicts_annotation_makes_the_fill_a_dict():
    row = _row(keep_maps, "missing(f, xs) drops")
    assert row.verdict == "holds", (row.verdict, row.note)


def test_an_isinstance_check_on_a_record_class_makes_the_fill_a_record():
    row = _row(keep_moves, "missing(f, xs) drops")
    assert row.verdict == "holds", (row.verdict, row.note)


def test_a_function_that_skips_entries_that_are_not_dicts_drops_the_hole():
    row = _row(drop_move, "missing(f, transitions) drops")
    assert row.verdict == "holds", (row.verdict, row.note)


def test_a_dict_beside_the_hole_is_the_fill():
    def call_at(point):
        try:
            return keep_maps(**point), None
        except Exception as exc:
            return None, type(exc).__name__
    point = {"xs": [{"a": 1.0}, NAN]}
    out = refill(call_at, point, keep_maps(**point), None, {"xs": 0.5})
    assert [b for *_r, b in out] == ["drops"]


def test_a_pass_through_still_propagates():
    bound = "for xs in [0, 1]^n, len(f(xs)) >= 0"
    assert _row(keep_all, bound, "missing(f, xs) propagates").verdict == "holds"
    assert _row(keep_all, bound, "missing(f, xs) drops").verdict == "falsified"


def test_a_function_that_never_reads_the_slot_stays_indifferent():
    assert _row(constant, "missing(f, xs) drops").verdict == "unknown"
    row = _row(constant, "missing(f, xs) propagates")
    assert row.verdict == "falsified"
    assert row.note.startswith("stated; f drops instead: a null slot in, 0 out")
