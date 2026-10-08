# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A chained premise is the conjunction of its links.

`assuming a < 0 < b` says `a < 0` and `0 < b`, exactly as a chained
statement does. Read as one relation split at its first operator it
becomes `a < (0 < b)`, a comparison with a boolean that admits almost
every point, so a claim true on the premise region is falsified by a
point outside it. A premise that does not read as plain relations is
refused, never evaluated as a malformed filter.
"""
import pytest

from mathema.claims import check_conjectures, claim


def gap(a, b):
    return b - a


def smallest(r):
    return min(r)


def _one(fn, law, route=None, **kw):
    kw = dict(kw)
    if route:
        kw["route"] = route
    return check_conjectures(fn, [claim(law, **kw)])[0]


@pytest.mark.parametrize("route", ["probe", "derive"])
def test_a_chained_premise_rejects_a_point_outside_either_link(route):
    # b - a > 0 holds wherever a < 0 < b; the point a = -1, b = -1
    # satisfies `a < (0 < b)` and gives 0
    p = _one(gap, "for a in [-2, 2], b in [-2, 2], "
                  "assuming a < 0 < b, f(a, b) > 0", route=route)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample)


@pytest.mark.parametrize("route", ["probe", "derive"])
def test_a_chain_gives_the_verdicts_of_its_links_written_apart(route):
    for law_tail in ("f(a, b) > 0", "f(a, b) > 1", "f(a, b) >= 0"):
        chained = _one(gap, f"for a in [-2, 2], b in [-2, 2], "
                            f"assuming a < 0 < b, {law_tail}", route=route)
        apart = _one(gap, f"for a in [-2, 2], b in [-2, 2], "
                          f"assuming a < 0, assuming 0 < b, {law_tail}",
                     route=route)
        assert (chained.verdict, chained.route, chained.counterexample) \
            == (apart.verdict, apart.route, apart.counterexample), law_tail


def test_a_counterexample_always_satisfies_a_chained_sequence_premise():
    p = _one(smallest, "for r in [-1, 1]^n, assuming min(r) < 0 < max(r), "
                       "f(r) < -0.5")
    assert p.verdict == "falsified", p.verdict
    (r,) = p.meta["mathema.counterexample_args"]
    assert min(r) < 0 < max(r), r
    q = _one(smallest, "for r in [-1, 1]^n, assuming min(r) < 0 < max(r), "
                       "f(r) < 0")
    assert q.verdict in ("proven", "holds"), (q.verdict, q.counterexample)


def test_a_chained_equality_premise_is_refused_with_a_reason():
    p = _one(gap, "for a in [-2, 2], b in [-2, 2], "
                  "assuming a == 0 == b, f(a, b) == 0")
    assert p.verdict == "skipped", p.verdict
    assert "assuming" in (p.note or ""), p.note


def test_a_premise_comparing_with_a_comparison_is_refused():
    p = _one(gap, "for a in [-2, 2], b in [-2, 2], "
                  "assuming a < (0 < b), f(a, b) > 0")
    assert p.verdict == "skipped", (p.verdict, p.counterexample)


def reciprocal_pole(x):
    return 1 / (x - 1)


@pytest.mark.parametrize("premise", ["x > 2", "2 < x < 9"])
def test_a_definedness_claim_under_a_premise_reads_its_region(premise):
    p = _one(reciprocal_pole, f"assuming {premise}, is_defined(f)")
    assert p.verdict != "falsified", (p.verdict, p.counterexample)


def test_a_chained_premise_around_the_pole_still_falsifies_definedness():
    p = _one(reciprocal_pole, "assuming 0 < x < 9, is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.counterexample)
