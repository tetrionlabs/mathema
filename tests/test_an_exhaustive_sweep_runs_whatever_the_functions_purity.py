# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A finite integer domain is swept point by point. A counterexample the
sweep executes falsifies the claim whatever is known about the
function's purity; only a clean sweep's proof needs the function shown
pure, so a function the examination cannot read (it calls pandas.isna,
which has no purity entry) gets holds with the reason, never proven."""
import math

import pytest

from mathema._brute_force import _examined_clean
from mathema.conjecture import check_conjectures, claim

pd = pytest.importorskip("pandas")


def exposure_counts(active: int, periods: int) -> float:
    """The share of periods with exposure, rounded up to a whole percent."""
    if periods <= 0 or pd.isna(active):
        return 0.0
    hits = len([day for day in range(periods) if day < active])
    return math.ceil(hits / periods * 100) / 100


def exposure_floor(active: int, periods: int) -> float:
    if periods <= 0 or pd.isna(active):
        return 0.0
    hits = len([day for day in range(periods) if day < active])
    return math.floor(hits / periods * 100) / 100


def exposure_pure(active: int, periods: int) -> float:
    if periods <= 0:
        return 0.0
    hits = len([day for day in range(periods) if day < active])
    return math.floor(hits / periods * 100) / 100


_DOMAIN = ("for active in [0, 50] : int, periods in [1, 50] : int, "
           "assuming active <= periods, ")


def test_the_examination_cannot_read_the_pandas_call():
    assert not _examined_clean(exposure_counts)
    assert not _examined_clean(exposure_floor)
    assert _examined_clean(exposure_pure)


def test_a_rare_counterexample_is_found_though_purity_is_unknown():
    (p,) = check_conjectures(exposure_counts, [claim(
        _DOMAIN + "f(active, periods) <= active / periods + 0.0099")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.route == "derive:brute_force"
    assert p.counterexample == "active = 7, periods = 25"
    assert exposure_counts(7, 25) == 0.29


def test_a_clean_sweep_over_an_unexamined_function_holds_with_its_reason():
    (p,) = check_conjectures(exposure_floor, [claim(
        _DOMAIN + "f(active, periods) <= active / periods")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert p.route == "derive:brute_force"
    assert "proven needs the function to be shown pure" in p.note


def test_a_clean_sweep_over_a_pure_function_is_still_proven():
    (p,) = check_conjectures(exposure_pure, [claim(
        _DOMAIN + "f(active, periods) <= active / periods")])
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.route == "derive:brute_force"
