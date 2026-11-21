# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A derive proof of a claim whose every variable ranges over texts
has no `[float]` companion: there is no float arithmetic in it to run
again. The proof states that no companion was made, and why. A numeric
claim keeps its companion."""
import warnings

import pytest

import _text_validators as T
from mathema.conjecture import check_conjectures, claim

pytest.importorskip("z3")


@pytest.fixture(autouse=True)
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


def _rows(fn, text):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return check_conjectures(fn, [claim(text, route="best")], float_companions=True)


def test_a_proven_claim_over_texts_spawns_no_float_row():
    rows = _rows(T.check_slug, "for text in L[slugs], f(text) == text")
    assert [r.name for r in rows] == ["f_text_eq_text"], [r.name for r in rows]
    (proven,) = rows
    assert proven.verdict == "proven"
    assert proven.meta["mathema.float_companion"].startswith("none (")


def _double(x: float) -> float:
    return 2 * x


def test_a_numeric_claim_keeps_its_float_row():
    rows = _rows(_double, "for x in [0, 1], f(x) == 2 * x")
    names = [r.name for r in rows]
    assert len(rows) == 2 and names[1] == names[0] + "[float]", names
    assert rows[0].meta["mathema.float_companion"] == names[1]
