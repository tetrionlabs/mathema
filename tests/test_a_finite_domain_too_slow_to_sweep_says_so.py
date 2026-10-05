# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A finite domain too slow to sweep in the time budget is never left
with a bare sampled verdict: the exhaustive route runs every point where
a rounding step in the claim jumps, then a seeded sample, and the record
says how much of the domain it executed."""
import math

import mathema

_LAW = ("for periods in [1, 260] subset Z, active in [0, 260] subset Z, "
        "assuming active <= periods, "
        "f(active, periods) == ceil(100*active/periods)/100")


def slow_exposure(active: int, periods: int) -> float:
    days = [1 for d in range(periods) if d < active]
    sum(i * i for i in range(2000))
    return math.ceil(len(days) / periods * 100) / 100


def slow_exact(active: int, periods: int) -> float:
    days = [1 for d in range(periods) if d < active]
    sum(i * i for i in range(2000))
    return -((-100 * len(days)) // periods) / 100


def _main(fn):
    rec = mathema.check(fn, claims=[_LAW])
    (row,) = [p for p in rec.probes if p.name.startswith("f_active")
              and not p.name.endswith("]")]
    return row


def test_a_slow_function_is_falsified_at_a_rounding_jump(monkeypatch):
    from mathema import _brute_force
    monkeypatch.setattr(_brute_force, "_SWEEP_SECONDS", 0.5)
    row = _main(slow_exposure)
    assert row.verdict == "falsified", (row.verdict, row.note)
    head = row.counterexample.split(":")[0]
    pairs = dict(part.split(" = ") for part in head.split(", "))
    a, p = int(pairs["active"]), int(pairs["periods"])
    assert round(slow_exposure(a, p) * 100) != -((-100 * a) // p)


def test_a_slow_function_that_holds_says_the_sweep_was_skipped(monkeypatch):
    from mathema import _brute_force
    monkeypatch.setattr(_brute_force, "_SWEEP_SECONDS", 0.5)
    row = _main(slow_exact)
    assert row.verdict in ("holds", "unknown"), (row.verdict, row.note)
    assert "of 34190 points: every jump point of ceil(" in row.note, row.note
