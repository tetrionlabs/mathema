# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function may return a nan in a slot the claim never reads: the
first difference of a series has no value, and a claim about the
differences slices it away. The computation line judges what the claim
reads, so such a nan is no failure of the computation, on the probe's
own draws and on the companion sweep alike."""
import math

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.records import Probe

pytest.importorskip("numpy")

_LAW = ("for a in [-1e150, 1e150]^n, assuming dim(a) >= 2, "
        "f(a)[1:] ~= a[1:] - a[:-1]")


def lagged(a: list) -> list:
    """The differences between neighbours; position 0 has none."""
    return [math.nan] + [a[i] - a[i - 1] for i in range(1, len(a))]


def _derive_undecided(ctx, fn, facts, extensive):
    ctx.derive_undecided = Probe(
        ctx.cj.name, ctx.statement, "unknown", route="derive",
        note=f"{ctx.note}; derive could not decide it",
        meta={"mathema.derive_status": "undecided", "mathema.timeout": "fast"})
    return None


def test_the_probe_holds_the_differences_claim():
    (p,) = check_conjectures(lagged, [claim(_LAW, route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_the_companion_sweep_holds_it_too(monkeypatch):
    # derive cut short: the probe stands in and the computation line runs
    # the corners of the domain, where f's nan at position 0 is sliced
    # away by the claim as everywhere else; a companion that held is not
    # shown beside the stand-in, so the record is the one line
    monkeypatch.setattr(mathema.conjecture, "_adjudicate_derive", _derive_undecided)
    rows = check_conjectures(lagged, [claim(_LAW)], float_companions=True)
    assert [p.verdict for p in rows] == ["holds"], \
        [(p.name, p.verdict, p.counterexample, p.note) for p in rows]


def test_a_nan_the_claim_reads_is_still_a_failure(monkeypatch):
    # the same function under a claim that reads position 0
    monkeypatch.setattr(mathema.conjecture, "_adjudicate_derive", _derive_undecided)
    rows = check_conjectures(
        lagged, [claim("for a in [-1e150, 1e150]^n, assuming dim(a) >= 2, "
                       "f(a)[0] == 0")], float_companions=True)
    assert "falsified" in [p.verdict for p in rows], \
        [(p.name, p.verdict, p.counterexample) for p in rows]
