# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raises claim over a domain that names a missing value claims the
raise at that value too: where the call returns there (0.0, None or
nan), the claim is falsified with the named value as its witness, in
every spelling of the domain and on both routes. A note names only rows
the record holds."""
import math
from typing import Optional

import pytest

import mathema
from mathema.conjecture import claim


def zero_at_none(x: Optional[float]) -> float:
    if x is None:
        return 0.0
    raise ValueError("all")


def none_at_none(x: Optional[float]) -> float:
    if x is None:
        return None  # type: ignore[return-value]
    raise ValueError("all")


def nan_at_none(x: Optional[float]) -> float:
    if x is None:
        return math.nan
    raise ValueError("all")


def zero_at_nan(x: float) -> float:
    if x != x:
        return 0.0
    raise ValueError("all")


def raises_everywhere(x: Optional[float]) -> float:
    if x is None:
        raise ValueError("none")
    raise ValueError("all")


NONE_DOMAINS = ["{0, None}", "{1, 2, None}", "[0, 1] : float|absent",
                "[0, 1] | {None}"]
NONE_FNS = [zero_at_none, none_at_none, nan_at_none]


def _rows(fn, text, route=None):
    extra = {"route": route} if route else {}
    rec = mathema.check(fn, claims=[claim(text, name="c", **extra)])
    return rec, {p.name: p for p in rec.probes}


def _notes_name_rows_that_exist(rows):
    import re
    for row in rows.values():
        for named in re.findall(r"policy row ([\w\[\]]+)", row.note or ""):
            assert named in rows, (named, row.note, sorted(rows))


@pytest.mark.parametrize("route", [None, "probe"])
@pytest.mark.parametrize("fn", NONE_FNS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("domain", NONE_DOMAINS)
def test_a_return_at_a_named_none_falsifies_the_raises_claim(domain, fn, route):
    _rec, rows = _rows(fn, f"for x in {domain}, raises(f(x), ValueError)", route)
    main = rows["c"]
    assert main.verdict == "falsified", (main.verdict, main.route, main.note)
    assert (main.counterexample or "").startswith("x = None"), main.counterexample
    _notes_name_rows_that_exist(rows)


@pytest.mark.parametrize("route", [None, "probe"])
def test_a_return_at_a_named_nan_falsifies_the_raises_claim(route):
    _rec, rows = _rows(zero_at_nan, "for x in [0, 1] | {nan}, raises(f(x), ValueError)",
                       route)
    main = rows["c"]
    assert main.verdict == "falsified", (main.verdict, main.route, main.note)
    assert (main.counterexample or "").startswith("x = nan"), main.counterexample
    _notes_name_rows_that_exist(rows)


def test_a_raise_at_the_named_none_keeps_the_point():
    _rec, rows = _rows(raises_everywhere, "for x in {0, None}, raises(f(x), ValueError)")
    main = rows["c"]
    assert main.verdict != "falsified", (main.verdict, main.note)
    assert "absent" in main.statement, main.statement
