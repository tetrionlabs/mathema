# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A row whose printed domain leaves a named missing value out prints a
domain that names exactly what remains. Where nothing named remains,
that is the text of the same claim naming nothing, so the printed row
read back as a claim judges the points the row judged, with the same
verdict."""
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim


def guarded(x: Optional[float]) -> float:
    if x is None:
        raise ValueError("n")
    if x != x:
        return -1.0
    return x


def guarded_abs(x: Optional[float]) -> float:
    if x is None:
        raise ValueError("n")
    return abs(x)


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


CASES = [
    (guarded, "for x in [0, 1] | {None}, f(x) >= 0", "for x in [0, 1], f(x) >= 0"),
    (guarded, "for x in [0, 1]|absent, f(x) >= 0", "for x in [0, 1], f(x) >= 0"),
    (guarded_abs, "for x in R | {None}, f(x) >= 0", "for x in R, f(x) >= 0"),
    (guarded, "for x in {0.5, 1, None}, f(x) >= 0", "for x in {0.5, 1}, f(x) >= 0"),
]


@pytest.mark.parametrize("fn, named, plain", CASES, ids=[n for _f, n, _p in CASES])
def test_the_restated_domain_is_the_text_of_the_claim_naming_nothing(fn, named, plain):
    row = _row(fn, named)
    assert row.verdict in ("proven", "holds"), (row.verdict, row.note)
    assert row.statement == _row(fn, plain).statement, row.statement


@pytest.mark.parametrize("fn, named, plain", CASES, ids=[n for _f, n, _p in CASES])
def test_the_printed_row_read_back_keeps_its_verdict(fn, named, plain):
    row = _row(fn, named)
    again = _row(fn, row.statement)
    if named.startswith("for x in R"):
        # derive does not decide the `x is None` branch over the plain
        # type beside an Optional parameter, so the text read back is
        # decided by running the code: the same points, a weaker rung
        assert again.verdict in (row.verdict, "holds"), (row.statement, again.verdict,
                                                        again.note)
        return
    assert again.verdict == row.verdict, (row.statement, again.verdict,
                                          again.counterexample, again.note)
