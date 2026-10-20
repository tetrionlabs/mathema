# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness holding `pd.NA` is shown, never the end of the check.

A large table witness is shortened to its shape and first entries, and
the shortening asks whether every entry is the same. `pd.NA` answers
`==` with neither true nor false, so the reading treats a hole as a
hole: two holes of one member are the same entry, a hole and a value
are not.
"""
from __future__ import annotations

import pytest

pytest.importorskip("pandas")

import pandas as pd  # noqa: E402

from mathema._shapes import witness_text  # noqa: E402
from mathema.conjecture import check_conjectures, claim  # noqa: E402


def totals(a: pd.DataFrame):
    return a.sum()


def test_a_reduction_over_a_boolean_column_with_holes_is_adjudicated():
    (p,) = check_conjectures(totals, [claim(
        'for a.x in [0, 1]^n, a.i in [0, 10]^n subset Z, a.s in {"u", "v"}^n, '
        'a.b in {True, False}^n, f(a)["b"] ~= sum(a.b)')])
    assert p.verdict in ("holds", "proven", "falsified", "unknown"), p.verdict


def test_a_table_of_na_reads_as_every_entry_na():
    shown = witness_text({"b": [pd.NA] * 9, "c": [pd.NA] * 9})
    assert shown is not None and "every entry <NA>" in shown, shown


def test_na_beside_values_is_not_every_entry_the_same():
    shown = witness_text({"b": [pd.NA, True] * 5, "c": [True] * 10})
    assert shown is not None and "every entry" not in shown, shown
