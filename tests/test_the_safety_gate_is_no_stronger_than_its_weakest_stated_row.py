# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_missing_safe(f)` rolls up the policy each parameter follows. A
policy a stated row gives is only as sure as that row: a row that only
holds (sampled, not proven) leaves the gate at holds, never proven."""
import math

from mathema.conjecture import check_conjectures, claim

_ORDER = ("falsified", "unknown", "holds", "proven")


def narrow_spike(x: float, y: float) -> float:
    if 0.6180 < y < 0.6181:
        return 1.0
    return x + y


def plain_sum(x: float, y: float) -> float:
    return x + y


def _rows(fn):
    texts = ["missing(f, x) propagates", "missing(f, y) propagates",
             "is_missing_safe(f)"]
    rows = check_conjectures(fn, [claim(t) for t in texts])
    return [r for r in rows if not r.name.endswith("[float]")]


def _gate_and_stated(fn):
    rows = _rows(fn)
    gate = next(r for r in rows if r.statement.startswith("is_missing_safe"))
    stated = [r for r in rows if r is not gate
              and r.statement.startswith("missing(")]
    return gate, stated


def test_a_gate_over_rows_that_only_hold_is_not_proven():
    gate, stated = _gate_and_stated(narrow_spike)
    assert {r.verdict for r in stated} == {"holds"}, \
        [(r.statement, r.verdict) for r in stated]
    assert gate.verdict != "proven", (gate.verdict, gate.route, gate.sketch)


def test_the_gate_is_no_stronger_than_its_weakest_stated_row():
    for fn in (narrow_spike, plain_sum):
        gate, stated = _gate_and_stated(fn)
        weakest = min((r.verdict for r in stated), key=_ORDER.index)
        assert _ORDER.index(gate.verdict) <= _ORDER.index(weakest), \
            (fn.__name__, gate.verdict, [(r.statement, r.verdict) for r in stated])


def refuses_missing(x: float, y: float) -> float:
    if math.isnan(x):
        raise ValueError("x is missing")
    if math.isnan(y):
        raise ValueError("y is missing")
    return x + y


def test_a_gate_over_rows_proven_from_read_guards_stays_proven():
    (gate,) = [r for r in check_conjectures(refuses_missing,
                                            [claim("is_missing_safe(f)")])
               if not r.name.endswith("[float]")]
    assert gate.verdict == "proven", (gate.verdict, gate.route, gate.sketch)
