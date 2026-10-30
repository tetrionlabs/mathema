# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim comparing string or boolean columns says it compared them by
equality.

`~=` reads `abs(a - b) <= ε` between numbers. Strings and booleans have
no distance, so their columns compare element by element for equality,
whatever tolerance the claim declares, and the record's reading says so
rather than describing a subtraction that was not made.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402

_OVER = ('for df.s in {"u", "v"}^n \\ {missing}, df.b in {True, False}^n '
         '\\ {missing}, df.x in [0, 1]^n \\ {missing}, ')


def flip_b(df: pd.DataFrame):
    out = df.copy()
    out["b"] = ~df["b"].astype(bool)
    return out


def all_u(df: pd.DataFrame):
    out = df.copy()
    out["s"] = "u"
    return out


def same(df: pd.DataFrame):
    return df


@pytest.mark.parametrize("fn, side, tolerance, verdict", [
    (flip_b, "b", 2, "falsified"), (flip_b, "b", {"abs": 2}, "falsified"),
    (all_u, "s", 100, "falsified"), (same, "b", 2, "holds")])
def test_the_reading_says_equality(fn, side, tolerance, verdict):
    (p,) = check_conjectures(fn, [claim(
        f'{_OVER}f(df)["{side}"] ~= df.{side}', tolerance=tolerance)])
    assert p.verdict == verdict, (p.verdict, p.note)
    assert "abs(" not in p.note, p.note
    assert (f'read as f(df)["{side}"] == df.{side} element by element'
            in p.note), p.note


def test_a_numeric_column_keeps_the_tolerance_reading():
    (p,) = check_conjectures(same, [claim(f"{_OVER}f(df)[\"x\"] ~= df.x",
                                          tolerance=2)])
    assert 'read as abs(f(df)["x"] - df.x) <= ε, ε = 2 (declared)' in p.note, p.note
