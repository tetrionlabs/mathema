# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The derive route proves a claim about a guarded function only over
inputs the guard admits. An `enforce_domain` guard that is a union of
intervals is read like a single interval: a claim over a region the
union leaves out, or over one that crosses a gap, is decided by the
executed guard, which refuses the call there."""
from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim

_UNION = claim("for x in [-1, -0.5] ∪ [0.5, 3], f(x) >= 0").domain["x"]


@enforce_domain(domain={"x": _UNION})
def union_guard(x: float) -> float:
    return x


def _row(text):
    (p,) = check_conjectures(union_guard, [claim(text)])
    return p


def test_a_region_the_union_leaves_out_is_never_proven():
    p = _row("for x in [0, 0.25], f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert "DomainError" in p.counterexample


def test_a_region_crossing_the_gap_is_never_proven():
    p = _row("for x in [-1, 1], f(x) == x")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)


def test_a_region_inside_one_piece_is_still_proven():
    p = _row("for x in [0.5, 2], f(x) == x")
    assert (p.verdict, p.route) == ("proven", "derive"), (p.verdict, p.note)
