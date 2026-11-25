# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Raise-reading cases: a mathema domain wrapper whose own check fires on part of the claim's domain."""
from mathema.authoring import enforce_domain

D = {"x": (-5, -1)}


@enforce_domain({"x": (-4.9999999, 10)})
def guarded_thin(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


def plain_thin(x: float) -> float:
    if x < 0:
        raise TypeError("neg")
    return x


CASES = [
    (guarded_thin, "for x in (-5, -1], raises(f(x), TypeError)", ("f(x)", "TypeError", D)),
    (guarded_thin, "for x in [-4.9999999, -1], raises(f(x), TypeError)", None),
]
