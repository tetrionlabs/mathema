# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A domain that comes from a type marker (`Annotated[float,
Probability]`) reaches the built-in shape checks (monotonicity,
curvature) as a `Domain` object, not a `(lo, hi)` pair. Those checks
sample inside it and never step outside it."""
from typing import Annotated

import mathema
from mathema.types import Probability


def odds(p: Annotated[float, Probability]) -> float:
    """A probability's odds, defined on [0, 1)."""
    if not 0.0 <= p <= 1.0:
        raise ValueError("p is not a probability")
    return p / (1.0 - p + 1e-12)


def weighted(prior: Annotated[float, Probability],
             likelihood: Annotated[float, Probability]) -> float:
    """A weighted average of two probabilities."""
    if not (0.0 <= prior <= 1.0 and 0.0 <= likelihood <= 1.0):
        raise ValueError("outside [0, 1]")
    return 0.25 * prior + 0.75 * likelihood


def test_a_marker_domain_reaches_the_shape_checks_without_crashing():
    rec = mathema.check(weighted)
    shape = [p for p in rec.probes
             if p.name.split("[", 1)[0] in ("monotonic_increasing",
                                            "monotonic_decreasing", "convex",
                                            "concave", "affine")]
    assert shape, [p.name for p in rec.probes]


def test_shape_checks_never_step_outside_a_marker_domain():
    # odds raises outside [0, 1]; a shape check that sampled or stepped
    # outside the marker's domain would report that raise as a finding
    rec = mathema.check(odds)
    for p in rec.probes:
        if p.name.split("[", 1)[0] in ("monotonic_increasing", "convex"):
            assert "not a probability" not in (p.counterexample or ""), p
            assert p.verdict != "falsified", (p.name, p.counterexample)
