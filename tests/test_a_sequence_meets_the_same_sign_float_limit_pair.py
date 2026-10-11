# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every sequence whose elements reach the largest double meets the
same-sign pairs there, `[M, M]` and `[-M, -M]`, beside the cancelling
pair `[M, -M]`: a sum of the pair overflows to an infinity although the
mean is M. The probe and the computation line under a proven claim both
draw them, as the scalar `(a + b) / 2` meets `a = b = M` at its box
corners."""
import sys

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.probing import sequence_corners

M = sys.float_info.max


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def test_the_corners_of_an_unbounded_sequence_hold_both_same_sign_pairs():
    corners = sequence_corners(None)
    assert [M, M] in corners and [-M, -M] in corners, corners
    assert [M, -M] in corners, corners


def test_the_corners_of_a_range_near_the_limit_hold_its_same_sign_ends():
    corners = sequence_corners((-1e308, 1.5e308))
    assert [1.5e308, 1.5e308] in corners and [-1e308, -1e308] in corners, corners


def test_a_small_range_has_no_same_sign_pair():
    assert sequence_corners((0.5, 1)) == [[0.5, 1]]


def test_the_probe_falsifies_the_mean_at_the_same_sign_pair():
    (p,) = check_conjectures(mean, [claim(
        "for xs in R^n, assuming len(xs) >= 1, min(xs) <= f(xs) <= max(xs)",
        route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "e+308" in p.counterexample, p.counterexample


def test_the_computation_line_falsifies_the_mean_at_the_same_sign_pair():
    rows = mathema.check(mean, claims=[
        "for xs in R^n, assuming len(xs) >= 1, min(xs) <= f(xs) <= max(xs)"]).probes
    falsified = [p for p in rows if p.verdict == "falsified"
                 and "e+308" in (p.counterexample or "")]
    assert falsified, [(p.name, p.verdict, p.counterexample) for p in rows]

