# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A vector over a fixed-length box is tried at the box's corners.

`for r in [-0.1, 0.1]^13, year_total(r) >= -1.2` is false: every month
at -0.1 sums to -1.3. Random draws of thirteen elements almost never
land all at the lower end, so the probe tries the all-lower and
all-upper vectors before sampling, and a linear sum over the box is
settled at those corners.
"""
from __future__ import annotations

from mathema.conjecture import check_conjectures, claim


def year_total(r: list) -> float:
    """The sum of the monthly returns."""
    total = 0.0
    for x in r:
        total += x
    return total


def _one(text):
    (p,) = check_conjectures(year_total, [claim(text)])
    return p


def test_the_all_lower_corner_falsifies_a_lower_bound():
    p = _one("for r in [-0.1, 0.1]^13, f(r) >= -1.2")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "-0.1, -0.1" in (p.counterexample or ""), p.counterexample


def test_the_all_upper_corner_falsifies_an_upper_bound():
    p = _one("for r in [-0.1, 0.1]^13, f(r) <= 1.2")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_bound_the_corners_respect_is_not_falsified():
    p = _one("for r in [-0.1, 0.1]^13, f(r) >= -1.31")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)


def test_a_fixed_size_matrix_box_is_tried_at_its_corners():
    def total(a: list) -> float:
        return sum(sum(row) for row in a)
    (p,) = check_conjectures(total, [claim(
        "for a in [-1, 1]^(4,4), f(a) >= -15.5")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_derive_names_the_corner_where_a_linear_sum_is_least():
    p = _one("for r in [-0.1, 0.1]^13, f(r) >= -1.2")
    assert "least at the corner" in (p.note or ""), p.note
