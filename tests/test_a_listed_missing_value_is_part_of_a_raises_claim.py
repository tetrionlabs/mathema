# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `raises(f(x), E)` claim over a domain that lists a missing value
(`{-1, -2, nan}`, `{-1, None}`, `{missing}`, `[-5, -1] | {nan}`) states
the raise at that value too. Derive reads only the real points of a
domain, so it does not prove such a claim; a finite domain is then swept
point by point, the missing values run as the values they stand for."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim


def raises_below_zero(x: float) -> float:
    if x < 0:
        raise ValueError(f"{x}")
    return x


def raises_below_zero_or_at_nan(x: float) -> float:
    if x < 0 or x != x:
        raise ValueError("bad")
    return x


def _row(fn, domain: str, route: str = "best"):
    (row,) = check_conjectures(
        fn, [claim(f"for x in {domain}, raises(f(x), ValueError)", route=route)])
    return row


_LISTS = ["{-1, -2, nan}", "{-1, -2, None}", "{-1, -2, missing}"]


@pytest.mark.parametrize("domain", _LISTS)
def test_a_listed_missing_value_where_the_function_does_not_raise_falsifies(domain):
    assert math.isnan(raises_below_zero(math.nan))
    with pytest.raises(TypeError):
        raises_below_zero(None)
    assert _row(raises_below_zero, domain, route="derive").verdict != "proven"
    row = _row(raises_below_zero, domain)
    assert row.verdict == "falsified", (row.verdict, row.route, row.sketch)


def test_a_missing_value_beside_an_interval_is_not_proven():
    row = _row(raises_below_zero, "[-5, -1] | {nan}")
    assert row.verdict != "proven", (row.verdict, row.route, row.sketch)


def test_a_listed_missing_value_where_the_function_raises_is_proven():
    row = _row(raises_below_zero_or_at_nan, "{-1, -2, nan}")
    assert row.verdict == "proven", (row.verdict, row.route, row.sketch)


def test_the_real_points_alone_are_still_proven_by_derive():
    row = _row(raises_below_zero, "{-1, -2}", route="derive")
    assert row.verdict == "proven", (row.verdict, row.route, row.sketch)
