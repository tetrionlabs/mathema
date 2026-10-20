# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive proves a branched function piece by piece, splitting the
domain at the guard's boundaries. The claim's premise holds on every
piece as it does on the whole domain: `assuming is_defined(f)` leaves
out the points where f raises, and an ordinary premise (`assuming x >=
5`) leaves out the points it rules out, so a piece where f raises, or a
point the premise excludes, is never a counterexample. Derive and the
probe then agree."""
import sys

import pytest

from mathema.conjecture import check_conjectures, claim


def guarded(x: float) -> float:
    if x < 0:
        raise ValueError("negative")
    return x + 1


def exits_below(x: float) -> float:
    if x < 0:
        sys.exit(2)
    return x + 1


def _row(fn, text, route):
    return check_conjectures(fn, [claim(text, route=route)])[0]


@pytest.mark.parametrize("fn", [guarded, exits_below],
                         ids=lambda f: f.__name__)
@pytest.mark.parametrize("text", [
    "assuming is_defined(f), for x in [-10, 10], f(x) >= 1",
    "assuming is_defined(f), for x in [-10, 10], f(x) >= 0",
])
def test_the_definedness_premise_leaves_out_the_raising_piece(fn, text):
    derived = _row(fn, text, "derive")
    probed = _row(fn, text, "probe")
    assert derived.verdict == "proven", (derived.verdict, derived.sketch)
    assert probed.verdict == "holds", (probed.verdict, probed.counterexample)


def test_an_ordinary_premise_holds_on_every_piece():
    p = _row(guarded, "assuming x >= 5, for x in [-10, 10], f(x) >= 6",
             "derive")
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_without_the_premise_the_raising_piece_still_falsifies():
    p = _row(guarded, "for x in [-10, 10], f(x) >= 1", "derive")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert "raises ValueError" in p.sketch


def test_a_premise_does_not_hide_a_point_it_admits():
    p = _row(guarded, "assuming is_defined(f), for x in [-10, 10], f(x) >= 2",
             "derive")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
