# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The probe route tries the corners of a bounded domain box before it
samples at random. A value claim whose function raises only where two
parameters sit at their extremes together (a joint corner) is found
there, and an open endpoint, which is not in the domain, is never
tried."""
from mathema.conjecture import check_conjectures, claim


def bayes_update(prior: float, likelihood: float) -> float:
    evidence = prior * likelihood + (1 - prior) * (1 - likelihood)
    return prior * likelihood / evidence


def blend(a: float, b: float) -> float:
    return 0.25 * a + 0.75 * b


def test_a_raise_at_a_joint_corner_falsifies():
    (p,) = check_conjectures(bayes_update, [claim(
        "for prior in [0, 1], likelihood in [0, 1], "
        "0 <= f(prior, likelihood) <= 1", route="probe")])
    assert p.verdict == "falsified"
    assert "ZeroDivisionError" in (p.counterexample or "") or \
        "raised" in (p.counterexample or ""), p.counterexample


def test_open_endpoints_are_never_tried():
    (p,) = check_conjectures(bayes_update, [claim(
        "for prior in (0, 1), likelihood in (0, 1), "
        "0 <= f(prior, likelihood) <= 1", route="probe")])
    assert p.verdict == "holds", p.counterexample


def test_a_claim_true_at_every_corner_still_holds():
    (p,) = check_conjectures(blend, [claim(
        "for a in [0, 1], b in [0, 1], 0 <= f(a, b) <= 1", route="probe")])
    assert p.verdict == "holds", p.counterexample
