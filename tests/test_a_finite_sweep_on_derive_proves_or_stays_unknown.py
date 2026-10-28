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


pd = None
try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pass


def exposure_percent(active: int, periods: int) -> int:
    """Whole percent of periods with exposure; integer arithmetic only."""
    if periods <= 0 or pd.isna(active):
        return 0
    return active * 100 // periods


def test_a_sweep_over_a_function_not_shown_pure_says_what_would_prove_it():
    # every point passes; the examination cannot read pandas.isna, and
    # the exact reading cannot follow that call either, so the sweep is
    # no proof: holds on the default route, unknown on derive (inexact),
    # each saying what would make the sweep a proof
    import pytest
    if pd is None:
        pytest.skip("pandas is not installed")
    law = ("for active in [0, 20] : int, periods in [1, 20] : int, "
           "assuming active <= periods, f(active, periods) <= 100 * active / periods")
    (p,) = check_conjectures(exposure_percent, [claim(law)])
    assert (p.verdict, p.route) == ("holds", "derive:brute_force"), (p.verdict,
                                                                     p.note)
    (q,) = check_conjectures(exposure_percent, [claim(law, route="derive")])
    assert (q.verdict, q.route) == ("unknown", "derive"), (q.verdict, q.note)
    for row in (p, q):
        assert "proven needs the function to be shown pure" in row.note
        assert "pandas.isna" in row.note
        assert "would make the sweep a proof" in row.note
