# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""In claim text over a matrix, `|A|` is the determinant of `A`, through
every entry point: `check_conjectures` and `mathema.check` read
`|A @ B| == |A| * |B|` alike, as `det(A @ B) == det(A) * det(B)`,
which is true and proven, never as the elementwise absolute value,
where it is false.
"""
from __future__ import annotations

import pytest

import mathema
from mathema.claims import check_conjectures, claim
from mathema.types import Mat

_LAW = "|A @ B| == |A| * |B|"


def two(A: Mat("n", "n"), B: Mat("n", "n")):
    return A


def _from_check(law):
    r = mathema.check(two, claims=[law])
    (p,) = [p for p in r.probes if p.statement and "B" in p.statement
            and "[float" not in (p.name or "")]
    return p


@pytest.mark.needs_full_proof_budget
def test_check_reads_bars_over_a_matrix_as_its_determinant():
    p = _from_check(_LAW)
    assert p.statement == "det(A @ B) = det(A)*det(B)", p.statement
    assert p.verdict == "proven", (p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
def test_both_entry_points_agree():
    (direct,) = check_conjectures(two, [claim(_LAW)])
    p = _from_check(_LAW)
    assert (direct.statement, direct.verdict) == (p.statement, p.verdict)
