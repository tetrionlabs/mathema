# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A finite set that names nan (`{0.5, nan}`) is proven by running every
member, and the named value is judged there as on every other route:
a None its return type does not admit falsifies at nan; a None or a nan
it admits leaves nan out of the printed set."""
import math
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim


def none_under_float(x: float) -> float:
    if x != x:
        return None  # type: ignore[return-value]
    return x


def none_under_optional(x: float) -> Optional[float]:
    if x != x:
        return None
    return x


def nan_under_float(x: float) -> float:
    if x != x:
        return math.nan
    return x


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


@pytest.mark.parametrize("domain", ["{0.5, nan}", "{0, 1, nan}"])
def test_none_under_a_float_return_falsifies_at_the_named_nan(domain):
    row = _row(none_under_float, f"for x in {domain}, f(x) >= 0")
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert (row.counterexample or "").startswith("x = nan"), row.counterexample


@pytest.mark.parametrize("fn", [none_under_optional, nan_under_float],
                         ids=lambda f: f.__name__)
@pytest.mark.parametrize("domain", ["{0.5, nan}", "{0, 1, nan}"])
def test_an_admitted_result_leaves_nan_out_of_the_set(domain, fn):
    row = _row(fn, f"for x in {domain}, f(x) >= 0")
    assert row.verdict in ("proven", "holds"), (row.verdict, row.route, row.note)
    assert "nan" not in row.statement, row.statement
    assert "x = nan is left out of the domain" in (row.note or ""), row.note
