# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The cross-route attempt log: a best/derive claim that falls through
records every route tried and why each did or didn't decide, in
`meta["mathema.routes_attempted"]`; the note leads with the deciding
route's own sentence."""
from mathema.conjecture import claim, check_conjectures


def branchy(x):
    if x >= 0:
        return x + 1.0
    return 1.0 - x


def sq(x):
    return x * x


def test_best_over_unliftable_lists_derive_and_probe(monkeypatch):
    # the attempt-log FORMAT pin: with the optional nlsat rung masked,
    # the piecewise sign question stays undecided and the note must
    # list what each route did
    import mathema.symbolic._smt as smt
    monkeypatch.setattr(smt, "available", lambda: False)
    (p,) = check_conjectures(branchy, [claim("f(x) >= 1", route="best")])
    assert p.verdict == "holds"
    trail = p.meta["mathema.routes_attempted"]
    assert "routes attempted" in trail
    assert "derive: undecided" in trail   # piecewise lifted, sign unsettled
    assert "probe: holds" in trail
    assert "the probe decided it" in p.note and "routes attempted" not in p.note


def test_best_escalates_to_an_nlsat_proof_when_available():
    import pytest
    pytest.importorskip("z3")
    # the same claim, extra installed: the attained minimum at x = 0 is
    # exactly what nlsat decides and refinement cannot, proven, and
    # no attempt log because nothing stayed open
    (p,) = check_conjectures(branchy, [claim("f(x) >= 1", route="best")])
    assert p.verdict == "proven"
    assert "nlsat" in (p.sketch or "")


def test_derive_proof_leaves_no_probe_line():
    (p,) = check_conjectures(sq, [claim("d(f(x), x) == 2*x", route="best")])
    assert p.verdict == "proven"
    assert "routes attempted" not in (p.note or "")
    assert "mathema.routes_attempted" not in (p.meta or {})
