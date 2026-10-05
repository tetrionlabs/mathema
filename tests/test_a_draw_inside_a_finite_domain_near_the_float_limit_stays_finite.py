# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every draw from a finite domain is a finite member of it, however
close its ends sit to the largest double: the width of
[-1e308, 1e308] and the midpoint of [1e307, 1.7e308] overflow when
computed naively, which must never put an infinity in the sample or
crash the sampler."""
import math
import random

from mathema.conjecture import check_conjectures, claim
from mathema.grammar import normalize, split_quantifier
from mathema.probing import _sample_domain
from mathema._sampling import _synth_scalar
from mathema.domain import Interval


def largest(xs: list) -> float:
    return max(xs)


def _dom(text):
    domain, _ = split_quantifier(normalize(text))
    return domain["x"]


def test_every_scalar_draw_near_the_float_limit_is_a_finite_member():
    rng = random.Random(0)
    for lo, hi in ((1e307, 1.7e308), (-1e308, 1e308), (-1.7e308, 1.7e308)):
        for _ in range(500):
            v = _synth_scalar(rng, Interval(lo, hi))
            assert math.isfinite(v) and lo <= v <= hi, (lo, hi, v)


def test_a_wide_union_is_sampled_without_crashing():
    rng = random.Random(0)
    dom = _dom("for x in [-1e308, -1] | [1, 1e308], True")
    for _ in range(200):
        v = _sample_domain(rng, dom)
        assert math.isfinite(v) and (-1e308 <= v <= -1 or 1 <= v <= 1e308)


def test_a_vector_claim_near_the_float_limit_holds():
    for law in ("for xs in [1e307, 1.7e308]^n, f(xs) <= 1.7e308",
                "for xs in [-1e308, 1e308]^n, f(xs) <= 1e308"):
        (p,) = check_conjectures(largest, [claim(law, route="probe")])
        assert p.verdict == "holds", (law, p.verdict, p.counterexample)
