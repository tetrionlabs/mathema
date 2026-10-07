# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Without z3, a claim the derive route leaves undecided past the
polynomial rungs says what would try next: the sketch ends "install
mathema[smt] to attempt a proof", and the probe note that quotes the
sketch carries it. With z3 the nlsat rung runs instead, so the hint is
never shown where the rung was available.
"""
import pytest

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.lexicon import double
from mathema.symbolic import try_prove

HINT = "install mathema[smt] to attempt a proof"
LAW = "for x in [0, 2], assuming x ~= 1, f(x) ~= 2"


def _derive(extensive: bool):
    cj = claim(LAW)
    return try_prove(double, analyze_source(double), cj.lhs, cj.rhs,
                     cj.relation, domain=cj.domain, extensive=extensive,
                     assumption=[("abs((x) - (1))", "<=", "ε")])


def test_the_sketch_ends_with_the_extra_to_install(monkeypatch):
    import mathema.symbolic._smt as smt
    monkeypatch.setattr(smt, "available", lambda: False)
    result = _derive(extensive=True)
    assert result.status == "undecided", (result.status, result.sketch)
    assert result.sketch.endswith(HINT), result.sketch
    # the hint belongs to the ladder: the fast attempt alone says nothing
    assert HINT not in (_derive(extensive=False).sketch or "")
    (p,) = check_conjectures(double, [claim(LAW, route="best")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert HINT in (p.note or ""), p.note


@pytest.mark.needs_smt
def test_the_rung_runs_instead_where_z3_is_installed():
    result = _derive(extensive=True)
    assert result.status == "disproven", (result.status, result.sketch)
    assert HINT not in (result.sketch or "")
