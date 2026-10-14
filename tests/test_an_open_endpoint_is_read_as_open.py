# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An interval's open end excludes its endpoint, and the built-in
claims read it that way: `(0, 10]` never contains 0, so math.log is
inside its number set over it, and log's natural domain `(0, oo)` is
proven. A closed end at the same point still contains it, and still
falsifies."""
import math

from mathema.conjecture import check_conjectures, claim


def log_growth(ratio: float) -> float:
    return math.log(ratio)


def log_one_plus(x: float) -> float:
    return math.log1p(x)


def _one(fn, text):
    (p,) = check_conjectures(fn, [claim(text)])
    return p


def test_an_open_lower_end_at_logs_boundary_is_proven():
    for text in ("for ratio in (0, 10], is_number_set_safe(ratio)",
                 "for ratio in (0, oo), is_number_set_safe(ratio)"):
        p = _one(log_growth, text)
        assert p.verdict == "proven", (text, p.verdict, p.note)


def test_an_open_end_at_log1ps_boundary_is_proven():
    for text in ("for x in (-1, 0], is_number_set_safe(x)",
                 "for x in (-1, 1), is_number_set_safe(x)"):
        p = _one(log_one_plus, text)
        assert p.verdict == "proven", (text, p.verdict, p.note)


def test_a_closed_end_at_the_boundary_still_falsifies():
    p = _one(log_growth, "for ratio in [0, 10], is_number_set_safe(ratio)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("ratio = 0"), p.counterexample
    p = _one(log_one_plus, "for x in [-1, 0], is_number_set_safe(x)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("x = -1"), p.counterexample


def test_definedness_over_an_open_end_at_logs_boundary_is_proven():
    p = _one(log_growth, "for ratio in (0, 10], is_defined(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "mathema bug" not in (p.note or ""), p.note
    p = _one(log_growth, "for ratio in [0, 10], is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
