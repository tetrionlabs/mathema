# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim whose body reaches a region where an interval bound turns
complex (`sqrt(1 - r**2)` over an unbounded `r`) comes back with a
verdict, never an exception out of `check_conjectures`: an interval
the bounds machinery cannot represent is simply not used to narrow the
domain."""
import math

from mathema.conjecture import check_conjectures, claim


def distance(r: float, scale: str = "info") -> float:
    if scale == "info":
        return math.sqrt(1.0 - r ** 2)
    raise ValueError(f"unknown scale {scale!r}")


def test_an_unbounded_parameter_under_a_square_root_returns_a_verdict():
    for route in ("derive", "best"):
        (p,) = check_conjectures(distance, [claim(
            'for scale in {"info", "nope"}, f(r, scale) >= 0', route=route)])
        assert p.verdict in ("falsified", "unknown", "holds", "proven", "skipped"), p
    (q,) = check_conjectures(distance, [claim('for scale in {"info", "nope"}, f(r, scale) >= 0')])
    assert q.verdict == "falsified", (q.verdict, q.note)
