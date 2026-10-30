# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An absence row reads only what the absence does.

`total_return([], None)` returns nan because the returns are empty, not
because `aggregate` is absent: with `aggregate` present it returns nan
too. Such a call says nothing about `absent[aggregate]`, so the row is
the same whichever claims happened to call f with an empty input, and
in whichever order they run. Where the absence itself gives the no
value back (with the parameter present f returns a number), the row
still says so.
"""
import math

import mathema


def total_return(returns: list[float], aggregate: str | None = None) -> float:
    if len(returns) == 0:
        return math.nan
    growth = 1.0
    for r in returns:
        growth *= 1.0 + r
    if aggregate is None:
        return growth - 1.0
    return growth ** (252 / len(returns)) - 1.0


def no_value_without_aggregate(returns: list[float],
                               aggregate: str | None = None) -> float:
    if aggregate is None:
        return math.nan
    return float(len(returns))


EMPTY = "f([], aggregate) != 0"
VALUE = "for returns in [-0.5, 0.5]^n, f(returns, aggregate) >= -1"


def _absent_row(fn, claims):
    record = mathema.check(fn, claims=claims)
    rows = [p for p in record.probes if p.name == "absent[aggregate]"]
    return rows[0] if rows else None


def test_an_empty_input_beside_a_value_claim_does_not_falsify_the_row():
    row = _absent_row(total_return, [EMPTY, VALUE])
    assert row is not None
    assert row.verdict != "falsified", (row.verdict, row.note)


def test_the_row_is_the_same_whichever_claims_run_and_in_what_order():
    alone = _absent_row(total_return, [VALUE])
    first = _absent_row(total_return, [EMPTY, VALUE])
    second = _absent_row(total_return, [VALUE, EMPTY])
    assert alone.verdict == first.verdict == second.verdict, \
        (alone.verdict, first.verdict, second.verdict)
    assert alone.statement == first.statement == second.statement


def test_an_empty_input_alone_is_not_read_as_the_absence_converting():
    row = _absent_row(total_return, [EMPTY])
    assert row is None or "converts" not in (row.note or ""), row.note


def test_an_absence_that_gives_no_value_back_is_still_read():
    row = _absent_row(no_value_without_aggregate,
                      ["for returns in [-0.5, 0.5]^n, f(returns, aggregate) != 1"])
    assert row is not None
    assert "converts" in (row.note or "") + row.statement, (row.verdict, row.note)
