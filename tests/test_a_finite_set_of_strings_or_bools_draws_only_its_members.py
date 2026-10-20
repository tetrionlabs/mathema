# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A vector whose elements range over a finite set of strings or of
booleans is drawn from that set alone.

`for a.k in {"u", "v"}^n` binds every element of the column `k` to
one of `"u"` and `"v"`. The corners a sequence of numbers is drawn at
(entries that cancel at a large magnitude, a series one ulp from
constant) belong to a real range, and a set of strings is none, so no
draw of such a vector holds a number.
"""
from __future__ import annotations

import random

import pytest

from mathema.conjecture import claim
from mathema.interfaces.extension import sample_bound


@pytest.mark.parametrize("text, members", [
    ('for a.k in {"u", "v"}^n, f(a) == 0', {"u", "v"}),
    ("for a.b in {True, False}^n, f(a) == 0", {True, False}),
])
def test_every_draw_holds_only_members_of_the_set(text, members):
    (bound,) = claim(text).domain.values()
    rng = random.Random(0)
    for _ in range(400):
        drawn = sample_bound(bound, rng, "sequence")
        assert drawn and all(v in members and type(v) is type(next(iter(members)))
                             for v in drawn), drawn


def test_a_set_of_numbers_with_a_hole_still_meets_the_number_corners():
    (bound,) = claim("for xs in ([-1, 1] | {missing})^n, f(xs) == 0").domain.values()
    rng = random.Random(0)
    draws = [sample_bound(bound, rng, "sequence") for _ in range(400)]
    assert any(len(d) >= 2 and d[0] == -d[1] and d[0] != 0 for d in draws)
