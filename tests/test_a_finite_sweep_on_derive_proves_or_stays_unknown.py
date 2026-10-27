# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""On route derive an exhaustive exact sweep of a finite domain with
every point passing is proven on `derive:brute_force`; a sweep that
passes only within a tolerance at points with no exact value
(inexact), or that runs part of the domain, is no proof, and the claim
stays unknown on the derive route rather than holding."""
from mathema.conjecture import check_conjectures, claim

#: a float the body reads from outside: no exact reading
OFFSET = 5e-10


def offset_read(n: int) -> float:
    i = 0
    while i < 3:
        i += 1
    return n + OFFSET


def counted(n: int) -> int:
    i = 0
    while i < n:
        i += 1
    return i


def test_an_exhaustive_exact_sweep_is_proven_on_derive():
    (p,) = check_conjectures(counted, [claim(
        "for n in [0, 30] subset Z, f(n) == n", route="derive")])
    assert (p.verdict, p.route) == ("proven", "derive:brute_force")


def test_an_inexact_sweep_stays_unknown_on_derive():
    law = "for n in {0, 1, 2, 3}, f(n) == n"
    (p,) = check_conjectures(offset_read, [claim(law, route="derive",
                                                 tolerance=1e-9)])
    assert (p.verdict, p.route) == ("unknown", "derive"), (p.verdict, p.route,
                                                           p.note)
    assert "every point" in p.note
    # the default route keeps the sweep's holds
    (q,) = check_conjectures(offset_read, [claim(law, tolerance=1e-9)])
    assert (q.verdict, q.route) == ("holds", "derive:brute_force")
