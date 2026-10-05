# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A guard in the body overrides only the case it decides. A function
that refuses a series with no value (`if xs.count() == 0: raise`) and
then returns `xs.mean()` passes every partly missing series to pandas
unchanged, so pandas.Series.mean's own policy row (a hole is dropped
while a value remains) still speaks for those calls: the drop is the
library's stated behaviour, not an unaccounted one.
"""
from __future__ import annotations

import pandas as pd

import mathema


def mean_return(xs: pd.Series) -> float:
    """The mean of a series of returns."""
    if xs.count() == 0:
        raise ValueError("no returns to average")
    return float(xs.mean())


def _check():
    return mathema.check(mean_return, claims=[
        mathema.claim("for xs in [-1, 1]^n, -1 <= f(xs) <= 1",
                      name="bounded"),
        mathema.claim("assuming count(xs) == 0, missing(f, xs) raises(ValueError)",
                      name="no_values"),
        mathema.claim("is_missing_safe(f)")])


def test_the_partly_missing_drop_comes_from_the_library_row():
    rows = {p.name: p for p in _check().probes}
    drops = [p for p in rows.values()
             if ((p.meta or {}).get("mathema.policy") or {}).get("behaviour") == "drops"]
    assert drops, sorted(rows)
    assert all("pandas.Series.mean's own policy row" in
               (p.meta["mathema.policy"].get("reason") or "") for p in drops), \
        [(p.name, p.meta["mathema.policy"].get("reason")) for p in drops]


def test_is_missing_safe_is_not_falsified_by_the_library_drop():
    rows = {p.name: p for p in _check().probes}
    gate = rows["is_missing_safe[f]"]
    assert gate.verdict in ("proven", "holds"), (gate.verdict, gate.counterexample)
    assert rows["bounded"].verdict in ("proven", "holds"), rows["bounded"].verdict
