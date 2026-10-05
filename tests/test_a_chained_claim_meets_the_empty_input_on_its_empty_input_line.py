# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A chained comparison over sequences (`0 <= f(xs) <= 1`) is, like any
value claim, its mathematics over non-empty inputs plus its empty-input
line. Its links are adjudicated over non-empty inputs only, so the
empty list never appears as a link's own witness: the claim's finding
over non-empty inputs is kept, and the empty list reaches the claim only
through `is_empty_safe`, exactly as for a single comparison."""
from statistics import fmean

from mathema.claims import check_conjectures, claim


def average(xs: list[float]) -> float:
    return fmean(xs)


def test_a_chain_keeps_its_mathematics_and_takes_the_line_witness():
    probes = check_conjectures(
        average, [claim("for xs in [0, 1]^n, 0 <= f(xs) <= 1")],
        float_companions=True)
    head = probes[0]
    line = next(p for p in probes if p.name == "is_empty_safe[xs]")
    assert line.verdict == "falsified"
    assert head.counterexample == line.counterexample, head.counterexample
    found = (head.meta or {}).get("mathema.mathematics") or {}
    assert found.get("verdict") in ("proven", "holds"), (head.meta, head.note)


def test_a_single_comparison_reads_the_same():
    probes = check_conjectures(
        average, [claim("for xs in [0, 1]^n, f(xs) <= 1")],
        float_companions=True)
    head = probes[0]
    line = next(p for p in probes if p.name == "is_empty_safe[xs]")
    assert head.counterexample == line.counterexample
    assert (head.meta or {}).get("mathema.mathematics", {}).get("verdict") \
        in ("proven", "holds")
