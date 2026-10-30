# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Within one check an exact decision at a point is kept for the claim
that took it, by its relation, tolerance and negation as well as its
sides, so claims sharing their sides each get their own verdict. (3x)/3
is x exactly, while the float run gives 0.10000000000000002 at x = 0.1."""
import mathema.conjecture as conjecture
from mathema.conjecture import check_conjectures, claim


def thirds(x: float) -> float:
    return (x * 3) / 3


def test_claims_with_the_same_sides_keep_their_own_exact_decisions(
        monkeypatch):
    keys = []
    keyed = conjecture._exact_decision_key

    def recording(*args, **kwargs):
        key = keyed(*args, **kwargs)
        keys.append(key)
        return key
    monkeypatch.setattr(conjecture, "_exact_decision_key", recording)
    rows = check_conjectures(thirds, [
        claim("for x in {0.1, 0.7}, f(x) == x", route="probe"),
        claim("for x in {0.1, 0.7}, f(x) < x", route="probe"),
        claim("for x in {0.1, 0.7}, f(x) <= x", route="probe")])
    verdicts = [p.verdict for p in rows]
    assert verdicts == ["holds", "falsified", "holds"], [
        (p.verdict, p.counterexample, p.note) for p in rows]
    relations = {key[1] for key in keys if key is not None}
    assert {"==", "<", "<="} <= relations, keys
