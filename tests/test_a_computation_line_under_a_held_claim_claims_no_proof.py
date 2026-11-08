# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `[float]` line spawned under a claim the probe decided because derive
could not (the claim holds, it is not proven) states what stands behind
it: the probe's draws, not a proof. Its sketch never calls the claim
proven, and its stratum names no sound mathematics, which only a proof
of the same claim establishes. Under a proven claim the line reads as it
always has."""
import math

from mathema.conjecture import check_conjectures, claim


def nudged(c: float) -> float:
    return (1.0 + c) - 1.0 + math.floor(c)


def nudged_flat(c: float, n: float) -> float:
    return (n + c) - n


def _rows(fn, law):
    probes = check_conjectures(fn, [claim(law, name="law")],
                               float_companions=True)
    return {p.name: p for p in probes}


def test_the_line_under_a_held_claim_does_not_call_it_proven():
    rows = _rows(nudged, "for c in (0, 1), f(c) > 0")
    assert rows["law"].verdict == "holds", rows["law"]
    line = rows["law[float]"]
    assert line.verdict == "falsified", line
    assert "proven" not in (line.sketch or ""), line.sketch
    assert "law holds on the probe's draws" in (line.sketch or ""), \
        line.sketch
    assert "c = 4.94066e-324" in (line.sketch or ""), line.sketch
    assert "mathematics" not in (line.stratum or {}), line.stratum
    assert (line.stratum or {}).get("blame") == "implementation", \
        line.stratum


def test_the_line_under_a_proven_claim_keeps_the_proof():
    rows = _rows(nudged_flat, "for c in (0, 1), n in [1, 100], f(c, n) > 0")
    assert rows["law"].verdict == "proven", rows["law"]
    line = rows["law[float]"]
    assert line.verdict == "falsified", line
    assert (line.sketch or "").startswith("law is mathematically proven, "
                                          "but its computation fails at"), \
        line.sketch
    assert line.stratum["mathematics"] == "sound", line.stratum
